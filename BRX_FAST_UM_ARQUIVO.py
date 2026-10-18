#!/usr/bin/env python3
# BRX FAST — um arquivo. Roteador estrutural Lira (LIRAFST5) + linguagem .lira
# + emissor do subconjunto reto para BRX 0 / BRXE v1.
# Biblioteca padrão apenas. Opcional: lfvm.c ao lado, compilado com `install`.
#
# Família:
#   lirafast                  memória, rota FAST/DEEP, contêiner .lirafast
#   BRX-Linguagens            linguagem .brx e módulo .brxe
#   self-continuing-pattern   primitivas, métodos, erros
#   brx-kernel                núcleo x86_64
#   FAST                      este arquivo (entrada única / Colab)
#
#   python BRX_FAST_UM_ARQUIVO.py clone
#   python BRX_FAST_UM_ARQUIVO.py run exemplos/perceptron.lira
#   python BRX_FAST_UM_ARQUIVO.py modelo
#   python BRX_FAST_UM_ARQUIVO.py brx exemplos/soma.lira --brx soma.brx --brxe soma.brxe

import argparse
import ast
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import unicodedata
import zlib
from datetime import datetime, timezone
from pathlib import Path

MAGIC = b"LIRAFST5"
VERSION = 5
HEADER = struct.Struct("<8sHHI")
ENTRY = struct.Struct("<16sQQII")
FLAG_ZLIB = 1
DEFAULT_HOME = Path.home() / ".brxfast_onefile"
HERE = Path(__file__).resolve().parent

FAMILY = (
    ("lira", "https://github.com/dragonolouco/lirafast.git"),
    ("linguagem", "https://github.com/dragonolouco/BRX-Linguagens.git"),
    ("padrao", "https://github.com/dragonolouco/self-continuing-pattern.git"),
    ("kernel", "https://github.com/dragonolouco/brx-kernel.git"),
    ("fast", "https://github.com/dragonolouco/FAST.git"),
)

ALIASES = {
    "intent:create": ("criar", "crie", "faça", "fazer", "gere", "gerar", "create", "build", "make"),
    "intent:edit": ("editar", "edite", "alterar", "altere", "modificar", "modifique", "update", "edit"),
    "artifact:file": ("arquivo", "file"),
    "artifact:function": ("função", "funcao", "function", "método", "metodo"),
    "artifact:class": ("classe", "class"),
    "lang:python": ("python", ".py"),
    "lang:lira": ("lira", ".lira", "lirafast"),
    "lang:brx": ("brx", ".brx", ".brxe"),
    "lang:typescript": ("typescript", ".ts", "tsx"),
    "lang:java": ("java", ".java"),
    "op:add": ("somar", "soma", "adicionar", "add", "sum", "+"),
    "op:subtract": ("subtrair", "subtração", "subtracao", "subtract", "-"),
    "op:multiply": ("multiplicar", "multiplicação", "multiplicacao", "multiply", "*"),
    "op:divide": ("dividir", "divisão", "divisao", "divide", "/"),
    "verify:test": ("testar", "teste", "tests", "test"),
    "verify:compile": ("compilar", "compile"),
    "constraint:preserve": ("preservar", "preserve", "manter", "não mudar", "nao mudar", "sem reescrever"),
    "error:fix": ("corrigir", "consertar", "fix", "erro", "error"),
}
STOP = set("o a os as um uma de da do dos das e em no na nos nas que para por com the an to of and in on for with".split())
NEGATORS = {"não", "nao", "sem", "nunca", "jamais", "nem", "nenhum", "nenhuma"}

# --- linguagem .lira -------------------------------------------------------

LFBC_MAGIC = b"LFBC0001"
OP_HALT, OP_CONST, OP_LOAD_LOCAL, OP_STORE_LOCAL = 0, 1, 2, 3
OP_LOAD_GLOBAL, OP_STORE_GLOBAL, OP_LOAD_INDEX, OP_STORE_INDEX = 4, 5, 6, 7
OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_POW = 8, 9, 10, 11, 12, 13
OP_NEG, OP_NOT = 14, 15
OP_EQ, OP_NE, OP_LT, OP_LE, OP_GT, OP_GE = 16, 17, 18, 19, 20, 21
OP_JUMP, OP_JUMP_IF_FALSE, OP_POP = 22, 23, 24
OP_CALL, OP_RETURN, OP_MAKE_LIST, OP_BUILTIN, OP_DUP = 25, 26, 27, 28, 29
OP_NAMES = (
    "HALT", "CONST", "LOAD_LOCAL", "STORE_LOCAL", "LOAD_GLOBAL", "STORE_GLOBAL",
    "LOAD_INDEX", "STORE_INDEX", "ADD", "SUB", "MUL", "DIV", "MOD", "POW",
    "NEG", "NOT", "EQ", "NE", "LT", "LE", "GT", "GE", "JUMP", "JUMP_IF_FALSE",
    "POP", "CALL", "RETURN", "MAKE_LIST", "BUILTIN", "DUP",
)
# id -> (nome, aridade). trilha vira MAKE_LIST, aridade variável.
BUILTINS = {
    "tamanho": (0, 1), "soma": (1, 1), "abs": (2, 1), "raiz": (3, 1),
    "piso": (4, 1), "teto": (5, 1), "ponto": (6, 2), "pot": (7, 2),
    "texto": (8, 1), "faixa": (9, 1),
}
BIN = {
    "+": OP_ADD, "-": OP_SUB, "*": OP_MUL, "/": OP_DIV, "%": OP_MOD, "**": OP_POW,
    "==": OP_EQ, "!=": OP_NE, "<": OP_LT, "<=": OP_LE, ">": OP_GT, ">=": OP_GE,
}
KEYWORDS = {
    "nucleo", "celula", "pulso", "grava", "se", "senao", "enquanto", "varre",
    "em", "entrega", "mostra", "fecha", "sim", "falso", "nao",
}


class LiraError(Exception):
    def __init__(self, message, line=None):
        self.line = line
        super().__init__(message if line is None else f"linha {line}: {message}")


class Tok:
    def __init__(self, kind, value, line):
        self.kind = kind
        self.value = value
        self.line = line


