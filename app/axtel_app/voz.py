"""Voz do spotter pelo ElevenLabs.

A chave fica só no PC, na variável de ambiente ELEVENLABS_API_KEY (nunca no código).
Cada frase gerada fica guardada em dados/voz/<idioma>/ e toca de graça na próxima vez.
Sem chave, sem internet ou sem créditos, o painel usa a voz do navegador.
"""
import hashlib
import json
import logging
import os
import sys
import threading
import urllib.error
import urllib.request

log = logging.getLogger("axtel")
URL = "https://api.elevenlabs.io/v1/text-to-speech/{voz}?output_format=mp3_44100_128"
MODELO = "eleven_multilingual_v2"


def ler_chave():
    chave = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if chave or sys.platform != "win32":
        return chave
    try:  # setx grava no registro; um Axtel aberto antes do setx ainda não vê a variável
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, "ELEVENLABS_API_KEY")[0]).strip()
    except OSError:
        return ""


class Voz:
    def __init__(self, pasta_dados, config):
        self.pasta = os.path.join(pasta_dados, "voz")
        self.config = config
        self.trava = threading.Lock()
        self.ultimo_erro = ""
        self.gerados = 0

    def _voz_id(self, lingua):
        vozes = self.config["spotter"]["vozes"]
        return (vozes.get(lingua) or {}).get("id", "").strip()

    def caminho(self, lingua, chave):
        return os.path.join(self.pasta, lingua, chave + ".mp3")

    def estado(self):
        total = 0
        if os.path.isdir(self.pasta):
            for raiz, _, arqs in os.walk(self.pasta):
                total += sum(1 for a in arqs if a.endswith(".mp3"))
        return {"chave": bool(ler_chave()), "ultimo_erro": self.ultimo_erro, "guardadas": total, "geradas_agora": self.gerados}

    def falar(self, texto, lingua):
        """Devolve (lingua, chave_do_arquivo) ou (None, mensagem de erro)."""
        texto = (texto or "").strip()[:400]
        lingua = lingua if lingua in ("pt", "en", "es") else "pt"
        if not texto:
            return None, "Frase vazia."
        voz = self._voz_id(lingua)
        if not voz:
            return None, "A voz do ElevenLabs deste idioma ainda não foi escolhida."
        chave_arq = hashlib.sha1(f"{voz}|{MODELO}|{texto}".encode("utf-8")).hexdigest()[:24]
        destino = self.caminho(lingua, chave_arq)
        if os.path.exists(destino):
            return lingua, chave_arq
        api = ler_chave()
        if not api:
            return None, "Sem a chave do ElevenLabs neste PC."
        corpo = json.dumps({"text": texto, "model_id": MODELO,
                            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25,
                                               "use_speaker_boost": True}}).encode("utf-8")
        req = urllib.request.Request(URL.format(voz=voz), data=corpo, method="POST",
                                     headers={"xi-api-key": api, "Content-Type": "application/json",
                                              "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                audio = r.read()
        except urllib.error.HTTPError as e:
            msg = {401: "A chave do ElevenLabs foi recusada.", 402: "Sem créditos no ElevenLabs.",
                   429: "O ElevenLabs pediu para esperar (limite de uso)."}.get(e.code, f"ElevenLabs respondeu {e.code}.")
            self.ultimo_erro = msg
            log.warning("voz: %s", msg)
            return None, msg
        except Exception as e:  # sem internet, tempo esgotado…
            self.ultimo_erro = "Sem conexão com o ElevenLabs."
            log.warning("voz: %s", e)
            return None, self.ultimo_erro
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        tmp = destino + ".tmp"
        with open(tmp, "wb") as f:
            f.write(audio)
        os.replace(tmp, destino)
        self.ultimo_erro = ""
        self.gerados += 1
        return lingua, chave_arq
