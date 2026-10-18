# FAST

Código único da família **BRX / Lira**. Um arquivo Python entra no Google Colab, clona os repositórios irmãos, roda a linguagem **`.lira`** e grava um modelo verificado.

`brx-fast` como nome de repositório não existe. A entrada é esta: [dragonolouco/FAST](https://github.com/dragonolouco/FAST).

## Como as peças se ligam

| Repositório | Papel |
|---|---|
| [self-continuing-pattern](https://github.com/dragonolouco/self-continuing-pattern) | Tese: primitiva, estado, método, erro, verificação |
| [lirafast](https://github.com/dragonolouco/lirafast) | Rota FAST / DEEP, memória estrutural, contêiner `.lirafast` |
| [BRX-Linguagens](https://github.com/dragonolouco/BRX-Linguagens) | Linguagem `.brx` e bytecode `.brxe` (assembly, sem libc) |
| [brx-kernel](https://github.com/dragonolouco/brx-kernel) | Núcleo x86_64 próprio |
| [FAST](https://github.com/dragonolouco/FAST) | Este arquivo: Colab, `.lira`, modelo, emissor BRX 0 |

`.lira` não é Python, JavaScript nem C com outro nome. O texto do programa usa `nucleo`, `celula`, `pulso`, `grava`, `varre`, `entrega`. O laço numérico pode ser compilado para C (`--vm native`). O trecho reto de inteiros desce para `.brx` / `.brxe`, o subconjunto que `brx0` / `brxvm0` já executam. Laço e `pulso` ainda não existem no BRX 0 — a spec de BRX-Linguagens diz isso, e o emissor recusa esse caso em vez de fingir.

## Colab

```python
!git clone --depth 1 https://github.com/dragonolouco/FAST.git
%cd FAST
!python BRX_FAST_UM_ARQUIVO.py autoteste
!python BRX_FAST_UM_ARQUIVO.py modelo --output modelo
!python BRX_FAST_UM_ARQUIVO.py install
!python BRX_FAST_UM_ARQUIVO.py bench --n 800
!python BRX_FAST_UM_ARQUIVO.py clone --into familia
!python BRX_FAST_UM_ARQUIVO.py brx exemplos/soma.lira --brx soma.brx --brxe soma.brxe
```

O notebook está em [`colab/LiraFast.ipynb`](colab/LiraFast.ipynb).

`modelo` treina um perceptron AND de 3 bits **escrito em `.lira`**, confere `prever(1,1,1) = 1` e o resto `0`, e grava `modelo/modelo.lirafast` (LIRAFST5, CRC32) com o método promovido.

## Velocidade, sem slogan

No mesmo laço numérico (medido neste ambiente, 360 mil voltas):

- VM `.lira` em Python: baseline
- VM `.lfbc` em C (`lfvm`): cerca de **45×** a VM Python da própria linguagem
- `--vm native` (gcc -O3): cerca de **20×** o `for` equivalente do CPython e cerca de **1600×** a VM Python

Isso não é mais rápido que C escrito à mão nem que NumPy vetorizado. O número muda com a máquina. `bench` mede de novo aí.

## Comandos

```bash
python BRX_FAST_UM_ARQUIVO.py familia
python BRX_FAST_UM_ARQUIVO.py run exemplos/perceptron.lira
python BRX_FAST_UM_ARQUIVO.py run exemplos/perceptron.lira --vm c
python BRX_FAST_UM_ARQUIVO.py compile "crie função lira para somar"
python BRX_FAST_UM_ARQUIVO.py route "crie função lira para somar"
python BRX_FAST_UM_ARQUIVO.py calc "dot([1,2],[3,4])"
```

Gramática em [LINGUAGEM.md](LINGUAGEM.md).