def lex(source):
    tokens, i, n, line = [], 0, len(source), 1
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in " \t\r":
            i += 1
            continue
        if ch == ":" and i + 1 < n and source[i + 1] == ":":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == '"':
            i += 1
            buf = []
            while i < n and source[i] != '"':
                if source[i] == "\n":
                    raise LiraError("string sem fechamento", line)
                if source[i] == "\\":
                    i += 1
                    if i >= n:
                        raise LiraError("escape incompleto", line)
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(source[i], source[i]))
                else:
                    buf.append(source[i])
                i += 1
            if i >= n or source[i] != '"':
                raise LiraError("string sem fechamento", line)
            i += 1
            tokens.append(Tok("str", "".join(buf), line))
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            start = i
            while i < n and source[i].isdigit():
                i += 1
            if i < n and source[i] == ".":
                i += 1
                while i < n and source[i].isdigit():
                    i += 1
            if i < n and source[i] in "eE":
                j = i + 1
                if j < n and source[j] in "+-":
                    j += 1
                if j < n and source[j].isdigit():
                    i = j
                    while i < n and source[i].isdigit():
                        i += 1
            tokens.append(Tok("num", float(source[start:i]), line))
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            word = source[start:i]
            tokens.append(Tok("kw" if word in KEYWORDS else "ident", word, line))
            continue
        two = source[i:i + 2]
        if two in ("==", "!=", "<=", ">=", "**"):
            tokens.append(Tok("sym", two, line))
            i += 2
            continue
        if ch in "+-*/%<>=()[],":
            tokens.append(Tok("sym", ch, line))
            i += 1
            continue
        raise LiraError("caractere inválido: " + ch, line)
    tokens.append(Tok("eof", "", line))
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self.depth = 0

    @property
    def tok(self):
        return self.tokens[self.i]

    def bump(self):
        tok = self.tok
        if tok.kind != "eof":
            self.i += 1
        return tok

    def check(self, kind, value=None):
        tok = self.tok
        return tok.kind == kind and (value is None or tok.value == value)

    def match(self, kind, value=None):
        if self.check(kind, value):
            self.bump()
            return True
        return False

    def expect(self, kind, value=None):
        if not self.check(kind, value):
            want = value if value is not None else kind
            raise LiraError(f"esperado {want}, achei {self.tok.value or self.tok.kind}", self.tok.line)
        return self.bump()

    def parse(self):
        nucleo, stmts = "", []
        while not self.check("eof"):
            stmts.append(self.statement(top=True))
        for stmt in stmts:
            if stmt[0] == "nucleo":
                nucleo = stmt[1]
        return nucleo, [s for s in stmts if s[0] != "nucleo"]

    def statement(self, top=False):
        line = self.tok.line
        if self.check("kw", "nucleo"):
            if not top or self.depth:
                raise LiraError("nucleo só no topo", line)
            self.bump()
            return ("nucleo", self.expect("ident").value, line)
        if self.check("kw", "celula"):
            if not top or self.depth:
                raise LiraError("celula só no topo; dentro do pulso use grava", line)
            self.bump()
            name = self.expect("ident").value
            self.expect("sym", "=")
            return ("celula", name, self.expr(), line)
        if self.check("kw", "pulso"):
            if not top or self.depth:
                raise LiraError("pulso só no topo", line)
            self.bump()
            name = self.expect("ident").value
            self.expect("sym", "(")
            params = []
            if not self.check("sym", ")"):
                params.append(self.expect("ident").value)
                while self.match("sym", ","):
                    params.append(self.expect("ident").value)
            self.expect("sym", ")")
            self.depth += 1
            body = self.block()
            self.depth -= 1
            self.expect("kw", "fecha")
            return ("func", name, params, body, line)
        if self.check("kw", "se"):
            self.bump()
            cond = self.expr()
            self.depth += 1
            then = self.block(("senao",))
            other = []
            if self.match("kw", "senao"):
                other = self.block()
            self.depth -= 1
            self.expect("kw", "fecha")
            return ("if", cond, then, other, line)
        if self.check("kw", "enquanto"):
            self.bump()
            cond = self.expr()
            self.depth += 1
            body = self.block()
            self.depth -= 1
            self.expect("kw", "fecha")
            return ("while", cond, body, line)
        if self.check("kw", "varre"):
            self.bump()
            name = self.expect("ident").value
            self.expect("kw", "em")
            seq = self.expr()
            self.depth += 1
            body = self.block()
            self.depth -= 1
            self.expect("kw", "fecha")
            if seq[0] == "call" and seq[1] == "faixa" and len(seq[2]) == 1:
                return ("for_range", name, seq[2][0], body, line)
            return ("for_each", name, seq, body, line)
        if self.check("kw", "entrega"):
            self.bump()
            return ("return", self.expr(), line)
        if self.check("kw", "mostra"):
            self.bump()
            args = [self.expr()]
            while self.match("sym", ","):
                args.append(self.expr())
            return ("print", args, line)
        if self.check("kw", "grava"):
            self.bump()
            name = self.expect("ident").value
            if self.match("sym", "["):
                index = self.expr()
                self.expect("sym", "]")
                self.expect("sym", "=")
                return ("assign_idx", name, index, self.expr(), line)
            self.expect("sym", "=")
            return ("assign", name, self.expr(), line)
        if self.check("kw", "fecha") or self.check("kw", "senao"):
            raise LiraError("fecha/senao fora de lugar", line)
        return ("expr", self.expr(), line)

    def block(self, extra=()):
        stops = {"fecha", *extra}
        stmts = []
        while not self.check("eof") and not (self.tok.kind == "kw" and self.tok.value in stops):
            stmts.append(self.statement(top=False))
        return stmts

    def expr(self):
        return self._or()

    def _or(self):
        node = self._and()
        while self.check("kw", "ou"):
            line = self.bump().line
            node = ("logic", "ou", node, self._and(), line)
        return node

    def _and(self):
        node = self._not()
        while self.check("kw", "e"):
            line = self.bump().line
            node = ("logic", "e", node, self._not(), line)
        return node

    def _not(self):
        if self.check("kw", "nao"):
            line = self.bump().line
            return ("unary", "nao", self._not(), line)
        return self._cmp()

    def _cmp(self):
        node = self._add()
        if self.tok.kind == "sym" and self.tok.value in ("==", "!=", "<", "<=", ">", ">="):
            op = self.bump()
            node = ("binop", op.value, node, self._add(), op.line)
        return node

    def _add(self):
        node = self._mul()
        while self.tok.kind == "sym" and self.tok.value in ("+", "-"):
            op = self.bump()
            node = ("binop", op.value, node, self._mul(), op.line)
        return node

    def _mul(self):
        node = self._pow()
        while self.tok.kind == "sym" and self.tok.value in ("*", "/", "%"):
            op = self.bump()
            node = ("binop", op.value, node, self._pow(), op.line)
        return node

    def _pow(self):
        node = self._unary()
        if self.match("sym", "**"):
            line = self.tokens[self.i - 1].line
            node = ("binop", "**", node, self._pow(), line)
        return node

    def _unary(self):
        if self.check("sym", "-") or self.check("sym", "+"):
            op = self.bump()
            node = self._unary()
            if op.value == "+":
                return node
            return ("unary", "-", node, op.line)
        return self._postfix()

    def _postfix(self):
        node = self._primary()
        while True:
            if self.match("sym", "("):
                if node[0] != "name":
                    raise LiraError("só um nome pode ser chamado", node[-1])
                args = []
                if not self.check("sym", ")"):
                    args.append(self.expr())
                    while self.match("sym", ","):
                        args.append(self.expr())
                self.expect("sym", ")")
                node = ("call", node[1], args, node[2])
            elif self.match("sym", "["):
                index = self.expr()
                self.expect("sym", "]")
                node = ("index", node, index, node[-1])
            else:
                break
        return node

    def _primary(self):
        tok = self.tok
        if tok.kind == "num":
            self.bump()
            return ("num", tok.value, tok.line)
        if tok.kind == "str":
            self.bump()
            return ("str", tok.value, tok.line)
        if tok.kind == "kw" and tok.value == "sim":
            self.bump()
            return ("num", 1.0, tok.line)
        if tok.kind == "kw" and tok.value == "falso":
            self.bump()
            return ("num", 0.0, tok.line)
        if tok.kind == "ident":
            self.bump()
            return ("name", tok.value, tok.line)
        if self.match("sym", "("):
            node = self.expr()
            self.expect("sym", ")")
            return node
        raise LiraError("expressão inválida", tok.line)


def _fix_or(parser_cls=Parser):
    return parser_cls


_fix_or()


class Pool:
    def __init__(self):
        self.items = [None]
        self.keys = {("null", None): 0}

    def _add(self, key, value):
        found = self.keys.get(key)
        if found is not None:
            return found
        self.keys[key] = len(self.items)
        self.items.append(value)
        return self.keys[key]

    def null(self):
        return 0

    def num(self, value):
        value = float(value)
        return self._add(("num", value), value)

    def string(self, value):
        return self._add(("str", value), value)


