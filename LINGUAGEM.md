# .lira — Lira Fast 0

Linguagem de método da família BRX. Não reutiliza a sintaxe de Python, C ou JavaScript. O arquivo é `nome.lira`. Comentário começa com `::`.

```lira
nucleo Exemplo
celula base = 10

pulso dobro(n)
  entrega n * 2
fecha

varre i em faixa(3)
  mostra dobro(i)
fecha
```

## Palavras

| Palavra | Função |
|---|---|
| `nucleo` | Nome do programa. Vira `run "..."` no `.brx` |
| `celula` | Estado global. Só no topo |
| `pulso` / `fecha` | Procedimento e fim de bloco |
| `grava` | Escrita. `grava a[i] = ...` mexe numa trilha |
| `se` / `senao` / `fecha` | Condicional. Zero, texto vazio e trilha vazia são falso |
| `enquanto` | Laço por condição |
| `varre x em faixa(n)` | Laço contado, sem montar a lista |
| `varre x em trilha` | Percorre uma trilha |
| `entrega` | Devolve e sai do pulso (ou do programa, no topo) |
| `mostra` | Imprime, itens separados por vírgula |
| `sim` / `falso` | 1 e 0 |
| `nao` `e` `ou` | Lógica. `e` / `ou` devolvem o próprio valor, em curto-circuito |

Números são reais. `trilha(1, 2)` monta uma lista. Índice negativo conta do fim.

## Embutidos

`tamanho` `soma` `abs` `raiz` `piso` `teto` `ponto` `pot` `texto` `faixa`

`ponto(a, b)` é o produto interno. O perceptron de `exemplos/perceptron.lira` usa isso.

## Três modos de rodar

1. `--vm py` — interpretador no próprio `BRX_FAST_UM_ARQUIVO.py` (só biblioteca padrão).
2. `--vm c` — o mesmo bytecode `.lfbc` na `lfvm` (`install` chama gcc -O3).
3. `--vm native` — trecho numérico sem `pulso` compilado para C. É o caminho rápido do `bench`.

## Descida para BRX

`brx exemplos/soma.lira` emite `.brx` e `.brxe` v1 (`BRXE`, opcodes de `HALT` até `PRINT_CONST`). Só entra o que BRX 0 realmente executa: inteiros, `+ - * / %`, `var` e `out`. `pulso`, `se` e `varre` produzem erro — esses comandos ainda estão na lista de “próximas partes” da especificação em BRX-Linguagens.
