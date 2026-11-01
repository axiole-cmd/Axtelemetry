"""Telemetria de cada jogo: o que precisa estar ligado, se o Axtel está recebendo,
e ajuste automático dos arquivos de configuração quando o jogo permite.

Só mexemos em arquivos de configuração conhecidos e sempre guardamos uma cópia
(.axtel-bak) antes de alterar.
"""
import ctypes
import os
import re
import shutil
import subprocess
import sys
import time


def pasta_documentos():
    if sys.platform == "win32":
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return buf.value
    return os.path.join(os.path.expanduser("~"), "Documents")


def processos():
    if sys.platform != "win32":
        return set()
    try:
        saida = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                               timeout=8, creationflags=0x08000000).stdout
        return {linha.split('","')[0].strip('"').lower() for linha in saida.splitlines() if linha}
    except Exception:
        return set()


def _copia(arq):
    bak = arq + ".axtel-bak"
    if not os.path.exists(bak):
        shutil.copy2(arq, bak)


# ---------------------------------------------------------------- iRacing (app.ini)
def _iracing_ini():
    return os.path.join(pasta_documentos(), "iRacing", "app.ini")


def _iracing_estado():
    arq = _iracing_ini()
    if not os.path.exists(arq):
        return {"arquivo": arq, "existe": False}
    txt = open(arq, encoding="latin-1").read()
    m = re.search(r"^\s*irsdkEnableMem\s*=\s*(\d+)", txt, re.M)
    return {"arquivo": arq, "existe": True, "ok": (m is None or m.group(1) != "0"), "valor": m.group(1) if m else "padrão (ligado)"}


def _iracing_ajustar(portas):
    e = _iracing_estado()
    if not e["existe"]:
        return False, "Não achei o app.ini do iRacing. Abra o iRacing uma vez e tente de novo."
    if e["ok"]:
        return True, "A telemetria do iRacing já está ligada (irsdkEnableMem)."
    arq = e["arquivo"]
    _copia(arq)
    txt = open(arq, encoding="latin-1").read()
    txt = re.sub(r"^(\s*irsdkEnableMem\s*=\s*)\d+", r"\g<1>1", txt, flags=re.M)
    open(arq, "w", encoding="latin-1").write(txt)
    return True, "Pronto: telemetria do iRacing ligada. Reinicie o iRacing."


# ---------------------------------------------------------------- F1 25 (hardware_settings_config.xml)
def _f1_xml():
    return os.path.join(pasta_documentos(), "My Games", "F1 25", "hardwaresettings", "hardware_settings_config.xml")


def _f1_estado(portas):
    arq = _f1_xml()
    if not os.path.exists(arq):
        return {"arquivo": arq, "existe": False}
    txt = open(arq, encoding="utf-8", errors="ignore").read()
    m = re.search(r"<udp\b[^>]*>", txt)
    if not m:
        return {"arquivo": arq, "existe": True, "ok": None}
    tag = m.group(0)
    at = dict(re.findall(r'(\w+)="([^"]*)"', tag))
    porta = str(portas.get("f1", 20777))
    ok = at.get("enabled") == "true" and at.get("port", porta) == porta and at.get("broadcast", "false") == "false"
    return {"arquivo": arq, "existe": True, "ok": ok, "atual": at}


def _f1_ajustar(portas):
    if "f1_25.exe" in processos():
        return False, "Feche o F1 25 antes: o jogo regrava esse arquivo quando fecha."
    e = _f1_estado(portas)
    if not e["existe"]:
        return False, "Não achei a configuração do F1 25. Abra o jogo uma vez, feche e tente de novo, ou ligue pelo menu do jogo."
    if e.get("ok") is None:
        return False, "O arquivo do F1 25 não tem a parte de telemetria. Ligue pelo menu do jogo (passos abaixo)."
    arq = e["arquivo"]
    _copia(arq)
    txt = open(arq, encoding="utf-8", errors="ignore").read()
    novos = {"enabled": "true", "broadcast": "false", "ip": "127.0.0.1", "port": str(portas.get("f1", 20777)),
             "sendRate": "60", "format": "2025"}

    def trocar(m):
        tag = m.group(0)
        for k, v in novos.items():
            if re.search(rf'\b{k}="', tag):
                tag = re.sub(rf'\b{k}="[^"]*"', f'{k}="{v}"', tag)
        return tag

    txt = re.sub(r"<udp\b[^>]*>", trocar, txt, count=1)
    open(arq, "w", encoding="utf-8").write(txt)
    return True, "Pronto: telemetria UDP do F1 25 ligada (127.0.0.1, porta %s, 60 Hz, formato 2025). Abra o jogo." % novos["port"]


