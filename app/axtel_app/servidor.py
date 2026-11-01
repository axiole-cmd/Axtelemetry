"""Servidor web local do Axtel: entrega o painel e a API em JSON."""
import csv
import io
import json
import logging
import math
import mimetypes
import os
import re
import threading
import socket
from collections import defaultdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import sistema, telemetria_jogos, treino
from .leitores import JOGOS_FUTUROS, JOGOS_SUPORTADOS

log = logging.getLogger("axtel")
VERSAO = "1.5"


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def desvio(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


class Api:
    def __init__(self, banco, coletor, porta, config=None, voz=None, backups=None, pasta_app="", pasta_dados=""):
        self.b = banco
        self.c = coletor
        self.porta = porta
        self.config = config
        self.voz = voz
        self.backups = backups
        self.pasta_app = pasta_app
        self.pasta_dados = pasta_dados

    # ---------------- auxiliares ----------------
    def _sessoes(self, jogo=None, tipo=None, data=None, mes=None):
        sql = "SELECT * FROM sessoes WHERE voltas>0"
        args = []
        if data:
            sql += " AND substr(inicio,1,10)=?"
            args.append(data)
        if mes:
            sql += " AND substr(inicio,1,7)=?"
            args.append(mes)
        if jogo:
            sql += " AND jogo=?"
            args.append(jogo)
        if tipo:
            sql += " AND tipo=?"
            args.append(tipo)
        ss = self.b.q(sql + " ORDER BY inicio", args)
        # marca as sessões que bateram o recorde pessoal daquele jogo+carro+pista
        todas = ss if not (jogo or tipo or data or mes) else self.b.q("SELECT id,jogo,carro,pista,melhor_ms FROM sessoes WHERE voltas>0 ORDER BY inicio")
        melhor = {}
        recorde = set()
        for s in todas:
            k = (s["jogo"], s["carro"], s["pista"])
            if s["melhor_ms"] and (k not in melhor or s["melhor_ms"] < melhor[k]):
                melhor[k] = s["melhor_ms"]
                recorde.add(s["id"])
        for s in ss:
            s["recorde"] = s["id"] in recorde
            s["aberta"] = bool(s["aberta"])
        ss.reverse()
        return ss

    @staticmethod
    def _totais(ss):
        return {"sessoes": len(ss), "voltas": sum(s["voltas"] for s in ss),
                "validas": sum(s["validas"] for s in ss), "tempo_s": sum(s["tempo_s"] or 0 for s in ss),
                "distancia_km": round(sum(s["distancia_m"] or 0 for s in ss) / 1000, 1),
                "recordes": sum(1 for s in ss if s["recorde"])}

    @staticmethod
    def _semanas(ss, n=8):
        hoje = date.today()
        ini = hoje - timedelta(days=hoje.weekday())
        semanas = [ini - timedelta(weeks=k) for k in range(n - 1, -1, -1)]
        cont = defaultdict(int)
        for s in ss:
            d = datetime.fromisoformat(s["inicio"]).date()
            cont[d - timedelta(days=d.weekday())] += 1
        return [{"semana": w.isoformat(), "sessoes": cont.get(w, 0)} for w in semanas]

    # ---------------- rotas ----------------
    def status(self, _):
        e = self.c.foto_status()
        e.update(ip=ip_local(), porta=self.porta, versao=VERSAO)
        return e

    def resumo(self, _):
        ss = self._sessoes()
        por_jogo = []
        for j in sorted({s["jogo"] for s in ss}):
            sj = [s for s in ss if s["jogo"] == j]
            t = self._totais(sj)
            t.update(jogo=j, ultima=sj[0]["inicio"])
            por_jogo.append(t)
        por_jogo.sort(key=lambda x: -x["tempo_s"])
        return {"totais": self._totais(ss), "por_jogo": por_jogo, "recentes": ss[:8],
                "recordes": [s for s in ss if s["recorde"]][:6], "semanas": self._semanas(ss),
                "suportados": JOGOS_SUPORTADOS, "futuros": JOGOS_FUTUROS}

    def jogos(self, _):
        return {"com_dados": [r["jogo"] for r in self.b.q(
            "SELECT jogo, MAX(inicio) u FROM sessoes WHERE voltas>0 GROUP BY jogo ORDER BY u DESC")],
            "suportados": JOGOS_SUPORTADOS}

    def jogo(self, a):
        nome = a.get("nome", "")
        ss = self._sessoes(nome)
        combos = {}
        for s in reversed(ss):  # do mais antigo para o mais novo
            k = (s["carro"], s["pista"])
            c = combos.setdefault(k, {"carro": s["carro"], "pista": s["pista"], "sessoes": 0, "voltas": 0,
                                      "melhor_ms": None, "melhor_sessao": None, "ultima": None, "evolucao": []})
            c["sessoes"] += 1
            c["voltas"] += s["voltas"]
            c["ultima"] = s["inicio"]
            if s["melhor_ms"]:
                c["evolucao"].append({"inicio": s["inicio"], "melhor_ms": s["melhor_ms"], "id": s["id"]})
                if c["melhor_ms"] is None or s["melhor_ms"] < c["melhor_ms"]:
                    c["melhor_ms"], c["melhor_sessao"] = s["melhor_ms"], s["id"]
        tipos = defaultdict(int)
        for s in ss:
            tipos[s["tipo"]] += 1
        voltas = self.b.q("SELECT v.tempo_ms, v.valida, s.carro, s.pista FROM voltas v JOIN sessoes s ON s.id=v.sessao_id"
                          " WHERE s.jogo=?", (nome,))
        total = len(voltas)
        validas = [v for v in voltas if v["valida"]]
        # consistência: desvio das voltas válidas até 107% da melhor de cada combo
        por_combo = defaultdict(list)
        for v in validas:
            por_combo[(v["carro"], v["pista"])].append(v["tempo_ms"])
        desvios = []
        for ts in por_combo.values():
            m = min(ts)
            boas = [t for t in ts if t <= m * 1.07]
            d = desvio(boas)
            if d is not None:
                desvios.append(d)
        return {"jogo": nome, "totais": self._totais(ss),
                "combos": sorted(combos.values(), key=lambda c: c["ultima"] or "", reverse=True),
                "tipos": [{"tipo": k, "sessoes": n} for k, n in sorted(tipos.items(), key=lambda x: -x[1])],
                "qualidade": {"voltas": total, "validas": len(validas),
                              "pct_validas": round(100 * len(validas) / total) if total else None,
                              "consistencia_ms": round(sum(desvios) / len(desvios)) if desvios else None},
                "sessoes": ss}

    def sessoes(self, a):
        data = a.get("data") or None
        ss = self._sessoes(a.get("jogo") or None, a.get("tipo") or None, data)
        tipos = sorted({s["tipo"] for s in self._sessoes(a.get("jogo") or None, data=data)})
        return {"sessoes": ss, "tipos": tipos, "totais": self._totais(ss)}

    def calendario(self, a):
        mes = a.get("mes") or date.today().strftime("%Y-%m")
        jogo = a.get("jogo") or None
        ss = self._sessoes(jogo, mes=mes)
        dias = {}
        for s in ss:
            d = dias.setdefault(s["inicio"][:10], {"sessoes": 0, "voltas": 0, "tempo_s": 0, "jogos": [], "recordes": 0})
            d["sessoes"] += 1
            d["voltas"] += s["voltas"]
            d["tempo_s"] += s["tempo_s"] or 0
            d["recordes"] += 1 if s["recorde"] else 0
            if s["jogo"] not in d["jogos"]:
                d["jogos"].append(s["jogo"])
        melhoras = treino.melhoras_por_sessao(self.b, jogo)
        for s in ss:
            if s["id"] in melhoras:
                d = dias[s["inicio"][:10]]
                d.setdefault("melhoras", []).extend(melhoras[s["id"]])
        meses = [r["m"] for r in self.b.q("SELECT DISTINCT substr(inicio,1,7) m FROM sessoes WHERE voltas>0 ORDER BY m")]
        return {"mes": mes, "dias": dias, "totais": self._totais(ss), "meses_com_dados": meses}

    def dia(self, a):
        data = a.get("data", "")
        ss = self._sessoes(a.get("jogo") or None, data=data)
        pistas = sorted({f"{s['pista']}" for s in ss})
        carros = sorted({s["carro"] for s in ss})
        melhoras = treino.melhoras_por_sessao(self.b, a.get("jogo") or None)
        return {"data": data, "sessoes": ss, "totais": self._totais(ss), "pistas": pistas, "carros": carros,
                "melhoras": [m for s in ss for m in melhoras.get(s["id"], [])],
                "jogos": sorted({s["jogo"] for s in ss})}

    # ---------------- eventos do spotter, voz, configurações ----------------
    def eventos(self, a):
        return {"eventos": self.c.eventos_depois(int(a.get("depois", 0) or 0)), "ultimo": self.c.ev_id}

    def voz_estado(self, _):
        e = self.voz.estado() if self.voz else {"chave": False}
        e["vozes"] = self.config["spotter"]["vozes"] if self.config else {}
        return e

    def p_voz(self, corpo):
        if not self.voz:
            return {"ok": False, "erro": "Voz indisponível."}
        lingua, chave = self.voz.falar(corpo.get("texto", ""), corpo.get("lingua", "pt"))
        if not lingua:
            return {"ok": False, "erro": chave}
        return {"ok": True, "url": f"/api/voz/arquivo?l={lingua}&h={chave}"}

    def arquivo_voz(self, a):
        l, h = a.get("l", ""), a.get("h", "")
        if l not in ("pt", "en", "es") or not re.fullmatch(r"[0-9a-f]{8,40}", h or ""):
            return None
        caminho = self.voz.caminho(l, h)
        if not os.path.exists(caminho):
            return None
        with open(caminho, "rb") as f:
            return f.read()

    def config_ler(self, _):
        c = self.config.tudo()
        c["iniciar_com_windows"] = sistema.esta_no_inicializar()
        c["backups"] = sistema.listar_backups(self.pasta_dados)[:20]
        c["pasta_dados"] = self.pasta_dados
        c["portas_em_uso"] = [l.jogo for l in self.c.leitores if getattr(l, "erro", None)]
        return c

    def p_config(self, corpo):
        aviso = ""
        permitido = {k: corpo[k] for k in ("spotter", "backup", "portas", "atalhos") if k in corpo}
        if "atalhos" in permitido:
            permitido["atalhos"] = bool(permitido["atalhos"])
            aviso = "Vale quando o Axtel for aberto de novo."
        if "portas" in permitido:
            try:
                portas = {k: int(v) for k, v in permitido["portas"].items() if k in ("f1", "forza")}
            except (TypeError, ValueError):
                portas = {"x": 0}
            if not portas or any(not 1024 <= v <= 65535 for v in portas.values()):
                return {"ok": False, "erro": "Porta inválida (use um número entre 1024 e 65535)."}
            if len(set(portas.values())) < len(portas):
                return {"ok": False, "erro": "O F1 25 e o Forza precisam de portas diferentes."}
            permitido["portas"] = portas
            aviso = "As portas novas valem quando o Axtel for aberto de novo."
        self.config.atualizar(permitido)
        if "iniciar_com_windows" in corpo:
            ok, msg = sistema.iniciar_com_windows(bool(corpo["iniciar_com_windows"]), self.pasta_app)
            if not ok:
                return {"ok": False, "erro": msg}
            aviso = msg
        return {"ok": True, "aviso": aviso}

    def _portas(self):
        return (self.config.tudo().get("portas") if self.config else None) or {"f1": 20777, "forza": 5300}

    def telemetria(self, _):
        return {"jogos": telemetria_jogos.estado(self.c, self._portas())}

    def p_telemetria(self, corpo):
        ok, msg = telemetria_jogos.ajustar(str(corpo.get("jogo", "")), self._portas())
        log.info("ajuste de telemetria %s: %s", corpo.get("jogo"), msg)
        return {"ok": ok, "aviso" if ok else "erro": msg}

    def p_fechar(self, _):
        log.info("fechando o Axtel pelo painel")
        if getattr(self, "desligar", None):
            threading.Timer(0.5, self.desligar).start()
        return {"ok": True}

    def p_backup(self, _):
        return {"ok": True, "arquivo": self.backups.agora()}

    # ---------------- setups ----------------
    def setups(self, a):
        jogo, carro, pista = a.get("jogo"), a.get("carro"), a.get("pista")
        return {"combos": treino.combos(self.b), "setups": treino.setups(self.b, jogo, carro, pista) if jogo else []}

    def p_setup_salvar(self, c):
        nome = (c.get("nome") or "").strip()[:80]
        if not nome or not c.get("jogo"):
            return {"ok": False, "erro": "Dê um nome ao setup."}
        params = json.dumps(treino.ler_parametros(c.get("parametros_texto", "")), ensure_ascii=False)
        if c.get("id"):
            self.b.executar("UPDATE setups SET nome=?, parametros=?, notas=? WHERE id=?",
                            (nome, params, (c.get("notas") or "")[:2000], int(c["id"])))
            return {"ok": True, "id": int(c["id"])}
        sid = self.b.executar("INSERT INTO setups(jogo,carro,pista,nome,parametros,notas,criado) VALUES(?,?,?,?,?,?,?)",
                              (c["jogo"], c["carro"], c["pista"], nome, params, (c.get("notas") or "")[:2000], treino.agora()))
        return {"ok": True, "id": sid}

    def p_setup_apagar(self, c):
        sid = int(c.get("id", 0))
        self.b.executar("UPDATE sessoes SET setup_id=NULL WHERE setup_id=?", (sid,))
        self.b.executar("DELETE FROM setups WHERE id=?", (sid,))
        return {"ok": True}

    def p_sessao_setup(self, c):
        sid = c.get("setup_id")
        self.b.executar("UPDATE sessoes SET setup_id=? WHERE id=?", (int(sid) if sid else None, int(c.get("sessao_id", 0))))
        return {"ok": True}

    # ---------------- desafios e plano ----------------
    def desafios(self, _):
        lista = treino.desafios(self.b)
        return {"desafios": lista, "sugestoes": treino.sugestoes(self.b, lista), "combos": treino.combos(self.b),
                "tipos": treino.TIPOS_DESAFIO}

    def p_desafio_criar(self, c):
        tipo = c.get("tipo")
        if tipo not in treino.TIPOS_DESAFIO or not c.get("jogo"):
            return {"ok": False, "erro": "Escolha o tipo e a combinação de carro e pista."}
        try:
            alvo = float(c.get("alvo"))
        except (TypeError, ValueError):
            return {"ok": False, "erro": "Meta inválida."}
        did = self.b.executar("INSERT INTO desafios(tipo,jogo,carro,pista,alvo,titulo,criado) VALUES(?,?,?,?,?,?,?)",
                              (tipo, c["jogo"], c["carro"], c["pista"], alvo, treino.titulo_desafio(tipo, alvo), treino.agora()))
        return {"ok": True, "id": did}

    def p_desafio_apagar(self, c):
        self.b.executar("DELETE FROM desafios WHERE id=?", (int(c.get("id", 0)),))
        return {"ok": True}

    def plano(self, a):
        return treino.plano(self.b, a.get("jogo", ""), a.get("carro", ""), a.get("pista", ""))

    def pendencias(self, _):
        return {"pendencias": self.b.q("SELECT * FROM pendencias ORDER BY feita, id")}

    def p_pend_nova(self, corpo):
        texto = (corpo.get("texto") or "").strip()
        if not texto:
            return {"ok": False, "erro": "Escreva a pendência."}
        return {"ok": True, "id": self.b.nova_pendencia(texto[:300], (corpo.get("nota") or "").strip()[:2000])}

    def p_pend_editar(self, corpo):
        self.b.editar_pendencia(int(corpo.get("id", 0)), {k: corpo[k] for k in ("feita", "texto", "nota") if k in corpo})
        return {"ok": True}

    def p_pend_apagar(self, corpo):
        self.b.apagar_pendencia(int(corpo.get("id", 0)))
        return {"ok": True}

    def sessao(self, a):
        sid = int(a.get("id", 0))
        todas = self._sessoes()
        s = next((x for x in todas if x["id"] == sid), None)
        if not s:
            return {"erro": "Sessão não encontrada"}
        pos = todas.index(s)
        voltas = self.b.q("SELECT id,numero,tempo_ms,valida,motivo,p1,p2,p3,distancia_m,combustivel,vel_max,quando"
                          " FROM voltas WHERE sessao_id=? ORDER BY numero", (sid,))
        val = [v for v in voltas if v["valida"]]
        tempos = [v["tempo_ms"] for v in val]
        ideal = None
        ps = [[v[k] for v in val if v[k]] for k in ("p1", "p2", "p3")]
        if all(ps):
            ideal = sum(min(p) for p in ps)
        pb = self.b.q1("SELECT MIN(v.tempo_ms) m FROM voltas v JOIN sessoes x ON x.id=v.sessao_id"
                       " WHERE v.valida=1 AND x.jogo=? AND x.carro=? AND x.pista=?", (s["jogo"], s["carro"], s["pista"]))
        setups_combo = self.b.q("SELECT id, nome FROM setups WHERE jogo=? AND carro=? AND pista=? ORDER BY criado DESC",
                                (s["jogo"], s["carro"], s["pista"]))
        return {"sessao": s, "voltas": voltas, "setups": setups_combo,
                "media_ms": round(sum(tempos) / len(tempos)) if tempos else None,
                "desvio_ms": round(desvio(tempos)) if desvio(tempos) is not None else None,
                "ideal_ms": ideal, "pb_ms": pb["m"] if pb else None,
                "mais_nova": todas[pos - 1]["id"] if pos > 0 else None,
                "mais_antiga": todas[pos + 1]["id"] if pos + 1 < len(todas) else None,
                "posicao": pos + 1, "total": len(todas)}

    def volta(self, a):
        v = self.b.q1("SELECT v.*, s.jogo, s.carro, s.pista, s.inicio FROM voltas v JOIN sessoes s ON s.id=v.sessao_id"
                      " WHERE v.id=?", (int(a.get("id", 0)),))
        if not v:
            return {"erro": "Volta não encontrada"}
        v["amostras"] = json.loads(v["amostras"] or "[]")
        return v

    def aovivo(self, _):
        d = self.c.foto_ao_vivo()
        d["status"] = self.c.foto_status()["nivel"]
        return d

    # ---------------- POST ----------------
    def p_relatorio(self, corpo):
        caminho = self.c.relatorio(corpo.get("texto", ""))
        return {"ok": True, "arquivo": caminho}

    def p_resolver(self, corpo):
        self.c.resolver_alerta(int(corpo.get("id", 0)))
        return {"ok": True}

    def p_apagar(self, corpo):
        sid = int(corpo.get("id", 0))
        if sid == self.c.sessao:
            return {"ok": False, "erro": "Essa sessão ainda está sendo gravada."}
        self.b.apagar_sessao(sid)
        return {"ok": True}

    def csv(self, a):
        sid = int(a.get("id", 0))
        s = self.b.q1("SELECT * FROM sessoes WHERE id=?", (sid,))
        voltas = self.b.q("SELECT numero,tempo_ms,valida,motivo,p1,p2,p3,distancia_m,combustivel,vel_max,quando"
                          " FROM voltas WHERE sessao_id=? ORDER BY numero", (sid,))
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["jogo", "carro", "pista", "tipo", "volta", "tempo_s", "valida", "motivo", "parcial1_s",
                    "parcial2_s", "parcial3_s", "distancia_m", "combustivel_l", "vel_max_kmh", "quando"])
        for v in voltas:
            seg = lambda x: f"{x / 1000:.3f}".replace(".", ",") if x else ""
            w.writerow([s["jogo"], s["carro"], s["pista"], s["tipo"], v["numero"], seg(v["tempo_ms"]),
                        "sim" if v["valida"] else "não", v["motivo"] or "", seg(v["p1"]), seg(v["p2"]), seg(v["p3"]),
                        v["distancia_m"], v["combustivel"] or "", v["vel_max"], v["quando"]])
        nome = f"axtel_{s['jogo']}_{s['pista']}_{s['inicio'][:10]}.csv".replace(" ", "_") if s else "axtel.csv"
        return buf.getvalue().encode("utf-8-sig"), nome


