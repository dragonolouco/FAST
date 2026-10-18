#define _GNU_SOURCE
/* lfvm — máquina de .lfbc da linguagem Lira. Números no laço quente não viram objeto Python. */
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
  OP_HALT = 0, OP_CONST, OP_LOAD_LOCAL, OP_STORE_LOCAL, OP_LOAD_GLOBAL, OP_STORE_GLOBAL,
  OP_LOAD_INDEX, OP_STORE_INDEX, OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_POW,
  OP_NEG, OP_NOT, OP_EQ, OP_NE, OP_LT, OP_LE, OP_GT, OP_GE, OP_JUMP, OP_JUMP_IF_FALSE,
  OP_POP, OP_CALL, OP_RETURN, OP_MAKE_LIST, OP_BUILTIN, OP_DUP, OP_PRINT = 240
};

typedef struct Val Val;
typedef struct {
  Val *items;
  uint32_t len, cap;
} List;

struct Val {
  uint8_t type; /* 0 null, 1 num, 2 str, 3 list */
  double num;
  char *str;
  uint32_t slen;
  List *list;
};

typedef struct {
  uint8_t op, a;
  uint16_t b;
  uint32_t line;
} Ins;

typedef struct {
  char *name;
  uint16_t arity, nlocals;
  uint32_t ncode;
  Ins *code;
} Func;

static Val *consts;
static uint16_t nconsts, nglobals, nfuncs;
static Val *globs;
static Func *funcs;
static Val *stack;
static uint32_t sp, stack_cap;
static int failed;

static void die(uint32_t line, const char *msg) {
  fprintf(stderr, "ERRO: linha %u: %s\n", line, msg);
  failed = 1;
  exit(2);
}

static void *xmalloc(size_t n) {
  void *p = calloc(1, n ? n : 1);
  if (!p) die(0, "sem memoria");
  return p;
}

static void push(Val v) {
  if (sp >= stack_cap) die(0, "pilha cheia");
  stack[sp++] = v;
}

static Val pop(void) {
  if (!sp) die(0, "pilha vazia");
  return stack[--sp];
}

static Val num(double x) {
  Val v;
  memset(&v, 0, sizeof v);
  v.type = 1;
  v.num = x;
  return v;
}

static int truthy(Val v) {
  if (v.type == 1) return v.num != 0.0 && !isnan(v.num);
  if (v.type == 2) return v.slen != 0;
  if (v.type == 3) return v.list && v.list->len != 0;
  return 0;
}

static double need_num(Val v, uint32_t line) {
  if (v.type != 1) die(line, "esperado numero");
  return v.num;
}

static int32_t as_index(Val v, uint32_t size, uint32_t line) {
  double n;
  int64_t i;
  if (v.type != 1 || v.num != floor(v.num)) die(line, "indice precisa ser inteiro");
  n = v.num;
  i = (int64_t)n;
  if (i < 0) i += (int64_t)size;
  if (i < 0 || (uint32_t)i >= size) die(line, "indice fora da trilha");
  return (int32_t)i;
}

static int vals_eq(Val a, Val b) {
  uint32_t i;
  if (a.type != b.type) return 0;
  if (a.type == 0) return 1;
  if (a.type == 1) return a.num == b.num;
  if (a.type == 2) return a.slen == b.slen && memcmp(a.str, b.str, a.slen) == 0;
  if (!a.list || !b.list || a.list->len != b.list->len) return 0;
  for (i = 0; i < a.list->len; i++) if (!vals_eq(a.list->items[i], b.list->items[i])) return 0;
  return 1;
}

static void print_val(FILE *fp, Val v) {
  uint32_t i;
  if (v.type == 0) { fputs("vazio", fp); return; }
  if (v.type == 1) {
    if (isnan(v.num)) { fputs("nan", fp); return; }
    if (isinf(v.num)) { fputs(v.num > 0 ? "inf" : "-inf", fp); return; }
    if (v.num == floor(v.num) && fabs(v.num) < 1e15) fprintf(fp, "%.0f", v.num);
    else fprintf(fp, "%.12g", v.num);
    return;
  }
  if (v.type == 2) { fwrite(v.str, 1, v.slen, fp); return; }
  fputc('[', fp);
  for (i = 0; i < v.list->len; i++) {
    if (i) fputs(", ", fp);
    print_val(fp, v.list->items[i]);
  }
  fputc(']', fp);
}