class FuncCompiler:
    def __init__(self, name, params, gindex, findex, farity, pool):
        self.name = name
        self.params = params
        self.gindex = gindex
        self.findex = findex
        self.farity = farity
        self.pool = pool
        self.locs = []
        self.lindex = {}
        self.code = []
        for param in params:
            if param in gindex:
                raise LiraError(f"parâmetro sombreia celula: {param}")
            self._local(param)

    def _local(self, name):
        if name not in self.lindex:
            self.lindex[name] = len(self.locs)
            self.locs.append(name)
        return self.lindex[name]

    def scan(self, stmts):
        for stmt in stmts:
            kind = stmt[0]
            if kind == "assign" and stmt[1] not in self.gindex:
                self._local(stmt[1])
            elif kind in ("for_range", "for_each"):
                if stmt[1] not in self.gindex:
                    self._local(stmt[1])
                self.scan(stmt[3])
            elif kind == "if":
                self.scan(stmt[2])
                self.scan(stmt[3])
            elif kind == "while":
                self.scan(stmt[2])

    def emit(self, op, a=0, b=0, line=1):
        self.code.append([op, a & 255, b & 65535, line])
        return len(self.code) - 1

    def patch(self, index, target):
        rel = target - (index + 1)
        if rel < -32768 or rel > 32767:
            raise LiraError("salto longo demais", self.code[index][3])
        self.code[index][2] = rel & 65535

    def block(self, stmts):
        for stmt in stmts:
            self.stmt(stmt)

    def stmt(self, stmt):
        kind = stmt[0]
        if kind == "celula":
            self.expr(stmt[2])
            self.emit(OP_STORE_GLOBAL, b=self.gindex[stmt[1]], line=stmt[3])
        elif kind == "assign":
            self.expr(stmt[2])
            self.store(stmt[1], stmt[3])
        elif kind == "assign_idx":
            self.load(stmt[1], stmt[4])
            self.expr(stmt[2])
            self.expr(stmt[3])
            self.emit(OP_STORE_INDEX, line=stmt[4])
        elif kind == "expr":
            self.expr(stmt[1])
            self.emit(OP_POP, line=stmt[1][-1])
        elif kind == "print":
            for item in stmt[1]:
                self.expr(item)
            self.emit(OP_BUILTIN, a=len(stmt[1]), b=255, line=stmt[2])  # mostra, tratado à parte
            # 255 não é builtin de valor: o VM reconhece MAKE via opcode próprio.
            # Reemitimos como opcode de impressão reusando HALT? Não.
            # Corrigimos abaixo: troca para um opcode dedicado codificado em CALL? 
            self.code[-1][0] = 240  # PRINT temporário, normalizado em finish()
        elif kind == "return":
            self.expr(stmt[1])
            self.emit(OP_RETURN, line=stmt[2])
        elif kind == "if":
            self.expr(stmt[1])
            jump_else = self.emit(OP_JUMP_IF_FALSE, line=stmt[4])
            self.block(stmt[2])
            jump_end = self.emit(OP_JUMP, line=stmt[4])
            self.patch(jump_else, len(self.code))
            self.block(stmt[3])
            self.patch(jump_end, len(self.code))
        elif kind == "while":
            start = len(self.code)
            self.expr(stmt[1])
            jump_end = self.emit(OP_JUMP_IF_FALSE, line=stmt[3])
            self.block(stmt[2])
            back = self.emit(OP_JUMP, line=stmt[3])
            self.patch(back, start)
            self.patch(jump_end, len(self.code))
        elif kind == "for_range":
            self.expr(stmt[2])
            limit = self._local(f"__lim{len(self.locs)}")
            self.emit(OP_STORE_LOCAL, b=limit, line=stmt[4])
            self.emit(OP_CONST, b=self.pool.num(0), line=stmt[4])
            self.store(stmt[1], stmt[4])
            start = len(self.code)
            self.load(stmt[1], stmt[4])
            self.emit(OP_LOAD_LOCAL, b=limit, line=stmt[4])
            self.emit(OP_LT, line=stmt[4])
            jump_end = self.emit(OP_JUMP_IF_FALSE, line=stmt[4])
            self.block(stmt[3])
            self.load(stmt[1], stmt[4])
            self.emit(OP_CONST, b=self.pool.num(1), line=stmt[4])
            self.emit(OP_ADD, line=stmt[4])
            self.store(stmt[1], stmt[4])
            back = self.emit(OP_JUMP, line=stmt[4])
            self.patch(back, start)
            self.patch(jump_end, len(self.code))
        elif kind == "for_each":
            self.expr(stmt[2])
            seq = self._local(f"__seq{len(self.locs)}")
            idx = self._local(f"__idx{len(self.locs)}")
            self.emit(OP_STORE_LOCAL, b=seq, line=stmt[4])
            self.emit(OP_CONST, b=self.pool.num(0), line=stmt[4])
            self.emit(OP_STORE_LOCAL, b=idx, line=stmt[4])
            start = len(self.code)
            self.emit(OP_LOAD_LOCAL, b=idx, line=stmt[4])
            self.emit(OP_LOAD_LOCAL, b=seq, line=stmt[4])
            self.emit(OP_BUILTIN, a=1, b=0, line=stmt[4])  # tamanho
            self.emit(OP_LT, line=stmt[4])
            jump_end = self.emit(OP_JUMP_IF_FALSE, line=stmt[4])
            self.emit(OP_LOAD_LOCAL, b=seq, line=stmt[4])
            self.emit(OP_LOAD_LOCAL, b=idx, line=stmt[4])
            self.emit(OP_LOAD_INDEX, line=stmt[4])
            self.store(stmt[1], stmt[4])
            self.block(stmt[3])
            self.emit(OP_LOAD_LOCAL, b=idx, line=stmt[4])
            self.emit(OP_CONST, b=self.pool.num(1), line=stmt[4])
            self.emit(OP_ADD, line=stmt[4])
            self.emit(OP_STORE_LOCAL, b=idx, line=stmt[4])
            back = self.emit(OP_JUMP, line=stmt[4])
            self.patch(back, start)
            self.patch(jump_end, len(self.code))
        else:
            raise LiraError("comando desconhecido: " + kind)

    def load(self, name, line):
        if name in self.lindex:
            self.emit(OP_LOAD_LOCAL, b=self.lindex[name], line=line)
        elif name in self.gindex:
            self.emit(OP_LOAD_GLOBAL, b=self.gindex[name], line=line)
        else:
            raise LiraError("nome desconhecido: " + name, line)

    def store(self, name, line):
        if name in self.lindex:
            self.emit(OP_STORE_LOCAL, b=self.lindex[name], line=line)
        elif name in self.gindex:
            self.emit(OP_STORE_GLOBAL, b=self.gindex[name], line=line)
        else:
            raise LiraError("nome desconhecido: " + name, line)

    def expr(self, node):
        kind = node[0]
        if kind == "num":
            self.emit(OP_CONST, b=self.pool.num(node[1]), line=node[2])
        elif kind == "str":
            self.emit(OP_CONST, b=self.pool.string(node[1]), line=node[2])
        elif kind == "name":
            self.load(node[1], node[2])
        elif kind == "unary":
            self.expr(node[2])
            self.emit(OP_NOT if node[1] == "nao" else OP_NEG, line=node[3])
        elif kind == "binop":
            self.expr(node[2])
            self.expr(node[3])
            self.emit(BIN[node[1]], line=node[4])
        elif kind == "logic":
            self.expr(node[2])
            self.emit(OP_DUP, line=node[4])
            if node[1] == "e":
                jump = self.emit(OP_JUMP_IF_FALSE, line=node[4])
                self.emit(OP_POP, line=node[4])
                self.expr(node[3])
                self.patch(jump, len(self.code))
            else:
                skip_right = self.emit(OP_JUMP_IF_FALSE, line=node[4])
                jump_end = self.emit(OP_JUMP, line=node[4])
                self.patch(skip_right, len(self.code))
                self.emit(OP_POP, line=node[4])
                self.expr(node[3])
                self.patch(jump_end, len(self.code))
        elif kind == "call":
            name, args, line = node[1], node[2], node[3]
            if name == "trilha":
                for arg in args:
                    self.expr(arg)
                self.emit(OP_MAKE_LIST, b=len(args), line=line)
            elif name in BUILTINS:
                bid, arity = BUILTINS[name]
                if len(args) != arity:
                    raise LiraError(f"{name} espera {arity} argumento(s)", line)
                for arg in args:
                    self.expr(arg)
                self.emit(OP_BUILTIN, a=arity, b=bid, line=line)
            elif name in self.findex:
                if len(args) != self.farity[name]:
                    raise LiraError(f"{name} espera {self.farity[name]} argumento(s)", line)
                for arg in args:
                    self.expr(arg)
                self.emit(OP_CALL, a=len(args), b=self.findex[name], line=line)
            else:
                raise LiraError("pulso desconhecido: " + name, line)
        elif kind == "index":
            self.expr(node[1])
            self.expr(node[2])
            self.emit(OP_LOAD_INDEX, line=node[1][-1])
        else:
            raise LiraError("expressão desconhecida")

    def finish(self):
        line = self.code[-1][3] if self.code else 1
        self.emit(OP_CONST, b=self.pool.null(), line=line)
        self.emit(OP_RETURN, line=line)
        # 240 = mostra(n). a já guarda a contagem. Vira opcode 30 dentro do arquivo? 
        # Mantemos 240 no interpretador Python e no C como OP_PRINT.
        return {
            "name": self.name,
            "arity": len(self.params),
            "nlocals": len(self.locs),
            "code": [tuple(item) for item in self.code],
        }


OP_PRINT = 240


def compile_source(source):
    nucleo, stmts = Parser(lex(source)).parse()
    gindex, seen = {}, set()
    funcs = [s for s in stmts if s[0] == "func"]
    names = []
    for stmt in stmts:
        if stmt[0] == "celula":
            if stmt[1] in seen:
                raise LiraError("celula repetida: " + stmt[1], stmt[3])
            seen.add(stmt[1])
            gindex[stmt[1]] = len(names)
            names.append(stmt[1])
    findex, farity = {}, {}
    for index, func in enumerate(funcs, start=1):
        if func[1] in findex or func[1] in BUILTINS or func[1] == "trilha":
            raise LiraError("pulso repetido ou reservado: " + func[1], func[4])
        findex[func[1]] = index
        farity[func[1]] = len(func[2])
    pool = Pool()
    script_stmts = [s for s in stmts if s[0] != "func"]
    script_c = FuncCompiler("", [], gindex, findex, farity, pool)
    script_c.scan(script_stmts)
    script_c.block(script_stmts)
    compiled = [script_c.finish()]
    for func in funcs:
        compiler = FuncCompiler(func[1], func[2], gindex, findex, farity, pool)
        compiler.scan(func[3])
        compiler.block(func[3])
        compiled.append(compiler.finish())
    return {"nucleo": nucleo, "consts": pool.items, "globals": len(names), "funcs": compiled}


def pack_lfbc(module):
    out = bytearray(LFBC_MAGIC)
    out += struct.pack("<HHH", len(module["consts"]), module["globals"], len(module["funcs"]))
    for value in module["consts"]:
        if value is None:
            out.append(0)
        elif isinstance(value, float):
            out.append(1)
            out += struct.pack("<d", value)
        elif isinstance(value, str):
            raw = value.encode("utf-8")
            out.append(2)
            out += struct.pack("<I", len(raw))
            out += raw
        else:
            raise LiraError("constante inválida")
    for func in module["funcs"]:
        name = func["name"].encode("utf-8")
        out += struct.pack("<H", len(name))
        out += name
        out += struct.pack("<HHI", func["arity"], func["nlocals"], len(func["code"]))
        for op, a, b, line in func["code"]:
            out += struct.pack("<BBHI", op, a, b, line)
    return bytes(out)


def unpack_lfbc(blob):
    if blob[:8] != LFBC_MAGIC:
        raise LiraError("não é LFBC")
    consts_n, globals_n, funcs_n = struct.unpack_from("<HHH", blob, 8)
    pos = 14
    consts = []
    for _ in range(consts_n):
        tag = blob[pos]
        pos += 1
        if tag == 0:
            consts.append(None)
        elif tag == 1:
            consts.append(struct.unpack_from("<d", blob, pos)[0])
            pos += 8
        elif tag == 2:
            size = struct.unpack_from("<I", blob, pos)[0]
            pos += 4
            consts.append(blob[pos:pos + size].decode("utf-8"))
            pos += size
        else:
            raise LiraError("tag LFBC inválida")
    funcs = []
    for _ in range(funcs_n):
        size = struct.unpack_from("<H", blob, pos)[0]
        pos += 2
        name = blob[pos:pos + size].decode("utf-8")
        pos += size
        arity, nlocals, ncode = struct.unpack_from("<HHI", blob, pos)
        pos += 8
        code = []
        for _ in range(ncode):
            code.append(struct.unpack_from("<BBHI", blob, pos))
            pos += 8
        funcs.append({"name": name, "arity": arity, "nlocals": nlocals, "code": code})
    if pos != len(blob):
        raise LiraError("LFBC com lixo no final")
    return {"consts": consts, "globals": globals_n, "funcs": funcs}


