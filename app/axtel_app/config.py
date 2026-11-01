"""Configurações do Axtel (dados/config.json). Tudo tem um valor padrão."""
import copy
import json
import os
import threading

PADRAO = {
    "portas": {"f1": 20777, "forza": 5300},
    "iniciar_com_windows": False,
    "atalhos": False,
    "backup": {"ativo": True, "manter": 14},
    "spotter": {
        "ligado": True, "modo": "normal", "volume": 80, "ritmo": 105, "lingua": "auto", "reserva": True,
        "retas": True, "freada": True, "prioridade": True, "intervalo": 4, "saida": "ambos", "desligados": [],
        "vozes": {
            "pt": {"nome": "Beto", "id": "xNGAXaCH8MaasNuo7Hr7"},
            "en": {"nome": "", "id": ""},  # ainda não escolhida
            "es": {"nome": "", "id": ""},  # ainda não escolhida
        },
    },
}


def _misturar(base, novo):
    for k, v in novo.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _misturar(base[k], v)
        else:
            base[k] = v
    return base


class Config:
    def __init__(self, pasta):
        self.caminho = os.path.join(pasta, "config.json")
        self.trava = threading.Lock()
        self.dados = copy.deepcopy(PADRAO)
        try:
            with open(self.caminho, encoding="utf-8") as f:
                _misturar(self.dados, json.load(f))
        except (OSError, ValueError):
            pass

    def __getitem__(self, k):
        return self.dados[k]

    def tudo(self):
        with self.trava:
            return copy.deepcopy(self.dados)

    def atualizar(self, novo):
        with self.trava:
            _misturar(self.dados, novo)
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.caminho)
            return copy.deepcopy(self.dados)