static void json_val(FILE *fp, Val v) {
  uint32_t i;
  if (v.type == 0) { fputs("null", fp); return; }
  if (v.type == 1) {
    if (isnan(v.num) || isinf(v.num)) { fputc('"', fp); print_val(fp, v); fputc('"', fp); return; }
    if (v.num == floor(v.num) && fabs(v.num) < 9007199254740992.0) fprintf(fp, "%.0f", v.num);
    else fprintf(fp, "%.17g", v.num);
    return;
  }
  if (v.type == 2) {
    fputc('"', fp);
    for (i = 0; i < v.slen; i++) {
      unsigned char c = (unsigned char)v.str[i];
      if (c == '"' || c == '\\') fprintf(fp, "\\%c", c);
      else if (c == '\n') fputs("\\n", fp);
      else if (c < 32) fprintf(fp, "\\u%04x", c);
      else fputc(c, fp);
    }
    fputc('"', fp);
    return;
  }
  fputc('[', fp);
  for (i = 0; i < (v.list ? v.list->len : 0); i++) {
    if (i) fputc(',', fp);
    json_val(fp, v.list->items[i]);
  }
  fputc(']', fp);
}

static int16_t rel16(uint16_t b) { return b >= 32768 ? (int16_t)(b - 65536) : (int16_t)b; }

static void builtin(uint16_t id, uint8_t argc, uint32_t line) {
  Val args[8];
  int i;
  if (argc > 8) die(line, "builtin demais");
  for (i = argc - 1; i >= 0; i--) args[i] = pop();
  if (id == 0) {
    if (args[0].type == 3) push(num(args[0].list->len));
    else if (args[0].type == 2) push(num(args[0].slen));
    else die(line, "tamanho espera trilha ou texto");
  } else if (id == 1) {
    double s = 0;
    if (args[0].type != 3) die(line, "soma espera trilha");
    for (i = 0; i < (int)args[0].list->len; i++) s += need_num(args[0].list->items[i], line);
    push(num(s));
  } else if (id == 2) push(num(fabs(need_num(args[0], line))));
  else if (id == 3) {
    double x = need_num(args[0], line);
    if (x < 0) die(line, "raiz de negativo");
    push(num(sqrt(x)));
  } else if (id == 4) push(num(floor(need_num(args[0], line))));
  else if (id == 5) push(num(ceil(need_num(args[0], line))));
  else if (id == 6) {
    double s = 0;
    uint32_t n;
    if (args[0].type != 3 || args[1].type != 3 || args[0].list->len != args[1].list->len)
      die(line, "ponto espera trilhas do mesmo tamanho");
    n = args[0].list->len;
    for (i = 0; i < (int)n; i++) s += need_num(args[0].list->items[i], line) * need_num(args[1].list->items[i], line);
    push(num(s));
  } else if (id == 7) push(num(pow(need_num(args[0], line), need_num(args[1], line))));
  else if (id == 8) {
    char buf[128];
    Val v = args[0];
    Val out;
    memset(&out, 0, sizeof out);
    out.type = 2;
    if (v.type == 2) { out.str = v.str; out.slen = v.slen; }
    else {
      FILE *mem = open_memstream(&out.str, (size_t *)&out.slen);
      if (!mem) die(line, "texto");
      print_val(mem, v);
      fclose(mem);
    }
    (void)buf;
    push(out);
  } else if (id == 9) {
    double c = need_num(args[0], line);
    List *list;
    uint32_t n, k;
    if (c != floor(c) || c < 0 || c > 2000000) die(line, "faixa invalida");
    n = (uint32_t)c;
    list = xmalloc(sizeof *list);
    list->len = list->cap = n;
    list->items = n ? xmalloc(sizeof(Val) * n) : NULL;
    for (k = 0; k < n; k++) list->items[k] = num((double)k);
    {
      Val v;
      memset(&v, 0, sizeof v);
      v.type = 3;
      v.list = list;
      push(v);
    }
  } else die(line, "builtin desconhecido");
}