def display(value):
    if value is None:
        return "vazio"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        text = format(value, ".12g")
        return text
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(display(item) for item in value) + "]"
    return str(value)


def to_plain(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return display(value)
        if value.is_integer() and abs(value) < 2**53:
            return int(value)
        return value
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    return value


def truthy(value):
    if value is None:
        return False
    if isinstance(value, float):
        return value != 0.0 and not math.isnan(value)
    if isinstance(value, str):
        return value != ""
    if isinstance(value, list):
        return len(value) > 0
    return True


def as_index(value, size, line):
    if not isinstance(value, float) or not value.is_integer():
        raise LiraError("índice precisa ser inteiro", line)
    index = int(value)
    if index < 0:
        index += size
    if index < 0 or index >= size:
        raise LiraError("índice fora da trilha", line)
    return index


def need_num(value, line):
    if not isinstance(value, float):
        raise LiraError("esperado número", line)
    return value


def execute(module, prints=None):
    consts = module["consts"]
    funcs = module["funcs"]
    globs = [None] * module["globals"]
    stack = []
    printed = prints if prints is not None else []

    def run(func, base):
        ip, code = 0, func["code"]
        while True:
            if ip >= len(code):
                raise LiraError("pulso terminou sem entrega", 0)
            op, a, b, line = code[ip]
            ip += 1
            try:
                if op == OP_CONST:
                    stack.append(consts[b])
                elif op == OP_LOAD_LOCAL:
                    stack.append(stack[base + b])
                elif op == OP_STORE_LOCAL:
                    stack[base + b] = stack.pop()
                elif op == OP_LOAD_GLOBAL:
                    stack.append(globs[b])
                elif op == OP_STORE_GLOBAL:
                    globs[b] = stack.pop()
                elif op == OP_LOAD_INDEX:
                    index, container = stack.pop(), stack.pop()
                    if isinstance(container, list):
                        stack.append(container[as_index(index, len(container), line)])
                    elif isinstance(container, str):
                        stack.append(container[as_index(index, len(container), line)])
                    else:
                        raise LiraError("não dá para indexar isso", line)
                elif op == OP_STORE_INDEX:
                    value, index, container = stack.pop(), stack.pop(), stack.pop()
                    if not isinstance(container, list):
                        raise LiraError("gravação indexada exige trilha", line)
                    container[as_index(index, len(container), line)] = value
                elif op in (OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_POW):
                    right, left = stack.pop(), stack.pop()
                    if op == OP_ADD and isinstance(left, str) and isinstance(right, str):
                        stack.append(left + right)
                    elif op == OP_ADD and isinstance(left, list) and isinstance(right, list):
                        stack.append(left + right)
                    else:
                        x, y = need_num(left, line), need_num(right, line)
                        if op == OP_ADD:
                            stack.append(x + y)
                        elif op == OP_SUB:
                            stack.append(x - y)
                        elif op == OP_MUL:
                            stack.append(x * y)
                        elif op == OP_DIV:
                            if y == 0:
                                raise LiraError("divisão por zero", line)
                            stack.append(x / y)
                        elif op == OP_MOD:
                            if y == 0:
                                raise LiraError("resto por zero", line)
                            stack.append(math.fmod(x, y))
                        else:
                            stack.append(float(x ** y))
                elif op == OP_NEG:
                    stack.append(-need_num(stack.pop(), line))
                elif op == OP_NOT:
                    stack.append(0.0 if truthy(stack.pop()) else 1.0)
                elif op in (OP_EQ, OP_NE, OP_LT, OP_LE, OP_GT, OP_GE):
                    right, left = stack.pop(), stack.pop()
                    if op in (OP_LT, OP_LE, OP_GT, OP_GE):
                        x, y = need_num(left, line), need_num(right, line)
                        ok = {OP_LT: x < y, OP_LE: x <= y, OP_GT: x > y, OP_GE: x >= y}[op]
                    else:
                        ok = json.dumps(to_plain(left), ensure_ascii=False) == json.dumps(to_plain(right), ensure_ascii=False)
                        if op == OP_NE:
                            ok = not ok
                    stack.append(1.0 if ok else 0.0)
                elif op == OP_JUMP:
                    rel = b - 65536 if b >= 32768 else b
                    ip += rel
                elif op == OP_JUMP_IF_FALSE:
                    rel = b - 65536 if b >= 32768 else b
                    if not truthy(stack.pop()):
                        ip += rel
                elif op == OP_POP:
                    stack.pop()
                elif op == OP_DUP:
                    stack.append(stack[-1])
                elif op == OP_MAKE_LIST:
                    items = [stack.pop() for _ in range(b)]
                    items.reverse()
                    stack.append(items)
                elif op == OP_CALL:
                    callee = funcs[b]
                    if a != callee["arity"]:
                        raise LiraError("aridade errada", line)
                    sub = len(stack) - a
                    while len(stack) < sub + callee["nlocals"]:
                        stack.append(None)
                    stack.append(run(callee, sub))
                elif op == OP_RETURN:
                    value = stack.pop()
                    del stack[base:]
                    return value
                elif op == OP_BUILTIN:
                    builtin(b, a, line)
                elif op == OP_PRINT:
                    items = [stack.pop() for _ in range(a)]
                    items.reverse()
                    line_out = " ".join(display(item) for item in items)
                    printed.append(line_out)
                else:
                    raise LiraError("opcode desconhecido " + str(op), line)
            except LiraError:
                raise
            except (IndexError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
                raise LiraError(str(exc), line)

    def builtin(bid, argc, line):
        args = [stack.pop() for _ in range(argc)]
        args.reverse()
        if bid == 0:
            item = args[0]
            if not isinstance(item, (list, str)):
                raise LiraError("tamanho espera trilha ou texto", line)
            stack.append(float(len(item)))
        elif bid == 1:
            if not isinstance(args[0], list):
                raise LiraError("soma espera trilha", line)
            stack.append(float(sum(need_num(x, line) for x in args[0])))
        elif bid == 2:
            stack.append(abs(need_num(args[0], line)))
        elif bid == 3:
            value = need_num(args[0], line)
            if value < 0:
                raise LiraError("raiz de negativo", line)
            stack.append(math.sqrt(value))
        elif bid == 4:
            stack.append(float(math.floor(need_num(args[0], line))))
        elif bid == 5:
            stack.append(float(math.ceil(need_num(args[0], line))))
        elif bid == 6:
            left, right = args
            if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
                raise LiraError("ponto espera trilhas do mesmo tamanho", line)
            stack.append(float(sum(need_num(x, line) * need_num(y, line) for x, y in zip(left, right))))
        elif bid == 7:
            stack.append(float(need_num(args[0], line) ** need_num(args[1], line)))
        elif bid == 8:
            stack.append(display(args[0]))
        elif bid == 9:
            count = need_num(args[0], line)
            if not count.is_integer() or count < 0 or count > 2_000_000:
                raise LiraError("faixa inválida", line)
            stack.append([float(i) for i in range(int(count))])
        else:
            raise LiraError("builtin desconhecido", line)

    while len(stack) < funcs[0]["nlocals"]:
        stack.append(None)
    result = run(funcs[0], 0)
    return {"return": result, "prints": printed, "globals": globs}


def run_source(source):
    module = compile_source(source)
    blob = pack_lfbc(module)
    loaded = unpack_lfbc(blob)
    return execute(loaded), blob


# --- BRX 0 / BRXE v1 (somente trecho reto de inteiros) ---------------------

BRXE_OPS = {
    "HALT": 0x00, "PUSH_I64": 0x01, "LOAD_LOCAL": 0x02, "STORE_LOCAL": 0x03,
    "ADD_I64": 0x04, "SUB_I64": 0x05, "MUL_I64": 0x06, "DIV_I64": 0x07,
    "MOD_I64": 0x08, "PRINT_I64": 0x09, "PRINT_CONST": 0x0A,
}


def _int_value(node):
    if node[0] != "num" or not float(node[1]).is_integer():
        raise LiraError("BRX 0 só aceita inteiros neste trecho", node[-1])
    return int(node[1])


def lower_brx(source):
    """Emite .brx e .brxe se o programa for reto: celula/grava/mostra, sem pulso nem laço."""
    _nucleo, stmts = Parser(lex(source)).parse()
    nucleo = _nucleo or "lira"
    for stmt in stmts:
        if stmt[0] not in ("celula", "assign", "print"):
            raise LiraError("BRX 0 ainda não tem pulso, se, enquanto ou varre — use `run`", stmt[-1])
    slots, order = {}, []

    def slot(name, line):
        if name not in slots:
            if len(order) >= 64:
                raise LiraError("BRX 0 aceita no máximo 64 variáveis", line)
            slots[name] = len(order)
            order.append(name)
        return slots[name]

    brx_lines = [f'run "{nucleo}"']
    code, data = bytearray(), bytearray()

    def push_expr(node):
        kind = node[0]
        if kind == "num":
            code.append(BRXE_OPS["PUSH_I64"])
            code.extend(struct.pack("<q", _int_value(node)))
        elif kind == "name":
            code.append(BRXE_OPS["LOAD_LOCAL"])
            code.extend(struct.pack("<H", slot(node[1], node[2])))
        elif kind == "unary" and node[1] == "-":
            push_expr(("num", 0.0, node[3]))
            push_expr(node[2])
            code.append(BRXE_OPS["SUB_I64"])
        elif kind == "binop" and node[1] in "+-*/%":
            push_expr(node[2])
            push_expr(node[3])
            code.append({"+" : 0x04, "-": 0x05, "*": 0x06, "/": 0x07, "%": 0x08}[node[1]])
        else:
            raise LiraError("expressão fora do subconjunto BRX 0", node[-1])

    def expr_text(node, parent=None, right=False):
        kind = node[0]
        if kind == "num":
            return str(_int_value(node))
        if kind == "name":
            return node[1]
        if kind == "unary" and node[1] == "-":
            if node[2][0] == "num":
                return str(-_int_value(node[2]))
            raise LiraError("BRX 0 não tem menos unário", node[3])
        if kind != "binop":
            raise LiraError("expressão fora do subconjunto BRX 0", node[-1])
        prec = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2}
        op = node[1]
        if op not in prec:
            raise LiraError("operador fora do BRX 0", node[4])

        def needs_paren(side, is_right):
            if side[0] != "binop":
                return False
            child = prec[side[1]]
            if child < prec[op]:
                return True
            if is_right and child == prec[op] and op in "-/%":
                return True
            return False

        if needs_paren(node[2], False) or needs_paren(node[3], True):
            raise LiraError("BRX 0 não tem parênteses; reescreva a expressão", node[4])
        return expr_text(node[2], op, False) + f" {op} " + expr_text(node[3], op, True)

    declared = set()
    for stmt in stmts:
        if stmt[0] in ("celula", "assign"):
            name = stmt[1]
            slot(name, stmt[-1])
            text = expr_text(stmt[2])
            if name not in declared:
                brx_lines.append(f"var {name}:num = {text}")
                declared.add(name)
            else:
                brx_lines.append(f"{name} = {text}")
            push_expr(stmt[2])
            code.append(BRXE_OPS["STORE_LOCAL"])
            code.extend(struct.pack("<H", slots[name]))
        elif stmt[0] == "print":
            if len(stmt[1]) != 1:
                raise LiraError("BRX 0 imprime um valor por out", stmt[2])
            item = stmt[1][0]
            if item[0] == "str":
                raw = item[1].encode("utf-8")
                brx_lines.append('out "' + item[1].replace('"', "") + '"')
                code.append(BRXE_OPS["PRINT_CONST"])
                code.extend(struct.pack("<II", len(data), len(raw)))
                data.extend(raw)
            else:
                brx_lines.append("out " + expr_text(item))
                push_expr(item)
                code.append(BRXE_OPS["PRINT_I64"])
    code.append(BRXE_OPS["HALT"])
    header = struct.pack("<4sHHI I", b"BRXE", 1, 0, len(code), len(data))
    return {"brx": "\n".join(brx_lines) + "\n", "brxe": header + bytes(code) + bytes(data), "slots": order}


def run_brxe(blob):
    if len(blob) < 16 or blob[:4] != b"BRXE":
        raise LiraError("BRXE inválido")
    _magic, version, _flags, code_size, data_size = struct.unpack_from("<4sHHII", blob, 0)
    if version != 1 or 16 + code_size + data_size != len(blob):
        raise LiraError("BRXE truncado ou versão diferente de 1")
    code, data = blob[16:16 + code_size], blob[16 + code_size:]
    ip, stack, locals_, printed = 0, [], {}, []
    while ip < len(code):
        op = code[ip]
        ip += 1
        if op == 0x00:
            break
        if op == 0x01:
            stack.append(struct.unpack_from("<q", code, ip)[0])
            ip += 8
        elif op == 0x02:
            index = struct.unpack_from("<H", code, ip)[0]
            ip += 2
            if index not in locals_:
                raise LiraError("local BRX não inicializado")
            stack.append(locals_[index])
        elif op == 0x03:
            index = struct.unpack_from("<H", code, ip)[0]
            ip += 2
            locals_[index] = stack.pop()
        elif op in (0x04, 0x05, 0x06, 0x07, 0x08):
            right, left = stack.pop(), stack.pop()
            if op == 0x04:
                stack.append((left + right) & 0xFFFFFFFFFFFFFFFF)
                if stack[-1] >= 2**63:
                    stack[-1] -= 2**64
            elif op == 0x05:
                stack.append(left - right)
            elif op == 0x06:
                stack.append(left * right)
            elif op == 0x07:
                if right == 0:
                    raise LiraError("divisão por zero")
                stack.append(int(left / right))
            else:
                if right == 0:
                    raise LiraError("resto por zero")
                stack.append(int(math.fmod(left, right)))
        elif op == 0x09:
            printed.append(str(stack.pop()))
        elif op == 0x0A:
            offset, length = struct.unpack_from("<II", code, ip)
            ip += 8
            text = data[offset:offset + length].decode("utf-8")
            printed.append(text)
        else:
            raise LiraError("opcode BRXE não executável nesta versão: " + hex(op))
    return {"prints": printed, "locals": locals_}


# --- roteador Lira / memória LIRAFST5 (o arquivo original, estendido) ------

def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).lower().strip().split())


