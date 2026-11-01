# Testes do Axtel

| Arquivo | O que faz | Precisa de |
|---|---|---|
| `test_basico.py` | Testes rápidos: fechamento de voltas (inclusive o repique do AC/ACC), leitores, ajuste de telemetria do iRacing e do F1 25. | Só Python |
| `simulador.py` | Imita a telemetria dos 7 jogos (memória compartilhada e UDP) e roda o Axtel de verdade. | Só Python |
| `validar.py` | Validação completa: simulação dos jogos + roteiro clicando em cada botão (PC e celular) + gremlins.js (cliques aleatórios) + varredura de todos os controles. Gera `relatorio/index.html` com prints. | Playwright |

```powershell
python -m unittest discover -s testes -v
pip install playwright
python -m playwright install chromium
python testes\validar.py
```

Os dados de teste ficam em `testes/.dados-teste`, separados dos seus.