static Val run(uint16_t fn, uint32_t base) {
  uint32_t ip = 0;
  for (;;) {
    Ins in;
    uint16_t b;
    uint32_t line;
    if (ip >= funcs[fn].ncode) die(0, "pulso terminou sem entrega");
    in = funcs[fn].code[ip++];
    b = in.b;
    line = in.line;
    switch (in.op) {
      case OP_CONST: push(consts[b]); break;
      case OP_LOAD_LOCAL: push(stack[base + b]); break;
      case OP_STORE_LOCAL: stack[base + b] = pop(); break;
      case OP_LOAD_GLOBAL: push(globs[b]); break;
      case OP_STORE_GLOBAL: globs[b] = pop(); break;
      case OP_LOAD_INDEX: {
        Val index = pop(), container = pop(), out;
        int32_t i;
        memset(&out, 0, sizeof out);
        if (container.type == 3) {
          i = as_index(index, container.list->len, line);
          push(container.list->items[i]);
        } else if (container.type == 2) {
          i = as_index(index, container.slen, line);
          out.type = 2;
          out.str = xmalloc(2);
          out.str[0] = container.str[i];
          out.str[1] = 0;
          out.slen = 1;
          push(out);
        } else die(line, "nao da para indexar isso");
        break;
      }
      case OP_STORE_INDEX: {
        Val value = pop(), index = pop(), container = pop();
        if (container.type != 3) die(line, "gravacao indexada exige trilha");
        container.list->items[as_index(index, container.list->len, line)] = value;
        break;
      }
      case OP_ADD: case OP_SUB: case OP_MUL: case OP_DIV: case OP_MOD: case OP_POW: {
        Val right = pop(), left = pop();
        if (in.op == OP_ADD && left.type == 2 && right.type == 2) {
          Val v;
          memset(&v, 0, sizeof v);
          v.type = 2;
          v.slen = left.slen + right.slen;
          v.str = xmalloc(v.slen + 1);
          memcpy(v.str, left.str, left.slen);
          memcpy(v.str + left.slen, right.str, right.slen);
          push(v);
          break;
        }
        if (in.op == OP_ADD && left.type == 3 && right.type == 3) {
          List *list = xmalloc(sizeof *list);
          Val v;
          list->len = list->cap = left.list->len + right.list->len;
          list->items = xmalloc(sizeof(Val) * (list->len ? list->len : 1));
          if (left.list->len) memcpy(list->items, left.list->items, sizeof(Val) * left.list->len);
          if (right.list->len) memcpy(list->items + left.list->len, right.list->items, sizeof(Val) * right.list->len);
          memset(&v, 0, sizeof v);
          v.type = 3;
          v.list = list;
          push(v);
          break;
        }
        {
          double x = need_num(left, line), y = need_num(right, line);
          if ((in.op == OP_DIV || in.op == OP_MOD) && y == 0) die(line, "divisao ou resto por zero");
          if (in.op == OP_ADD) push(num(x + y));
          else if (in.op == OP_SUB) push(num(x - y));
          else if (in.op == OP_MUL) push(num(x * y));
          else if (in.op == OP_DIV) push(num(x / y));
          else if (in.op == OP_MOD) push(num(fmod(x, y)));
          else push(num(pow(x, y)));
        }
        break;
      }
      case OP_NEG: push(num(-need_num(pop(), line))); break;
      case OP_NOT: push(num(truthy(pop()) ? 0.0 : 1.0)); break;
      case OP_EQ: case OP_NE: case OP_LT: case OP_LE: case OP_GT: case OP_GE: {
        Val right = pop(), left = pop();
        int ok = 0;
        if (in.op == OP_LT || in.op == OP_LE || in.op == OP_GT || in.op == OP_GE) {
          double x = need_num(left, line), y = need_num(right, line);
          ok = in.op == OP_LT ? x < y : in.op == OP_LE ? x <= y : in.op == OP_GT ? x > y : x >= y;
        } else {
          ok = vals_eq(left, right);
          if (in.op == OP_NE) ok = !ok;
        }
        push(num(ok ? 1.0 : 0.0));
        break;
      }
      case OP_JUMP: ip = (uint32_t)((int32_t)ip + rel16(b)); break;
      case OP_JUMP_IF_FALSE: if (!truthy(pop())) ip = (uint32_t)((int32_t)ip + rel16(b)); break;
      case OP_POP: pop(); break;
      case OP_DUP: push(stack[sp - 1]); break;
      case OP_MAKE_LIST: {
        List *list = xmalloc(sizeof *list);
        Val v;
        uint32_t i, n = b;
        list->len = list->cap = n;
        list->items = n ? xmalloc(sizeof(Val) * n) : NULL;
        for (i = n; i-- > 0;) list->items[i] = pop();
        memset(&v, 0, sizeof v);
        v.type = 3;
        v.list = list;
        push(v);
        break;
      }
      case OP_CALL: {
        Func *callee = &funcs[b];
        uint32_t sub = sp - in.a;
        Val ret;
        if (in.a != callee->arity) die(line, "aridade errada");
        while (sp < sub + callee->nlocals) push(num(0)), stack[sp - 1].type = 0;
        ret = run((uint16_t)b, sub);
        push(ret);
        break;
      }
      case OP_RETURN: {
        Val v = pop();
        sp = base;
        return v;
      }
      case OP_BUILTIN: builtin(b, in.a, line); break;
      case OP_PRINT: {
        Val items[16];
        int n = in.a, i;
        if (n > 16) die(line, "mostra demais");
        for (i = n - 1; i >= 0; i--) items[i] = pop();
        for (i = 0; i < n; i++) {
          if (i) fputc(' ', stdout);
          print_val(stdout, items[i]);
        }
        fputc('\n', stdout);
        break;
      }
      default: die(line, "opcode desconhecido");
    }
  }
}

