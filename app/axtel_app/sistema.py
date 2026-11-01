"""Abrir junto com o Windows e backup automático do banco."""
import logging
import os
import sys
import threading
import time
from datetime import datetime

log = logging.getLogger("axtel")
NOME_ATALHO = "Axtel.bat"


def pasta_inicializar():
    appdata = os.environ.get("APPDATA")
    if sys.platform != "win32" or not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def iniciar_com_windows(ativar, pasta_app):
    """Cria ou remove o atalho na pasta Inicializar do Windows. Devolve (ok, mensagem)."""
    pasta = pasta_inicializar()
    if not pasta:
        return False, "Só funciona no Windows."
    arq = os.path.join(pasta, NOME_ATALHO)
    try:
        if ativar:
            with open(arq, "w", encoding="ascii", errors="ignore", newline="\r\n") as f:
                f.write("@echo off\n")
                f.write(f'cd /d "{pasta_app}"\n')
                f.write('where py >nul 2>nul && (start "Axtel" /min py axtel.py --sem-navegador) || '
                        '(start "Axtel" /min python axtel.py --sem-navegador)\n')
            return True, "O Axtel vai abrir sozinho quando o Windows ligar."
        if os.path.exists(arq):
            os.remove(arq)
        return True, "O Axtel não abre mais sozinho com o Windows."
    except OSError as e:
        return False, f"Não consegui mexer na pasta Inicializar: {e}"


def esta_no_inicializar():
    pasta = pasta_inicializar()
    return bool(pasta and os.path.exists(os.path.join(pasta, NOME_ATALHO)))


def listar_backups(pasta_dados):
    pasta = os.path.join(pasta_dados, "backups")
    if not os.path.isdir(pasta):
        return []
    itens = []
    for f in sorted(os.listdir(pasta), reverse=True):
        if f.startswith("axtel-") and f.endswith(".db"):
            caminho = os.path.join(pasta, f)
            itens.append({"arquivo": f, "caminho": caminho, "tamanho_kb": round(os.path.getsize(caminho) / 1024),
                          "quando": datetime.fromtimestamp(os.path.getmtime(caminho)).isoformat(timespec="minutes")})
    return itens


class Backups(threading.Thread):
    """Faz um backup por dia enquanto o Axtel estiver aberto."""

    def __init__(self, banco, pasta_dados, config):
        super().__init__(daemon=True, name="backup")
        self.banco, self.pasta, self.config = banco, pasta_dados, config

    def agora(self):
        destino = self.banco.backup(os.path.join(self.pasta, "backups"), self.config["backup"]["manter"])
        log.info("backup salvo: %s", destino)
        return destino

    def run(self):
        time.sleep(20)
        while True:
            try:
                if self.config["backup"]["ativo"]:
                    feitos = listar_backups(self.pasta)
                    hoje = "axtel-" + datetime.now().strftime("%Y-%m-%d") + ".db"
                    if not feitos or feitos[0]["arquivo"] != hoje:
                        self.agora()
            except Exception:
                log.exception("backup automático falhou")
            time.sleep(3600)


class AtalhosGlobais(threading.Thread):
    """F9 repete o último aviso, F10 silencia por 1 volta e Ctrl+F10 liga/desliga o spotter, mesmo com o jogo na frente."""
    TECLAS = {1: (0, 0x78, "repetir"), 2: (0, 0x79, "silenciar"), 3: (0x0002, 0x79, "alternar")}  # 0x78 = F9, 0x79 = F10

    def __init__(self, coletor):
        super().__init__(daemon=True, name="atalhos")
        self.coletor = coletor

    def run(self):
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        registradas = []
        for ident, (mod, vk, acao) in self.TECLAS.items():
            if u32.RegisterHotKey(None, ident, mod | 0x4000, vk):  # 0x4000 = não repetir enquanto segura
                registradas.append(acao)
            else:
                self.coletor.alerta("aviso", f"O atalho do spotter para '{acao}' já está em uso por outro programa.")
        log.info("atalhos do spotter ativos: %s", ", ".join(registradas) or "nenhum")
        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam in self.TECLAS:  # WM_HOTKEY
                self.coletor._evento("comando", acao=self.TECLAS[msg.wParam][2])
