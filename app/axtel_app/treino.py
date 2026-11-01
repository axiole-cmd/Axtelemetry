"""Setups, desafios e plano de treino, calculados a partir das sessões gravadas."""
import json
import math
from datetime import datetime

TIPOS_DESAFIO = {
    "tempo": "Bater um tempo de volta",
    "seguidas": "Voltas válidas seguidas",
    "validas": "Porcentagem de voltas válidas numa sessão",
    "consistencia": "Consistência (variação entre as voltas)",
}


def agora():
    return datetime.now().isoformat(timespec="seconds")


def fmt_volta(ms):
    if ms is None:
        return "—"
    m, s = divmod(ms / 1000.0, 60)
    return f"{int(m)}:{s:06.3f}"


def desvio(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def combos(b):
    return b.q("SELECT jogo, carro, pista, COUNT(*) sessoes, MAX(inicio) ultima, MIN(melhor_ms) melhor_ms FROM sessoes"
               " WHERE voltas>0 GROUP BY jogo, carro, pista ORDER BY ultima DESC")


# ------------------------------------------------------------------ setups
def setups(b, jogo=None, carro=None, pista=None):
    sql, args = "SELECT * FROM setups", []
    if jogo:
        sql += " WHERE jogo=? AND carro=? AND pista=?"
        args = [jogo, carro, pista]
    lista = b.q(sql + " ORDER BY criado DESC", args)
    for s in lista:
        try:
            s["parametros"] = json.loads(s["parametros"] or "[]")
        except ValueError:
            s["parametros"] = []
        ss = b.q("SELECT id, inicio, melhor_ms, voltas FROM sessoes WHERE setup_id=? AND voltas>0 ORDER BY inicio", (s["id"],))
        melhores = [x["melhor_ms"] for x in ss if x["melhor_ms"]]
        s["sessoes"] = len(ss)
        s["voltas"] = sum(x["voltas"] for x in ss)
        s["melhor_ms"] = min(melhores) if melhores else None
        s["media_melhores_ms"] = round(sum(melhores) / len(melhores)) if melhores else None
        s["ultima"] = ss[-1]["inicio"] if ss else None
        s["sessoes_lista"] = [{"id": x["id"], "inicio": x["inicio"], "melhor_ms": x["melhor_ms"]} for x in ss[-8:]][::-1]
    return lista


def ler_parametros(texto):
    """'Asa traseira = 6' (um por linha) -> [["Asa traseira", "6"], ...]"""
    saida = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        for sep in ("=", ":", "\t"):
            if sep in linha:
                k, v = linha.split(sep, 1)
                saida.append([k.strip()[:60], v.strip()[:60]])
                break
        else:
            saida.append([linha[:60], ""])
    return saida[:80]


# ------------------------------------------------------------------ desafios
def _voltas_desde(b, d):
    return b.q("SELECT v.sessao_id, v.numero, v.tempo_ms, v.valida FROM voltas v JOIN sessoes s ON s.id=v.sessao_id"
               " WHERE s.jogo=? AND s.carro=? AND s.pista=? AND s.inicio>=? ORDER BY v.sessao_id, v.numero",
               (d["jogo"], d["carro"], d["pista"], d["criado"][:19]))


def progresso(b, d):
    """Devolve (feito, atual_texto, pct 0..100)."""
    voltas = _voltas_desde(b, d)
    por_sessao = {}
    for v in voltas:
        por_sessao.setdefault(v["sessao_id"], []).append(v)
    alvo = d["alvo"]
    if d["tipo"] == "tempo":
        val = [v["tempo_ms"] for v in voltas if v["valida"]]
        melhor = min(val) if val else None
        ref = b.q1("SELECT MIN(v.tempo_ms) m FROM voltas v JOIN sessoes s ON s.id=v.sessao_id WHERE v.valida=1"
                   " AND s.jogo=? AND s.carro=? AND s.pista=? AND s.inicio<?", (d["jogo"], d["carro"], d["pista"], d["criado"][:19]))
        partida = (ref or {}).get("m") or (melhor or alvo) + 2000
        if melhor is None:
            return False, "Nenhuma volta válida desde que o desafio foi criado", 0
        pct = 100 if melhor <= alvo else max(0, min(99, round((partida - melhor) / max(1, partida - alvo) * 100)))
        return melhor <= alvo, f"Melhor desde então: {fmt_volta(melhor)} (faltam {max(0, melhor - alvo) / 1000:.3f} s)" if melhor > alvo else f"Feito: {fmt_volta(melhor)}", pct
    if d["tipo"] == "seguidas":
        melhor = 0
        for vs in por_sessao.values():
            atual = 0
            for v in vs:
                atual = atual + 1 if v["valida"] else 0
                melhor = max(melhor, atual)
        return melhor >= alvo, f"Melhor sequência: {melhor} de {int(alvo)}", min(100, round(melhor / alvo * 100))
    if d["tipo"] == "validas":
        melhor = 0
        for vs in por_sessao.values():
            if len(vs) >= 5:
                melhor = max(melhor, round(100 * sum(v["valida"] for v in vs) / len(vs)))
        return melhor >= alvo, f"Melhor sessão: {melhor}% válidas (sessões com 5 voltas ou mais)", min(100, round(melhor / alvo * 100))
    if d["tipo"] == "consistencia":
        melhor = None
        for vs in por_sessao.values():
            ts = [v["tempo_ms"] for v in vs if v["valida"]]
            if len(ts) >= 5:
                lim = min(ts) * 1.07
                dv = desvio([t for t in ts if t <= lim])
                if dv is not None and (melhor is None or dv < melhor):
                    melhor = dv
        if melhor is None:
            return False, "Precisa de uma sessão com 5 voltas válidas ou mais", 0
        return melhor <= alvo, f"Melhor variação: ±{melhor / 1000:.3f} s (meta ±{alvo / 1000:.3f} s)", 100 if melhor <= alvo else max(0, min(99, round(alvo / melhor * 100)))
    return False, "", 0


def titulo_desafio(tipo, alvo):
    if tipo == "tempo":
        return f"Fazer uma volta abaixo de {fmt_volta(alvo)}"
    if tipo == "seguidas":
        return f"{int(alvo)} voltas válidas seguidas"
    if tipo == "validas":
        return f"Sessão com {int(alvo)}% das voltas válidas"
    return f"Variação de até ±{alvo / 1000:.3f} s entre as voltas boas"


def desafios(b):
    lista = b.q("SELECT * FROM desafios ORDER BY concluido IS NOT NULL, criado DESC")
    for d in lista:
        feito, texto, pct = progresso(b, d)
        if feito and not d["concluido"]:
            d["concluido"] = agora()
            b.executar("UPDATE desafios SET concluido=? WHERE id=?", (d["concluido"], d["id"]))
        d["progresso_texto"], d["pct"] = texto, (100 if d["concluido"] else pct)
    return lista


def sugestoes(b, existentes):
    ja = {(d["tipo"], d["jogo"], d["carro"], d["pista"]) for d in existentes if not d["concluido"]}
    saida = []
    for c in combos(b)[:4]:
        chave = (c["jogo"], c["carro"], c["pista"])
        if c["melhor_ms"]:
            alvo = int(math.floor((c["melhor_ms"] - 300) / 100.0) * 100)
            saida.append({"tipo": "tempo", "alvo": alvo})
        saida.append({"tipo": "seguidas", "alvo": 5})
        saida.append({"tipo": "validas", "alvo": 90})
        ts = [v["tempo_ms"] for v in b.q("SELECT v.tempo_ms FROM voltas v JOIN sessoes s ON s.id=v.sessao_id WHERE v.valida=1"
                                          " AND s.jogo=? AND s.carro=? AND s.pista=?", chave)]
        if len(ts) >= 5:
            dv = desvio([t for t in ts if t <= min(ts) * 1.07])
            if dv:
                saida.append({"tipo": "consistencia", "alvo": int(max(150, dv * 0.8) // 10 * 10)})
        for s in saida[-4:]:
            s.update(jogo=c["jogo"], carro=c["carro"], pista=c["pista"])
    return [dict(s, titulo=titulo_desafio(s["tipo"], s["alvo"])) for s in saida
            if (s["tipo"], s["jogo"], s["carro"], s["pista"]) not in ja][:8]


# ------------------------------------------------------------------ plano de treino
def plano(b, jogo, carro, pista):
    s = b.q1("SELECT * FROM sessoes WHERE jogo=? AND carro=? AND pista=? AND validas>=2 ORDER BY inicio DESC LIMIT 1",
             (jogo, carro, pista))
    if not s:
        return {"ok": False, "erro": "Faça uma sessão com pelo menos 2 voltas válidas nessa combinação para gerar o plano."}
    vs = b.q("SELECT tempo_ms, p1, p2, p3 FROM voltas WHERE sessao_id=? AND valida=1", (s["id"],))
    pb = b.q1("SELECT MIN(v.tempo_ms) m FROM voltas v JOIN sessoes x ON x.id=v.sessao_id WHERE v.valida=1"
              " AND x.jogo=? AND x.carro=? AND x.pista=?", (jogo, carro, pista))["m"]
    melhor = min(v["tempo_ms"] for v in vs)
    perdas = []
    for k in ("p1", "p2", "p3"):
        xs = [v[k] for v in vs if v[k]]
        if len(xs) >= 2:
            perdas.append((sum(xs) / len(xs) - min(xs), k))
    fraca = max(perdas)[1] if perdas else None
    perda = max(perdas)[0] if perdas else 0
    nomes = {"p1": "parcial 1 (primeiro terço da volta)", "p2": "parcial 2 (meio da volta)", "p3": "parcial 3 (último terço, até a chegada)"}
    ts = [v["tempo_ms"] for v in vs]
    blocos = [
        {"titulo": "Aquecimento", "min": 5, "meta": f"Voltas por volta de {fmt_volta(int(pb * 1.03))}",
         "texto": "Duas ou três voltas calmas para esquentar pneus e freios. Use para relembrar os pontos de freada."},
    ]
    if fraca:
        blocos.append({"titulo": f"Foco na {nomes[fraca]}", "min": 10,
                       "meta": f"Cortar a perda média de {perda / 1000:.2f} s pela metade",
                       "texto": "Na última sessão, foi a parte da volta em que mais variou. Repita com calma: freie um pouco antes, "
                                "acerte o ápice e acelere mais cedo na saída. Abra o detalhe da sessão para ver curva a curva."})
    blocos += [
        {"titulo": "Consistência", "min": 10, "meta": f"Voltas válidas entre {fmt_volta(int(pb * 1.01))} e {fmt_volta(int(pb * 1.015))}",
         "texto": "Sem buscar o limite: o objetivo é repetir a mesma volta, sem cortar a pista."},
        {"titulo": "Volta rápida", "min": 5, "meta": f"Bater {fmt_volta(pb)}",
         "texto": "Pneus no ponto: duas ou três tentativas no limite. Se errar, volte uma volta lenta antes de tentar de novo."},
    ]
    return {"ok": True, "base": {"id": s["id"], "inicio": s["inicio"], "melhor_ms": melhor, "pb_ms": pb,
                                 "desvio_ms": round(desvio(ts)) if desvio(ts) else None, "voltas": len(vs)},
            "blocos": blocos, "total_min": sum(x["min"] for x in blocos)}


# ------------------------------------------------------------------ melhoras de pilotagem (calendário)
def melhoras_por_sessao(b, jogo=None):
    """Para cada sessão, as melhoras em relação ao histórico daquele carro + pista."""
    sql = "SELECT id, jogo, carro, pista, inicio, voltas, validas, melhor_ms FROM sessoes WHERE voltas>0"
    args = []
    if jogo:
        sql += " AND jogo=?"
        args.append(jogo)
    ss = b.q(sql + " ORDER BY inicio", args)
    tempos = {}
    for v in b.q("SELECT sessao_id, tempo_ms FROM voltas WHERE valida=1"):
        tempos.setdefault(v["sessao_id"], []).append(v["tempo_ms"])
    hist, saida = {}, {}
    for s in ss:
        k = (s["jogo"], s["carro"], s["pista"])
        h = hist.get(k)
        combo = f"{s['carro']} · {s['pista']}"
        ts = tempos.get(s["id"], [])
        dv = desvio([t for t in ts if t <= min(ts) * 1.07]) if len(ts) >= 5 else None
        lista = []
        if h and s["melhor_ms"]:
            if h["melhor"]:
                ganho = h["melhor"] - s["melhor_ms"]
                if ganho >= 300:
                    lista.append({"tipo": "tempo", "curto": f"▲ −{ganho / 1000:.2f} s".replace(".", ","),
                                  "titulo": f"Ganho de tempo: −{ganho / 1000:.2f} s".replace(".", ","),
                                  "texto": f"{combo}: a melhor volta caiu de {fmt_volta(h['melhor'])} para {fmt_volta(s['melhor_ms'])}."})
                if s["melhor_ms"] // 1000 < h["melhor"] // 1000:
                    marco = fmt_volta(h["melhor"] // 1000 * 1000)[:-4]
                    lista.append({"tipo": "marco", "curto": f"◎ abaixo de {marco}", "titulo": f"Marco: primeira vez abaixo de {marco}",
                                  "texto": f"{combo}: nunca tinha passado desse tempo."})
            if dv is not None and h["desvio"] is not None and dv < h["desvio"] - 40:
                lista.append({"tipo": "consistencia", "curto": "◆ consistência",
                              "titulo": f"Consistência recorde: ±{dv / 1000:.3f} s".replace(".", ","),
                              "texto": f"{combo}: a menor variação entre voltas até agora (antes ±{h['desvio'] / 1000:.3f} s).".replace(".", ",", 1)})
        if s["voltas"] >= 10 and s["validas"] / s["voltas"] >= 0.95:
            lista.append({"tipo": "limpas", "curto": "✓ voltas limpas", "titulo": f"Voltas limpas: {round(100 * s['validas'] / s['voltas'])}% válidas",
                          "texto": f"{combo}: {s['validas']} de {s['voltas']} voltas sem corte de pista."})
        melhor_ant = h["melhor"] if h else None
        hist[k] = {"melhor": min(x for x in (melhor_ant, s["melhor_ms"]) if x) if (melhor_ant or s["melhor_ms"]) else None,
                   "desvio": min(x for x in ((h or {}).get("desvio"), dv) if x is not None) if ((h or {}).get("desvio") is not None or dv is not None) else None}
        if lista:
            saida[s["id"]] = lista
    return saida