# ---------------------------------------------------------------- lista dos jogos
JOGOS = [
    {"id": "evo", "nome": "AC EVO", "leitor": "LeitorACEvo", "tipo": "memoria", "auto": False,
     "passos": ["Não precisa configurar nada: o AC EVO libera a telemetria sozinho.",
                "Entre na pista (fora do menu) para o Axtel começar a ler."]},
    {"id": "ac", "nome": "Assetto Corsa e ACC", "leitor": "LeitorACClassico", "tipo": "memoria", "auto": False,
     "passos": ["Não precisa configurar nada: AC e ACC liberam a telemetria sozinhos.",
                "No ACC, a sessão só é guardada depois que você completa pelo menos uma volta (passar pela linha de chegada)."]},
    {"id": "iracing", "nome": "iRacing", "leitor": "LeitorIRacing", "tipo": "memoria", "auto": True,
     "processos": ["iracingsim64dx11.exe", "iracingsim64.exe"],
     "passos": ["A telemetria vem ligada de fábrica (app.ini › irsdkEnableMem=1). O botão abaixo confere e liga se estiver desligada.",
                "O Axtel só lê quando você está dentro do carro na pista (não na garagem).",
                "Se o iRacing roda como administrador, abra o Axtel também como administrador."]},
    {"id": "ams2", "nome": "Automobilista 2", "leitor": "LeitorAMS2", "tipo": "memoria", "auto": False,
     "processos": ["ams2avx.exe", "ams2.exe"],
     "passos": ["No jogo: Opções › Sistema › Memória compartilhada (Shared Memory) = \"Project CARS 2\".",
                "Saia do menu e entre na pista. Se mudou a opção agora, reinicie o AMS2.",
                "Essa opção fica só dentro do jogo: o Axtel não consegue mudá-la por fora."]},
    {"id": "f1", "nome": "F1 25", "leitor": "LeitorF1", "tipo": "udp", "auto": True, "processos": ["f1_25.exe"],
     "passos": ["No jogo: Configurações › Telemetria: Telemetria UDP = Ligada, Transmissão (broadcast) = Desligada.",
                "IP = 127.0.0.1 (o jogo e o Axtel no mesmo PC), Porta = a mesma daqui, Taxa = 60 Hz, Formato UDP = 2025.",
                "O botão abaixo faz isso no arquivo do jogo (com o F1 25 fechado)."]},
    {"id": "forza", "nome": "Forza", "leitor": "LeitorForza", "tipo": "udp", "auto": False,
     "processos": ["forzamotorsport7.exe", "forza_steamworks_release_final.exe", "forzahorizon5.exe", "forzahorizon4.exe"],
     "passos": ["No jogo: Configurações › HUD e jogabilidade › Saída de dados (Data Out) = Ligada.",
                "IP = 127.0.0.1, Porta = a mesma daqui (padrão 5300).",
                "Essa opção fica só dentro do jogo: o Axtel não consegue mudá-la por fora."]},
]


def estado(coletor, portas):
    agora = time.time()
    rodando = processos()
    diag = dict(getattr(coletor, "diag", {}) or {})
    ativo = coletor.ativo.__class__.__name__ if getattr(coletor, "ativo", None) else None
    leitores = {l.__class__.__name__: l for l in getattr(coletor, "leitores", [])}
    saida = []
    for j in JOGOS:
        item = {k: j[k] for k in ("id", "nome", "tipo", "auto", "passos")}
        aberto = any(p in rodando for p in j.get("processos", []))
        item["jogo_aberto"] = aberto if j.get("processos") else None
        l = leitores.get(j["leitor"])
        if j["tipo"] == "udp":
            ult = getattr(l, "ultimo", 0) if l else 0
            porta = getattr(l, "porta", None)
            erro = getattr(l, "erro", None)
            if erro:
                item.update(nivel="ruim", situacao=f"Porta {porta} ocupada: {erro}")
            elif ult and agora - ult < 3:
                item.update(nivel="ok", situacao=f"Recebendo dados na porta {porta}")
            elif ult:
                item.update(nivel="", situacao=f"Último dado há {int(agora - ult)} s (porta {porta})")
            else:
                item.update(nivel="ruim" if aberto else "", situacao=(f"O jogo está aberto mas nada chegou na porta {porta}: confira os passos"
                                                                      if aberto else f"Esperando dados na porta {porta}"))
        else:
            st, quando = diag.get(j["leitor"], (None, 0))
            if ativo == j["leitor"] and st == "lendo":
                item.update(nivel="ok", situacao="Lendo agora")
            elif st == "negado":
                item.update(nivel="ruim", situacao="O Windows bloqueou: o jogo está como administrador. Abra o Axtel como administrador.")
            elif st in ("aberta", "lendo") or ativo == j["leitor"]:
                item.update(nivel="ok", situacao="Memória do jogo encontrada (entre na pista para gravar)")
            else:
                item.update(nivel="ruim" if aberto else "", situacao=("O jogo está aberto mas não liberou a telemetria: confira os passos"
                                                                      if aberto else "Jogo fechado"))
        if j["id"] == "iracing":
            e = _iracing_estado()
            item["arquivo"] = e["arquivo"] if e["existe"] else ""
            item["config"] = ("ligada" if e.get("ok") else "DESLIGADA no app.ini") if e["existe"] else "app.ini não encontrado"
        elif j["id"] == "f1":
            e = _f1_estado(portas)
            item["arquivo"] = e["arquivo"] if e["existe"] else ""
            item["config"] = ("ligada no arquivo do jogo" if e.get("ok") else "desligada ou diferente no arquivo do jogo") if e["existe"] and e.get("ok") is not None else "arquivo do jogo não encontrado"
        saida.append(item)
    return saida


def ajustar(jogo_id, portas):
    try:
        if jogo_id == "iracing":
            return _iracing_ajustar(portas)
        if jogo_id == "f1":
            return _f1_ajustar(portas)
    except PermissionError:
        return False, "O Windows não deixou alterar o arquivo. Feche o jogo e tente de novo."
    except Exception as e:
        return False, f"Não consegui ajustar: {type(e).__name__}: {e}"
    return False, "Este jogo só pode ser configurado por dentro do jogo. Siga os passos."