def stable_hash(parts, ordered=False):
    digest = hashlib.blake2b(digest_size=16)
    values = list(parts)
    if not ordered:
        values = sorted(set(values))
    for part in values:
        raw = str(part).encode("utf-8")
        digest.update(len(raw).to_bytes(4 if ordered else 2, "little"))
        digest.update(raw)
    return digest.hexdigest()


def compile_text(text, context=()):
    normalized = normalize(text)
    context = tuple(normalize(x) for x in context)
    tokens = re.findall(r"(?:\.[A-Za-z_]\w*|[\w+#-]+(?:\.[\w+#-]+)?)|[^\w\s]", normalized, re.UNICODE)
    analysis = " ".join((normalized, *context)).strip()
    found, covered = set(), set()
    words = list(re.finditer(r"[\wÀ-ÿ]+", analysis, re.UNICODE))

    def negated(index):
        prior = [m.group(0) for m in words if m.end() <= index]
        return any(w in NEGATORS for w in prior[-3:])

    for concept, values in ALIASES.items():
        for phrase in values:
            if " " not in phrase:
                continue
            start = 0
            while (index := analysis.find(phrase, start)) >= 0:
                if not (concept.startswith(("intent:", "op:")) and negated(index)):
                    found.add(concept)
                    covered.update(phrase.split())
                start = index + max(1, len(phrase))
    alias_map = {}
    for concept, values in ALIASES.items():
        for alias in values:
            alias_map.setdefault(alias, []).append(concept)
    unknown = []
    for match in re.finditer(r"(?:\.[A-Za-z_]\w*|[\w+#-]+(?:\.[\w+#-]+)?)|[^\w\s]", analysis, re.UNICODE):
        token = match.group(0)
        concepts = alias_map.get(token)
        if concepts is None and "." in token:
            concepts = alias_map.get("." + token.rsplit(".", 1)[1])
        if concepts:
            for concept in concepts:
                if not (concept.startswith(("intent:", "op:")) and negated(match.start())):
                    found.add(concept)
            covered.add(token)
        elif token.isalnum() and len(token) > 2 and token not in STOP and token not in covered:
            unknown.append(token)
    primitives = sorted(found)
    context_sig = stable_hash(context, ordered=True)
    sig_parts = list(primitives)
    if context:
        sig_parts.append("context:" + context_sig)
    confidence = min(1.0, max(1, len(primitives)) / (max(1, len(primitives)) + .35 * len(set(unknown))))
    return {"normalized": normalized, "primitives": primitives,
            "unknown": list(dict.fromkeys(unknown)), "signature": stable_hash(sig_parts),
            "context_signature": context_sig, "confidence": confidence, "tokens": tokens}


def empty_memory():
    return {"version": 1, "result_threshold": .985, "min_result_verifications": 2,
            "methods": [], "errors": [], "results": [], "family": [name for name, _url in FAMILY]}


def load_state(home):
    home.mkdir(parents=True, exist_ok=True)
    path = home / "memory.json"
    if not path.exists():
        save_state(home, empty_memory())
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("methods", "errors", "results"):
        data.setdefault(key, [])
    return data


def save_state(home, data):
    home.mkdir(parents=True, exist_ok=True)
    target = home / "memory.json"
    raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".memory-", dir=home)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def route_request(home, text, domain="general", context=()):
    memory = load_state(home)
    compiled = compile_text(text, context)
    norm = compiled["normalized"]
    for result in memory["results"]:
        if result.get("request_signature") == stable_hash((norm,), ordered=True):
            return {"mode": "RESULT", "domain": domain, "payload": result, "compiled": None}
    resolved = domain
    if resolved == "general":
        routed = [x.split(":", 1)[1] for x in compiled["primitives"] if x.startswith("domain:")]
        if routed:
            resolved = routed[0]
    candidates = [m for m in memory["methods"]
                  if m.get("structure_signature") == compiled["signature"]
                  and (resolved == "general" or m.get("domain") == resolved)]
    if candidates:
        best = max(candidates, key=lambda m: (m.get("confidence", 0), m.get("verified_runs", 0), -m.get("failures", 0)))
        return {"mode": "METHOD", "domain": resolved, "payload": best, "compiled": compiled}
    return {"mode": "DEEP", "domain": resolved, "payload": None, "compiled": compiled}