static uint16_t ru16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t ru32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

static void load_file(const char *path) {
  FILE *fp = fopen(path, "rb");
  long size;
  uint8_t *buf;
  uint32_t pos;
  int i;
  if (!fp) die(0, "nao abri o lfbc");
  fseek(fp, 0, SEEK_END);
  size = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  buf = xmalloc((size_t)size + 1);
  if (fread(buf, 1, (size_t)size, fp) != (size_t)size) die(0, "leitura");
  fclose(fp);
  if (size < 14 || memcmp(buf, "LFBC0001", 8) != 0) die(0, "nao e LFBC");
  nconsts = ru16(buf + 8);
  nglobals = ru16(buf + 10);
  nfuncs = ru16(buf + 12);
  pos = 14;
  consts = xmalloc(sizeof(Val) * (nconsts ? nconsts : 1));
  for (i = 0; i < nconsts; i++) {
    uint8_t tag = buf[pos++];
    memset(&consts[i], 0, sizeof(Val));
    if (tag == 0) consts[i].type = 0;
    else if (tag == 1) {
      uint64_t bits;
      memcpy(&bits, buf + pos, 8);
      pos += 8;
      consts[i].type = 1;
      memcpy(&consts[i].num, &bits, 8);
    } else if (tag == 2) {
      uint32_t n = ru32(buf + pos);
      pos += 4;
      consts[i].type = 2;
      consts[i].slen = n;
      consts[i].str = xmalloc(n + 1);
      memcpy(consts[i].str, buf + pos, n);
      pos += n;
    } else die(0, "tag LFBC");
  }
  funcs = xmalloc(sizeof(Func) * (nfuncs ? nfuncs : 1));
  for (i = 0; i < nfuncs; i++) {
    uint16_t ns = ru16(buf + pos);
    uint32_t k;
    pos += 2;
    funcs[i].name = xmalloc(ns + 1);
    memcpy(funcs[i].name, buf + pos, ns);
    pos += ns;
    funcs[i].arity = ru16(buf + pos);
    funcs[i].nlocals = ru16(buf + pos + 2);
    funcs[i].ncode = ru32(buf + pos + 4);
    pos += 8;
    funcs[i].code = xmalloc(sizeof(Ins) * (funcs[i].ncode ? funcs[i].ncode : 1));
    for (k = 0; k < funcs[i].ncode; k++) {
      funcs[i].code[k].op = buf[pos];
      funcs[i].code[k].a = buf[pos + 1];
      funcs[i].code[k].b = ru16(buf + pos + 2);
      funcs[i].code[k].line = ru32(buf + pos + 4);
      pos += 8;
    }
  }
  if (pos != (uint32_t)size) die(0, "LFBC com lixo");
  globs = xmalloc(sizeof(Val) * (nglobals ? nglobals : 1));
}

int main(int argc, char **argv) {
  const char *json_path = NULL;
  Val result;
  int i;
  if (argc < 2) {
    fprintf(stderr, "uso: lfvm arquivo.lfbc [--json saida.json]\n");
    return 2;
  }
  for (i = 2; i < argc; i++) {
    if (strcmp(argv[i], "--json") == 0 && i + 1 < argc) json_path = argv[++i];
  }
  load_file(argv[1]);
  stack_cap = 1 << 20;
  stack = xmalloc(sizeof(Val) * stack_cap);
  sp = funcs[0].nlocals;
  result = run(0, 0);
  if (json_path) {
    FILE *fp = fopen(json_path, "wb");
    if (!fp) die(0, "nao abri json");
    fputs("{\"return\":", fp);
    json_val(fp, result);
    fputs("}\n", fp);
    fclose(fp);
  }
  return failed ? 2 : 0;
}