def criar_servidor(api, pasta_painel, porta):
    rotas_get = {"/api/status": api.status, "/api/resumo": api.resumo, "/api/jogos": api.jogos,
                 "/api/jogo": api.jogo, "/api/sessoes": api.sessoes, "/api/sessao": api.sessao,
                 "/api/volta": api.volta, "/api/aovivo": api.aovivo, "/api/calendario": api.calendario,
                 "/api/dia": api.dia, "/api/pendencias": api.pendencias, "/api/eventos": api.eventos,
                 "/api/voz/estado": api.voz_estado, "/api/config": api.config_ler, "/api/setups": api.setups,
                 "/api/desafios": api.desafios, "/api/plano": api.plano,
                 "/api/telemetria": api.telemetria}
    rotas_post = {"/api/relatorio": api.p_relatorio, "/api/alerta/resolver": api.p_resolver,
                  "/api/sessao/apagar": api.p_apagar, "/api/pendencias/nova": api.p_pend_nova,
                  "/api/pendencias/editar": api.p_pend_editar, "/api/pendencias/apagar": api.p_pend_apagar,
                  "/api/voz": api.p_voz, "/api/config": api.p_config, "/api/backup": api.p_backup, "/api/fechar": api.p_fechar,
                  "/api/setups/salvar": api.p_setup_salvar, "/api/setups/apagar": api.p_setup_apagar,
                  "/api/sessao/setup": api.p_sessao_setup, "/api/desafios/criar": api.p_desafio_criar,
                  "/api/desafios/apagar": api.p_desafio_apagar, "/api/telemetria/ajustar": api.p_telemetria}

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _enviar(self, codigo, corpo, tipo, extra=None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, obj, codigo=200):
            self._enviar(codigo, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                         "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            args = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in rotas_get:
                    return self._json(rotas_get[u.path](args))
                if u.path == "/api/voz/arquivo":
                    dados = api.arquivo_voz(args)
                    if dados is None:
                        return self._json({"erro": "áudio não encontrado"}, 404)
                    return self._enviar(200, dados, "audio/mpeg")
                if u.path == "/api/sessao/csv":
                    dados, nome = api.csv(args)
                    return self._enviar(200, dados, "text/csv; charset=utf-8",
                                        {"Content-Disposition": f'attachment; filename="{nome}"'})
            except Exception as e:
                log.exception("erro na API")
                return self._json({"erro": str(e)}, 500)
            caminho = u.path.lstrip("/") or "index.html"
            arq = os.path.normpath(os.path.join(pasta_painel, caminho))
            if not arq.startswith(os.path.normpath(pasta_painel)) or not os.path.isfile(arq):
                arq = os.path.join(pasta_painel, "index.html")
            with open(arq, "rb") as fh:
                dados = fh.read()
            tipo = mimetypes.guess_type(arq)[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo.endswith("javascript"):
                tipo += "; charset=utf-8"
            self._enviar(200, dados, tipo)

        def do_POST(self):
            u = urlparse(self.path)
            # Proteção contra outros sites mandando comandos pelo navegador (CSRF):
            # só aceita JSON e, se o navegador informar a origem, ela tem que ser o próprio painel.
            tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            origem = self.headers.get("Origin")
            if tipo != "application/json" or (origem and urlparse(origem).netloc != self.headers.get("Host")):
                return self._json({"erro": "pedido recusado"}, 403)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
                if u.path in rotas_post:
                    return self._json(rotas_post[u.path](corpo))
                return self._json({"erro": "rota desconhecida"}, 404)
            except Exception as e:
                log.exception("erro na API")
                return self._json({"erro": str(e)}, 500)

    srv = ThreadingHTTPServer(("0.0.0.0", porta), H)
    srv.daemon_threads = True
    return srv