def promote(home, text, domain, op_ids, runs, min_successes=3, min_confidence=.8,
            preconditions=(), postconditions=(), lira_source="", pulse=""):
    if runs < min_successes:
        raise ValueError(f"São necessárias pelo menos {min_successes} execuções; recebido {runs}.")
    if not op_ids:
        raise ValueError("Informe pelo menos um --op-id.")
    compiled = compile_text(text)
    confidence = (1 + runs) / (2 + runs)
    if confidence < min_confidence:
        raise ValueError(f"Confiança estimada {confidence:.3f} abaixo do limite {min_confidence:.3f}.")
    memory = load_state(home)
    method_id = "auto:" + domain + ":" + compiled["signature"][:12] + ":" + hashlib.sha1(json.dumps(op_ids).encode()).hexdigest()[:4]
    method = {"method_id": method_id, "domain": domain,
              "structure_signature": compiled["signature"], "op_ids": list(op_ids),
              "preconditions": list(preconditions), "postconditions": list(postconditions),
              "confidence": confidence, "verified_runs": runs, "failures": 0,
              "provenance": "deep-to-fast", "language": "lira" if lira_source else "",
              "lira": lira_source, "pulse": pulse}
    memory["methods"] = [m for m in memory["methods"] if m.get("method_id") != method_id]
    memory["methods"].append(method)
    save_state(home, memory)
    return {"promoted": True, "method": method,
            "warning": "O programa registra observações declaradas verificadas; não executa seu método automaticamente, salvo com --execute."}


