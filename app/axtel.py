"""Axtel — telemetria de simuladores.

Uso:  python axtel.py            (abre o painel no navegador)
      python axtel.py --porta 8600 --sem-navegador
"""
import argparse
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from axtel_app.banco import Banco  # noqa: E402
from axtel_app.coletor import Coletor  # noqa: E402
from axtel_app.config import Config  # noqa: E402
from axtel_app.servidor import VERSAO, Api, criar_servidor, ip_local  # noqa: E402
from axtel_app.sistema import AtalhosGlobais, Backups  # noqa: E402
from axtel_app.voz import Voz  # noqa: E402


def porta_ocupada(porta):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def main():
    # Aberto pelo Axtel.exe (pythonw), não há janela: as mensagens vão só para o log.
    if sys.stdout is None or sys.stderr is None:
        sys.stdout = sys.stderr = open(os.devnull, "w")
    ap = argparse.ArgumentParser(description="Axtel — telemetria de simuladores")
    ap.add_argument("--porta", type=int, default=8501)
    ap.add_argument("--dados", default=os.path.join(AQUI, "dados"))
    ap.add_argument("--sem-navegador", action="store_true")
    a = ap.parse_args()

    if sys.version_info < (3, 9):
        print("O Axtel precisa do Python 3.9 ou mais novo.")
        sys.exit(1)
    if sys.platform != "win32":
        print("Aviso: a leitura dos jogos só funciona no Windows. O painel abre normalmente.")

    endereco = f"http://localhost:{a.porta}"
    if porta_ocupada(a.porta):
        print(f"O Axtel já está aberto. Abrindo {endereco}")
        if not a.sem_navegador:
            webbrowser.open(endereco)
        return

    os.makedirs(a.dados, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(os.path.join(a.dados, "axtel.log"), maxBytes=2_000_000,
                                                      backupCount=2, encoding="utf-8")])
    logging.getLogger("axtel").info("Axtel %s iniciando", VERSAO)

    config = Config(a.dados)
    banco = Banco(os.path.join(a.dados, "axtel.db"))
    coletor = Coletor(banco, a.dados, config)
    coletor.start()
    backups = Backups(banco, a.dados, config)
    backups.start()
    if config["atalhos"]:
        AtalhosGlobais(coletor).start()
    api = Api(banco, coletor, a.porta, config=config, voz=Voz(a.dados, config), backups=backups,
              pasta_app=AQUI, pasta_dados=a.dados)
    srv = criar_servidor(api, os.path.join(AQUI, "painel"), a.porta)
    api.desligar = lambda: threading.Thread(target=srv.shutdown, daemon=True).start()

    print("=" * 60)
    print(f"  AXTEL {VERSAO} rodando")
    print(f"  Painel neste PC:   {endereco}")
    print(f"  Painel no celular: http://{ip_local()}:{a.porta}  (mesmo Wi-Fi)")
    print("  Para fechar: feche esta janela ou aperte Ctrl+C")
    print("=" * 60)
    if not a.sem_navegador:
        threading.Timer(1.0, lambda: webbrowser.open(endereco)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        coletor.parar.set()
        coletor.join(timeout=3)
        srv.server_close()
        print("Axtel fechado. Sessão salva.")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