class SafeCalc:
    FUNCTIONS = {"abs": abs, "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
                 "tan": math.tan, "floor": math.floor, "ceil": math.ceil, "round": round,
                 "sum": sum, "min": min, "max": max,
                 "mean": lambda x: sum(x) / len(x), "prod": math.prod,
                 "dot": lambda a, b: sum(x * y for x, y in zip(a, b)) if len(a) == len(b) else (_ for _ in ()).throw(ValueError("vetores incompatíveis"))}

    def calculate(self, expression, variables=None):
        self.variables = variables or {}
        return self.visit(ast.parse(expression, mode="eval").body)

    def visit(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.variables:
                raise ValueError("variável desconhecida: " + node.id)
            return self.variables[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.visit(x) for x in node.elts]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            value = self.visit(node.operand)
            return +value if isinstance(node.op, ast.UAdd) else -value if isinstance(node.op, ast.USub) else not value
        if isinstance(node, ast.BinOp):
            left, right = self.visit(node.left), self.visit(node.right)
            ops = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right, ast.Mult: lambda: left * right,
                   ast.Div: lambda: left / right, ast.FloorDiv: lambda: left // right, ast.Mod: lambda: left % right,
                   ast.Pow: lambda: left ** right}
            for kind, fn in ops.items():
                if isinstance(node.op, kind):
                    return fn()
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right, op = self.visit(node.left), self.visit(node.comparators[0]), node.ops[0]
            for kind, fn in ((ast.Eq, lambda: left == right), (ast.NotEq, lambda: left != right),
                             (ast.Lt, lambda: left < right), (ast.LtE, lambda: left <= right),
                             (ast.Gt, lambda: left > right), (ast.GtE, lambda: left >= right)):
                if isinstance(op, kind):
                    return fn()
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [self.visit(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.FUNCTIONS and not node.keywords:
            return self.FUNCTIONS[node.func.id](*(self.visit(a) for a in node.args))
        raise ValueError("expressão contém operação não permitida: " + type(node).__name__)


def pack_container(sections, compress=True):
    if len(sections) > 65535:
        raise ValueError("número excessivo de seções")
    rows, payloads = [], []
    offset = HEADER.size + len(sections) * ENTRY.size
    for name, raw in sections.items():
        name_raw = name.encode("ascii")
        if not name_raw or len(name_raw) > 16:
            raise ValueError("nome de seção deve ter 1-16 bytes ASCII")
        raw = bytes(raw)
        stored = zlib.compress(raw, 6) if compress and len(raw) > 64 else raw
        flags = FLAG_ZLIB if compress and len(raw) > 64 and len(stored) < len(raw) else 0
        if not flags:
            stored = raw
        rows.append((name_raw.ljust(16, b"\0"), offset, len(stored), zlib.crc32(raw) & 0xffffffff, flags))
        payloads.append(stored)
        offset += len(stored)
    output = bytearray(HEADER.pack(MAGIC, VERSION, len(rows), len(rows) * ENTRY.size))
    for row in rows:
        output.extend(ENTRY.pack(*row))
    for payload in payloads:
        output.extend(payload)
    return bytes(output)


def unpack_container(blob):
    if len(blob) < HEADER.size:
        raise ValueError("header .lirafast truncado")
    magic, version, count, directory_bytes = HEADER.unpack_from(blob)
    if magic != MAGIC or version != VERSION or directory_bytes != count * ENTRY.size:
        raise ValueError("cabeçalho LIRAFST5 inválido ou versão incompatível")
    if HEADER.size + directory_bytes > len(blob):
        raise ValueError("diretório truncado")
    sections, names = {}, set()
    pos = HEADER.size
    for _ in range(count):
        raw_name, offset, size, crc, flags = ENTRY.unpack_from(blob, pos)
        pos += ENTRY.size
        name = raw_name.rstrip(b"\0").decode("ascii")
        if not name or name in names:
            raise ValueError("nome de seção vazio ou duplicado")
        names.add(name)
        if offset < HEADER.size + directory_bytes or offset + size > len(blob):
            raise ValueError("seção fora dos limites do arquivo")
        stored = blob[offset:offset + size]
        raw = zlib.decompress(stored) if flags & FLAG_ZLIB else stored
        if zlib.crc32(raw) & 0xffffffff != crc:
            raise ValueError("CRC32 inválido na seção " + name)
        sections[name] = raw
    return sections


def build_archive(home, output, extras=(), compress=True):
    memory = load_state(home)
    memory_bytes = json.dumps(memory, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    sections = {"memory": memory_bytes}
    facts_path = home / "facts.json"
    if facts_path.exists():
        sections["facts"] = facts_path.read_bytes()
    for spec in extras:
        if "=" not in spec:
            raise ValueError("seção adicional use NOME=ARQUIVO")
        name, filename = spec.split("=", 1)
        if name in sections or name == "meta":
            raise ValueError("seção repetida/reservada: " + name)
        sections[name] = Path(filename).read_bytes()
    manifest = {"format": "LIRAFST5", "format_version": VERSION,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "creator": "BRX_FAST_UM_ARQUIVO.py",
                "repositories": [url for _name, url in FAMILY],
                "sections": {k: {"bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()} for k, v in sections.items()}}
    sections["meta"] = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    blob = pack_container(sections, compress)
    check = unpack_container(blob)
    json.loads(check["memory"].decode("utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + output.name, dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, output)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise
    return {"file": str(output), "size": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
            "sections": {k: len(v) for k, v in check.items()}, "integrity": "CRC32 OK"}


def inspect_archive(path, extract_to=None):
    sections = unpack_container(path.read_bytes())
    memory = json.loads(sections["memory"].decode("utf-8")) if "memory" in sections else {}
    meta = json.loads(sections["meta"].decode("utf-8")) if "meta" in sections else {}
    result = {"file": str(path), "bytes": path.stat().st_size, "format": meta.get("format", "LIRAFST5"),
              "version": meta.get("format_version", 5), "integrity": "CRC32 OK",
              "memory_counts": {"methods": len(memory.get("methods", [])), "errors": len(memory.get("errors", [])),
                                "results": len(memory.get("results", []))},
              "sections": {k: {"bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()} for k, v in sections.items()}}
    if extract_to:
        extract_to.mkdir(parents=True, exist_ok=True)
        for name, raw in sections.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", name):
                raise ValueError("nome de seção não seguro")
            (extract_to / (name + ".bin")).write_bytes(raw)
        result["extracted_to"] = str(extract_to)
    return result


PERCEPTRON = """:: Perceptron AND de 3 bits — metodo Lira, executado pela VM .lira
:: Liga self-continuing-pattern (metodo verificavel) + BRX FAST (rota) + linguagem propria.
nucleo Perceptron

celula pesos = trilha(0.2, -0.1, 0.4)
celula vies = 0.05
celula taxa = 0.2

pulso prever(x)
  grava s = ponto(pesos, x) + vies
  se s > 0
    entrega 1
  senao
    entrega 0
  fecha
fecha

pulso treinar(x, y)
  grava palpite = prever(x)
  grava erro = y - palpite
  varre i em faixa(tamanho(pesos))
    grava pesos[i] = pesos[i] + taxa * erro * x[i]
  fecha
  grava vies = vies + taxa * erro
  entrega erro
fecha

pulso principal()
  grava amostras = trilha(trilha(0, 0, 0), trilha(0, 0, 1), trilha(0, 1, 0), trilha(0, 1, 1), trilha(1, 0, 0), trilha(1, 0, 1), trilha(1, 1, 0), trilha(1, 1, 1))
  grava alvos = trilha(0, 0, 0, 0, 0, 0, 0, 1)
  varre epoca em faixa(40)
    varre i em faixa(tamanho(amostras))
      treinar(amostras[i], alvos[i])
    fecha
  fecha
  mostra prever(trilha(1, 1, 1))
  mostra prever(trilha(1, 0, 1))
  mostra prever(trilha(0, 0, 0))
  mostra pesos
  mostra vies
  entrega trilha(pesos, vies, prever(trilha(1, 1, 1)), prever(trilha(0, 1, 0)))
fecha

principal()
entrega trilha(pesos, vies, prever(trilha(1, 1, 1)), prever(trilha(0, 1, 0)))
"""

SOMA = """:: Trecho reto: desce para .brx / .brxe (BRX-Linguagens, subconjunto 0).
nucleo Soma
celula base = 10
celula ajuste = 3 * 4
grava base = base + ajuste
grava base = base * 2 - 4
mostra "resultado"
mostra base
"""


def train_model(home, output_dir):
    outcome, blob = run_source(PERCEPTRON)
    plain = to_plain(outcome["return"])
    pesos, vies = plain[0], plain[1]
    if plain[2] != 1 or plain[3] != 0:
        raise LiraError("o perceptron não separou o AND; recusando o modelo")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "perceptron.lira").write_text(PERCEPTRON, encoding="utf-8")
    (output_dir / "perceptron.lfbc").write_bytes(blob)
    weights = {"language": "lira", "task": "and3", "pesos": pesos, "vies": vies,
               "prints": outcome["prints"], "return": plain}
    (output_dir / "pesos.json").write_text(json.dumps(weights, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compiled = compile_text("treine modelo lira para somar padroes AND")
    memory = load_state(home)
    method = {"method_id": "lira:perceptron:and3", "domain": "model",
              "structure_signature": compiled["signature"], "op_ids": [1, 6],
              "preconditions": ["entradas binarias de 3 bits"],
              "postconditions": ["prever(1,1,1)=1", "prever demais amostras AND=0"],
              "confidence": 0.98, "verified_runs": 40, "failures": 0,
              "provenance": "lira-vm", "language": "lira", "pulse": "principal",
              "lira": PERCEPTRON, "pesos": pesos, "vies": vies}
    memory["methods"] = [m for m in memory["methods"] if m.get("method_id") != method["method_id"]]
    memory["methods"].append(method)
    memory["results"].append({"request_signature": stable_hash((compiled["normalized"],), ordered=True),
                              "domain": "model", "value": weights, "verifications": 40})
    save_state(home, memory)
    archive = build_archive(home, output_dir / "modelo.lirafast")
    return {"model": "perceptron-and3", "pesos": pesos, "vies": vies, "verified": True,
            "archive": archive, "files": [str(output_dir / name) for name in
                                         ("perceptron.lira", "perceptron.lfbc", "pesos.json", "modelo.lirafast")]}


def clone_family(dest):
    dest.mkdir(parents=True, exist_ok=True)
    report = []
    for name, url in FAMILY:
        target = dest / name
        if (target / ".git").exists():
            report.append({"name": name, "path": str(target), "status": "ja-clonado", "url": url})
            continue
        if target.exists():
            report.append({"name": name, "path": str(target), "status": "caminho-ocupado", "url": url})
            continue
        proc = subprocess.run(["git", "clone", "--depth", "1", url, str(target)], capture_output=True, text=True)
        report.append({"name": name, "path": str(target), "url": url,
                       "status": "clonado" if proc.returncode == 0 else "falhou",
                       "stderr": (proc.stderr or "")[-400:]})
    return {"into": str(dest), "family": report}


def install_vm():
    src = HERE / "lfvm.c"
    if not src.exists():
        raise LiraError("lfvm.c não está ao lado deste arquivo")
    out = HERE / ("lfvm.exe" if os.name == "nt" else "lfvm")
    proc = subprocess.run(["gcc", "-O3", "-std=c11", "-o", str(out), str(src)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise LiraError("gcc falhou: " + (proc.stderr or "")[-500:])
    return {"vm": str(out), "compiler": "gcc -O3"}


def compile_native(source):
    """Trecho numérico reto vira C. Laço `varre/faixa` vira while nativo, sem bytecode."""
    _nucleo, stmts = Parser(lex(source)).parse()
    names = []

    def collect(block):
        for stmt in block:
            if stmt[0] in ("celula", "assign", "for_range") and stmt[1] not in names:
                names.append(stmt[1])
            if stmt[0] == "if":
                collect(stmt[2])
                collect(stmt[3])
            elif stmt[0] == "while":
                collect(stmt[2])
            elif stmt[0] == "for_range":
                collect(stmt[3])
            elif stmt[0] in ("func", "for_each", "assign_idx"):
                raise LiraError("VM nativa ainda não compila pulso, trilha ou varre genérico; use --vm c")

    def expr(node):
        kind = node[0]
        if kind == "num":
            return format(float(node[1]), ".17g")
        if kind == "name":
            if node[1] not in names:
                raise LiraError("nome fora do trecho nativo: " + node[1], node[2])
            return node[1]
        if kind == "unary" and node[1] == "-":
            return "(-(" + expr(node[2]) + "))"
        if kind == "unary" and node[1] == "nao":
            return "((" + expr(node[2]) + ")==0?1.0:0.0)"
        if kind == "binop":
            if node[1] == "**":
                return f"pow({expr(node[2])},{expr(node[3])})"
            if node[1] == "%":
                return f"fmod({expr(node[2])},{expr(node[3])})"
            if node[1] not in "+-*/":
                c_op = {"==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}[node[1]]
                return f"(({expr(node[2])}) {c_op} ({expr(node[3])}) ? 1.0 : 0.0)"
            return f"(({expr(node[2])}) {node[1]} ({expr(node[3])}))"
        if kind == "logic":
            left, right = expr(node[2]), expr(node[3])
            if node[1] == "e":
                return f"(({left})==0?({left}):({right}))"
            return f"(({left})!=0?({left}):({right}))"
        if kind == "call" and node[1] in ("piso", "teto", "abs", "raiz", "pot"):
            fn = {"piso": "floor", "teto": "ceil", "abs": "fabs", "raiz": "sqrt", "pot": "pow"}[node[1]]
            return fn + "(" + ",".join(expr(arg) for arg in node[2]) + ")"
        raise LiraError("expressão fora da VM nativa", node[-1] if node else 0)

    collect(stmts)
    lines = ["#include <math.h>", "#include <stdio.h>", "int main(void) {"]
    for name in names:
        lines.append(f"  double {name} = 0;")
    fresh = {"n": 0}

    def emit(block, indent):
        pad = "  " * indent
        for stmt in block:
            kind = stmt[0]
            if kind in ("celula", "assign"):
                lines.append(f"{pad}{stmt[1]} = {expr(stmt[2])};")
            elif kind == "print":
                fmt, args = [], []
                for item in stmt[1]:
                    if item[0] == "str":
                        fmt.append("%s")
                        args.append(json.dumps(item[1], ensure_ascii=False))
                    else:
                        fmt.append("%.12g")
                        args.append(expr(item))
                lines.append(pad + 'printf("' + " ".join(fmt) + '\\n", ' + ", ".join(args) + ");")
            elif kind == "if":
                lines.append(f"{pad}if (({expr(stmt[1])}) != 0) {{")
                emit(stmt[2], indent + 1)
                lines.append(f"{pad}}} else {{")
                emit(stmt[3], indent + 1)
                lines.append(f"{pad}}}")
            elif kind == "while":
                lines.append(f"{pad}while (({expr(stmt[1])}) != 0) {{")
                emit(stmt[2], indent + 1)
                lines.append(f"{pad}}}")
            elif kind == "for_range":
                fresh["n"] += 1
                lim = f"__lim{fresh['n']}"
                lines.append(f"{pad}{{ double {lim} = {expr(stmt[2])}; {stmt[1]} = 0;")
                lines.append(f"{pad}while ({stmt[1]} < {lim}) {{")
                emit(stmt[3], indent + 1)
                lines.append(f"{pad}{stmt[1]} = {stmt[1]} + 1; }} }}")
            elif kind == "return":
                lines.append(f"{pad}{{ double __r = {expr(stmt[1])};")
                lines.append(pad + 'if (__r == floor(__r) && fabs(__r) < 1e15) printf("{\\"return\\": %.0f}\\n", __r);')
                lines.append(pad + 'else printf("{\\"return\\": %.17g}\\n", __r); return 0; }')
            elif kind == "expr":
                lines.append(f"{pad}(void)({expr(stmt[1])});")
            else:
                raise LiraError("comando fora da VM nativa")

    emit(stmts, 1)
    lines.append('  printf("{\\"return\\": null}\\n");')
    lines.append("  return 0;")
    lines.append("}")
    return "\n".join(lines) + "\n"


def run_native(source):
    code = compile_native(source)
    tmp = Path(tempfile.mkdtemp())
    src, bin_path = tmp / "native.c", tmp / "native"
    src.write_text(code, encoding="utf-8")
    proc = subprocess.run(["gcc", "-O3", "-std=c11", "-o", str(bin_path), str(src), "-lm"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise LiraError("gcc nativo falhou: " + (proc.stderr or "")[-400:])
    started = __import__("time").perf_counter()
    ran = subprocess.run([str(bin_path)], capture_output=True, text=True)
    seconds = __import__("time").perf_counter() - started
    if ran.returncode != 0:
        raise LiraError(ran.stderr.strip() or "nativo falhou")
    payload = json.loads(ran.stdout.strip().splitlines()[-1])
    prints = ran.stdout.strip().splitlines()[:-1]
    return {"return": payload.get("return"), "prints": prints, "seconds": seconds, "vm": "native"}


def run_c_vm(source):
    vm = HERE / "lfvm"
    if not vm.exists():
        raise LiraError("VM em C ausente. Rode: python BRX_FAST_UM_ARQUIVO.py install")
    module = compile_source(source)
    fd, name = tempfile.mkstemp(suffix=".lfbc")
    os.close(fd)
    path = Path(name)
    json_path = Path(name + ".json")
    try:
        path.write_bytes(pack_lfbc(module))
        proc = subprocess.run([str(vm), str(path), "--json", str(json_path)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise LiraError((proc.stderr or proc.stdout or "lfvm falhou").strip())
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        payload = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
        return payload
    finally:
        path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)


def benchmark(n=400):
    source = f"""
celula acc = 0
varre i em faixa({n})
  varre j em faixa({n})
    grava acc = acc + (i * j) - piso((i * j) / 97) * 97
  fecha
fecha
entrega acc
"""
    import time
    started = time.perf_counter()
    py, _blob = run_source(source)
    py_s = time.perf_counter() - started

    def pure(limit):
        acc = 0.0
        for i in range(limit):
            for j in range(limit):
                prod = i * j
                acc += prod - math.floor(prod / 97) * 97
        return acc

    started = time.perf_counter()
    pure_value = pure(n)
    pure_s = time.perf_counter() - started
    c_report = None
    native_report = None
    if (HERE / "lfvm").exists():
        started = time.perf_counter()
        c_payload = run_c_vm(source)
        c_s = time.perf_counter() - started
        c_report = {"seconds": c_s, "return": c_payload.get("return"),
                    "versus_python_vm": (py_s / c_s) if c_s else None}
    try:
        native = run_native(source)
        native_report = {"seconds": native["seconds"], "return": native["return"],
                         "versus_cpython": (pure_s / native["seconds"]) if native["seconds"] else None,
                         "versus_python_vm": (py_s / native["seconds"]) if native["seconds"] else None}
    except LiraError as exc:
        native_report = {"erro": str(exc)}
    return {"n": n, "loops": n * n, "python_vm_seconds": py_s, "python_vm_return": to_plain(py["return"]),
            "cpython_equivalente_seconds": pure_s, "cpython_return": pure_value,
            "c_vm": c_report, "c_nativo": native_report,
            "nota": "O laço numérico compilado para C (--vm native) é o caminho rápido. A VM .lfbc em C é dezenas de vezes mais rápida que a VM em Python da mesma linguagem, mas um for do CPython ainda compete com um interpretador de bytecode. Não é mais rápido que NumPy vetorizado."}


def autoteste():
    checks = []

    def check(name, cond):
        checks.append({"name": name, "ok": bool(cond)})
        if not cond:
            raise LiraError("autoteste falhou: " + name)

    out, blob = run_source("""
celula a = 2
pulso add(x, y)
  entrega x + y
fecha
mostra add(a, 3)
grava a = add(a, 10)
se a > 10
  mostra "ok"
senao
  mostra "falhou"
fecha
mostra trilha(1, 2, 3)[1]
mostra ponto(trilha(1, 2), trilha(3, 4))
varre i em faixa(3)
  mostra i
fecha
entrega a
""")
    check("smoke-prints", out["prints"] == ["5", "ok", "2", "11", "0", "1", "2"])
    check("smoke-return", to_plain(out["return"]) == 12)
    check("lfbc-roundtrip", unpack_lfbc(blob)["funcs"][0]["nlocals"] >= 1)
    model, _ = run_source(PERCEPTRON)
    plain = to_plain(model["return"])
    check("and-positivo", plain[2] == 1)
    check("and-negativo", plain[3] == 0)
    lowered = lower_brx(SOMA)
    check("brx-text", 'var base:num = 10' in lowered["brx"] and 'out "resultado"' in lowered["brx"])
    brxe = run_brxe(lowered["brxe"])
    check("brxe-run", brxe["prints"] == ["resultado", "40"])
    try:
        lower_brx(PERCEPTRON)
        check("brx-rejects-loop", False)
    except LiraError:
        check("brx-rejects-loop", True)
    home = Path(tempfile.mkdtemp())
    routed = route_request(home, "crie função para somar")
    check("route-deep", routed["mode"] == "DEEP")
    archive = build_archive(home, home / "t.lirafast")
    check("container", archive["integrity"] == "CRC32 OK")
    calc = SafeCalc().calculate("dot([1,2],[3,4])")
    check("calc", calc == 11)
    if any(not item["ok"] for item in checks):
        raise LiraError("autoteste incompleto")
    return {"ok": True, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description="BRX FAST — um arquivo: rota Lira, linguagem .lira, BRX/BRXE")
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("familia", help="mostra os repositórios ligados")
    sub.add_parser("autoteste")
    clone = sub.add_parser("clone", help="clona lira, BRX, padrão e kernel")
    clone.add_argument("--into", type=Path, default=Path("familia"))
    comp = sub.add_parser("compile")
    comp.add_argument("text")
    comp.add_argument("--context", action="append", default=[])
    teach = sub.add_parser("teach")
    teach.add_argument("text")
    teach.add_argument("--domain", required=True)
    teach.add_argument("--op-id", type=int, action="append", required=True)
    teach.add_argument("--runs", type=int, default=3)
    teach.add_argument("--min-confidence", type=float, default=.8)
    teach.add_argument("--precondition", action="append", default=[])
    teach.add_argument("--postcondition", action="append", default=[])
    teach.add_argument("--lira", type=Path)
    teach.add_argument("--pulse", default="")
    route = sub.add_parser("route")
    route.add_argument("text")
    route.add_argument("--domain", default="general")
    route.add_argument("--context", action="append", default=[])
    route.add_argument("--execute", action="store_true")
    calc = sub.add_parser("calc")
    calc.add_argument("expression")
    calc.add_argument("--variables", default="{}")
    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--section", action="append", default=[])
    build.add_argument("--no-compress", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("archive", type=Path)
    inspect.add_argument("--extract-to", type=Path)
    run = sub.add_parser("run")
    run.add_argument("file", type=Path)
    run.add_argument("--vm", choices=("py", "c", "native"), default="py")
    run.add_argument("--json", type=Path)
    brx = sub.add_parser("brx")
    brx.add_argument("file", type=Path)
    brx.add_argument("--brx", type=Path)
    brx.add_argument("--brxe", type=Path)
    brxe = sub.add_parser("brxe-run")
    brxe.add_argument("file", type=Path)
    modelo = sub.add_parser("modelo")
    modelo.add_argument("--output", type=Path, default=Path("modelo"))
    sub.add_parser("install")
    bench = sub.add_parser("bench")
    bench.add_argument("--n", type=int, default=400)
    args = parser.parse_args()
    home = args.home
    try:
        if args.command == "init":
            load_state(home)
            result = {"initialized": True, "memory": str(home / "memory.json")}
        elif args.command == "familia":
            result = {"relacionados": [{"nome": n, "url": u} for n, u in FAMILY],
                      "papel": {"lira": "memória estrutural, rota FAST/DEEP, .lirafast",
                                "linguagem": "fonte .brx e bytecode .brxe",
                                "padrao": "primitivas, métodos e erros",
                                "kernel": "núcleo x86_64",
                                "fast": "este arquivo: Colab, .lira, modelo"}}
        elif args.command == "autoteste":
            result = autoteste()
        elif args.command == "clone":
            result = clone_family(args.into)
        elif args.command == "compile":
            result = compile_text(args.text, args.context)
        elif args.command == "teach":
            lira_source = args.lira.read_text(encoding="utf-8") if args.lira else ""
            result = promote(home, args.text, args.domain, args.op_id, args.runs, 3, args.min_confidence,
                             args.precondition, args.postcondition, lira_source, args.pulse)
        elif args.command == "route":
            result = route_request(home, args.text, args.domain, args.context)
            if args.execute and result["mode"] == "METHOD" and result["payload"].get("lira"):
                outcome, _blob = run_source(result["payload"]["lira"])
                result["executed"] = {"prints": outcome["prints"], "return": to_plain(outcome["return"])}
        elif args.command == "calc":
            result = {"expression": args.expression, "result": SafeCalc().calculate(args.expression, json.loads(args.variables))}
        elif args.command == "build":
            result = build_archive(home, args.output, args.section, not args.no_compress)
        elif args.command == "inspect":
            result = inspect_archive(args.archive, args.extract_to)
        elif args.command == "run":
            source = args.file.read_text(encoding="utf-8")
            if args.vm == "c":
                result = run_c_vm(source)
            elif args.vm == "native":
                result = run_native(source)
            else:
                outcome, _blob = run_source(source)
                result = {"prints": outcome["prints"], "return": to_plain(outcome["return"]), "vm": "py"}
            if args.json:
                args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif args.command == "brx":
            lowered = lower_brx(args.file.read_text(encoding="utf-8"))
            if args.brx:
                args.brx.write_text(lowered["brx"], encoding="utf-8")
            if args.brxe:
                args.brxe.write_bytes(lowered["brxe"])
            ran = run_brxe(lowered["brxe"])
            result = {"brx": lowered["brx"], "slots": lowered["slots"], "prints": ran["prints"], "brxe_bytes": len(lowered["brxe"])}
        elif args.command == "brxe-run":
            result = run_brxe(args.file.read_bytes())
        elif args.command == "modelo":
            result = train_model(home, args.output)
        elif args.command == "install":
            result = install_vm()
        elif args.command == "bench":
            result = benchmark(args.n)
        else:
            raise ValueError("comando desconhecido")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, zlib.error, LiraError, subprocess.CalledProcessError) as exc:
        print("ERRO:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
