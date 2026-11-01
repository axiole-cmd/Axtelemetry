"""Coletor: detecta o jogo, lê a telemetria e grava sessões e voltas."""
import bisect
import json
import logging
import math
import os
import threading
import time
import zipfile
from collections import deque
from datetime import datetime

from .leitores import legivel, todos_os_leitores

log = logging.getLogger("axtel")

INTERVALO = 0.02          # 50 leituras por segundo
AMOSTRA_S = 0.1           # guarda 10 pontos por segundo em cada volta
SEM_DADOS_AVISO = 5       # s sem pacote novo -> amarelo
SEM_DADOS_SOLTA = 10      # s sem pacote novo -> solta a memória do jogo
FECHA_SESSAO = 120        # s fora da pista -> encerra a sessão

MOTIVOS = {
    "saida": "Volta de saída (começou no meio da volta)",
    "box": "Passou pelos boxes",
    "pneus": "Saiu da pista (3 ou mais pneus fora)",
    "jogo": "Inválida no jogo",
    "incidente": "Incidente na pista",
}
ORDEM_MOTIVOS = ["saida", "box", "jogo", "incidente", "pneus"]


def agora_iso():
    return datetime.now().isoformat(timespec="seconds")


class Coletor(threading.Thread):
    def __init__(self, banco, pasta_dados, config=None):
        super().__init__(daemon=True, name="coletor")
        self.banco = banco
        self.pasta = pasta_dados
        self.config = config
        self.leitores = todos_os_leitores(config["portas"] if config else None)
        self.eventos = deque(maxlen=100)
        self.ev_id = 0
        self._avisos_porta = set()
        self._avisos_acesso = set()
        self._descanso = {}
        self.diag = {}  # por leitor: (estado da memória, quando) para a página de Configurações
        self._visto = {}
        self._voltas_validas = []
        self._comb_por_volta = []
        self._contorno = None
        self._t_linha = 0.0  # quando o carro cruzou a linha pela última vez
        self.ativo = None
        self.parar = threading.Event()
        self.trava = threading.RLock()
        self.alertas = deque(maxlen=30)
        self._id_alerta = 0
        self.estado = {"nivel": "amarelo", "titulo": "Aguardando jogo",
                       "detalhe": "Abra o AC EVO, o Assetto Corsa ou o ACC e entre na pista.",
                       "jogo": None, "gravando": False, "sessao_id": None, "desde": time.time(),
                       "jogos": "AC EVO, Assetto Corsa, ACC, iRacing, Automobilista 2, F1 25 e Forza"}
        self.ao_vivo = {}
        self.evento = 0
        self.ultimo_evento = None
        self._ult_busca = 0
        self._ult_pacote = None
        self._ult_mudanca = 0
        self._ult_live = 0
        self._ruins = 0
        self._erro_layout_avisado = False
        self.sessao = None
        self.chave = None
        self.prev = None
        self.v = None
        self.pendente = None
        self.num = 0
        self.melhor_ms = None
        self.melhor_curva = None
        self._ult_toque = 0

    # ------------------------------------------------------------------ util
    def alerta(self, nivel, texto):
        with self.trava:
            for a in self.alertas:
                if a["texto"] == texto and not a["resolvido"]:
                    a["quando"] = agora_iso()
                    return
            self._id_alerta += 1
            self.alertas.appendleft({"id": self._id_alerta, "nivel": nivel, "texto": texto,
                                     "quando": agora_iso(), "resolvido": False})
        log.warning("alerta: %s", texto)

    def resolver_alerta(self, aid):
        with self.trava:
            for a in self.alertas:
                if a["id"] == aid:
                    a["resolvido"] = True

    def _status(self, nivel, titulo, detalhe, jogo=None):
        with self.trava:
            if self.estado["titulo"] != titulo:
                self.estado["desde"] = time.time()
            self.estado.update(nivel=nivel, titulo=titulo, detalhe=detalhe, jogo=jogo,
                               gravando=self.sessao is not None and nivel == "verde",
                               sessao_id=self.sessao)

    def foto_status(self):
        with self.trava:
            e = dict(self.estado)
            e["alertas"] = [dict(a) for a in self.alertas]
            e["pendentes"] = sum(1 for a in self.alertas if not a["resolvido"])
            e["evento"] = self.evento
            e["ultimo_evento"] = self.ultimo_evento
            e["ev_id"] = self.ev_id
            return e

    def foto_ao_vivo(self):
        with self.trava:
            d = dict(self.ao_vivo)
            d["evento"] = self.evento
            d["ultimo_evento"] = self.ultimo_evento
            return d

    def _evento(self, tipo, **dados):
        with self.trava:
            self.ev_id += 1
            dados.update(id=self.ev_id, tipo=tipo, quando=agora_iso())
            self.eventos.append(dados)

    def eventos_depois(self, i):
        with self.trava:
            return [dict(e) for e in self.eventos if e["id"] > i]

    # ------------------------------------------------------------------ laço
    def run(self):
        log.info("coletor iniciado")
        while not self.parar.is_set():
            try:
                self.passo()
            except Exception as e:  # nunca derruba o app
                log.exception("erro na leitura")
                self._status("vermelho", "Erro na leitura", f"{type(e).__name__}: {e}",
                             self.ativo.jogo if self.ativo else None)
                self.alerta("erro", f"Erro na leitura: {type(e).__name__}: {e}")
                if self.ativo:
                    self.ativo.fechar()
                    self.ativo = None
                time.sleep(1)
            time.sleep(INTERVALO)
        self.encerrar_sessao()
        log.info("coletor parado")

    def passo(self):
        t = time.time()
        for l in self.leitores:
            erro = getattr(l, "erro", None)
            if erro and l.jogo not in self._avisos_porta:
                self._avisos_porta.add(l.jogo)
                self.alerta("erro", f"{l.jogo}: {erro} Troque a porta em Configurações.")
        if self.ativo is None:
            if t - self._ult_busca >= 1:
                self._ult_busca = t
                self._buscar(t)
            if self.ativo is None:
                self._status("amarelo", "Aguardando jogo",
                             "Abra um jogo compatível e entre na pista: " + self.estado["jogos"] + ".")
                self._talvez_fechar(t)
                with self.trava:
                    self.ao_vivo = {}
                return

        q = self.ativo.ler()
        if q is None:
            self.ativo.fechar()
            self.ativo = None
            return
        if q.pacote != self._ult_pacote:
            self._ult_pacote = q.pacote
            self._ult_mudanca = t
        parado = t - self._ult_mudanca
        if parado > SEM_DADOS_SOLTA:
            log.info("sem dados novos há %.0fs, soltando a memória do jogo", parado)
            self._descanso[self.ativo] = t + 60  # deixa os outros jogos serem procurados primeiro
            self.ativo.fechar()
            self.ativo = None
            return
        if parado > SEM_DADOS_AVISO:
            self._status("amarelo", "Sem dados novos", "O jogo parou de mandar dados (fechou ou está carregando).", q.jogo)
            self._talvez_fechar(t)
            return
        if q.status != "LIVE" and t - self._ult_busca >= 3:
            # outro jogo pode estar na pista enquanto este está parado no menu
            self._ult_busca = t
            if self._buscar(t, so_na_pista=True):
                return
        if q.status != "LIVE":
            textos = {"PAUSE": ("Jogo pausado", "A gravação continua quando você voltar para a pista."),
                      "REPLAY": ("Replay", "Replays não são gravados."),
                      "OFF": ("No menu do jogo", "Entre na pista para começar a gravar.")}
            tit, det = textos.get(q.status, ("Aguardando", ""))
            self._status("amarelo", tit, det, q.jogo)
            self._talvez_fechar(t)
            return
        # confere se os dados fazem sentido (protege contra layout errado)
        if not legivel(q.carro) or not (-0.01 <= q.npos <= 1.01) or q.atual_ms < 0 or abs(q.vel) > 600:
            self._ruins += 1
            if self._ruins > 150:
                self._status("vermelho", "Dados estranhos",
                             f"O {q.jogo} está mandando dados que o Axtel não entende. Use 'Relatar um problema'.", q.jogo)
                if not self._erro_layout_avisado:
                    self._erro_layout_avisado = True
                    self.alerta("erro", f"{q.jogo}: dados com formato inesperado (carro='{q.carro[:20]}', posição={q.npos:.3f})."
                                        " Mande um relatório para ajustarmos o leitor.")
            return
        self._ruins = 0
        self._ult_live = t
        self.diag[self.ativo.__class__.__name__] = ("lendo", t)
        self.processar(q, t)
        self._status("verde", f"Ao vivo · {q.jogo}", f"{q.carro} · {q.pista} · {q.tipo}", q.jogo)

    def _buscar(self, t, so_na_pista=False):
        """Procura o jogo aberto. Prefere quem está na pista e com dados mudando.

        Uma memória pode continuar existindo depois que o jogo fecha (outro programa
        segura ela aberta). Por isso um leitor parado não impede os outros de serem testados.
        """
        melhor, nota_melhor = None, 0
        for l in self.leitores:
            if l is self.ativo or self._descanso.get(l, 0) > t:
                continue
            if not l.abrir():
                l.fechar()
                self.diag[l.__class__.__name__] = ("negado" if l.acesso_negado else "ausente", t)
                if l.acesso_negado and l.jogo not in self._avisos_acesso:
                    self._avisos_acesso.add(l.jogo)
                    log.warning("%s: acesso negado à memória do jogo", l.jogo)
                    self.alerta("erro", f"{l.jogo}: o Windows bloqueou a leitura. O jogo deve estar rodando como administrador:"
                                        " feche o Axtel e abra de novo com o botão direito > Executar como administrador.")
                continue
            try:
                q = l.ler()
            except Exception:
                log.exception("erro testando %s", l.jogo)
                q = None
            nota = 0
            self.diag[l.__class__.__name__] = ("aberta", t)
            if q is not None:
                anterior = self._visto.get(l)
                parado = anterior is not None and anterior[0] == q.pacote and t - anterior[1] >= 2
                if anterior is None or anterior[0] != q.pacote:
                    self._visto[l] = (q.pacote, t)
                nota = 1 if parado else (3 if q.status == "LIVE" else 2)
            if nota > nota_melhor and (not so_na_pista or nota == 3):
                if melhor is not None:
                    melhor.fechar()
                melhor, nota_melhor = l, nota
            else:
                l.fechar()
        if melhor is None:
            return False
        if self.ativo is not None:
            log.info("trocando de %s para %s", self.ativo.jogo, melhor.jogo)
            self.ativo.fechar()
        self.ativo = melhor
        self._ult_pacote = None
        self._ult_mudanca = t
        log.info("memória encontrada: %s", melhor.__class__.__name__)
        return True

    def _talvez_fechar(self, t):
        if self.sessao is not None and t - self._ult_live > FECHA_SESSAO:
            self.encerrar_sessao()

    # ------------------------------------------------------------------ sessão / volta
    def encerrar_sessao(self):
        if self.sessao is not None:
            self.banco.encerrar_sessao(self.sessao, agora_iso())
            log.info("sessão %s encerrada", self.sessao)
        self.sessao = None
        self.chave = None
        self.prev = None
        self.v = None
        self.pendente = None

    def _nova_volta(self, q, limpo):
        self.v = {"limpo": limpo, "motivos": set(), "amostras": [], "t_amostra": 0.0, "p1": None, "p2": None,
                  "dist": 0.0, "ult_xz": None, "vel_max": 0.0, "comb0": q.combustivel, "quando": agora_iso(),
                  "inc0": (q.extra or {}).get("incidentes"), "avisou_invalida": False, "no_box": q.no_box}

    def processar(self, q, t):
        chave = (q.jogo, q.carro, q.pista, q.tipo)
        if self.sessao is None or chave != self.chave:
            self.encerrar_sessao()
            self.sessao = self.banco.nova_sessao(q.jogo, q.carro, q.pista, q.tipo, agora_iso())
            self.chave = chave
            self.num = 0
            self.melhor_ms = None
            self.melhor_curva = None
            self._nova_volta(q, limpo=(q.npos < 0.02 and q.atual_ms < 1500))
            self._voltas_validas = []
            self._comb_por_volta = []
            self._contorno = None
            log.info("sessão %s aberta: %s", self.sessao, chave)

        p = self.prev
        if p is not None:
            reiniciou_tempo = p.atual_ms > 10000 and q.atual_ms + 3000 < p.atual_ms
            contou = (q.contador_voltas is not None and p.contador_voltas is not None
                      and q.contador_voltas == p.contador_voltas + 1)
            cruzou = p.npos > 0.85 and q.npos < 0.15
            perto_da_linha = q.npos < 0.05 or q.npos > 0.97
            if reiniciou_tempo and (contou or cruzou) and not (t - self._t_linha < 5 and perto_da_linha):
                self.pendente = {"v": self.v, "tempo_antes": p.atual_ms, "ultima_antes": p.ultima_ms,
                                 "comb_fim": p.combustivel, "espera": 0}
                self._t_linha = t
                self._nova_volta(q, limpo=True)
            elif reiniciou_tempo and perto_da_linha and t - self._t_linha < 5:
                # Repique logo depois da linha: alguns jogos (AC, ACC) mandam por um instante o
                # tempo da volta anterior depois de zerar. A volta nova continua limpa.
                self._nova_volta(q, limpo=self.v["limpo"])
            elif reiniciou_tempo or (q.contador_voltas is not None and p.contador_voltas is not None
                                     and q.contador_voltas < p.contador_voltas):
                # sessão reiniciada / voltou para os boxes: descarta a volta em andamento
                self._nova_volta(q, limpo=False)

        if self.pendente is not None:
            pd = self.pendente
            pd["espera"] += 1
            if (q.ultima_ms != pd["ultima_antes"] and q.ultima_ms > 0) or pd["espera"] >= 25:
                self._fechar_volta(q)

        self._acumular(q, t)
        self.prev = q
        if t - self._ult_toque > 10:
            self._ult_toque = t
            self.banco.tocar_sessao(self.sessao, agora_iso())
        self._atualizar_ao_vivo(q)

    def _acumular(self, q, t):
        v = self.v
        if q.no_box and not v["no_box"]:
            self._evento("boxes", entrada=True)
        v["no_box"] = q.no_box
        if q.no_box:
            v["motivos"].add("box")
        inc = (q.extra or {}).get("incidentes")
        if inc is not None and v["inc0"] is not None and inc > v["inc0"]:
            v["motivos"].add("incidente")
        if v["limpo"] and not v["avisou_invalida"] and v["motivos"] & {"jogo", "pneus", "incidente"}:
            v["avisou_invalida"] = True
            m = next(MOTIVOS[k] for k in ORDEM_MOTIVOS if k in v["motivos"])
            self._evento("invalida", volta=self.num + 1, motivo=m)
        if q.pneus_fora is not None and q.pneus_fora > 2:
            v["motivos"].add("pneus")
        if q.valida_jogo is False and q.atual_ms > 1500:
            v["motivos"].add("jogo")
        if v["p1"] is None and 1 / 3 <= q.npos < 0.6:
            v["p1"] = q.atual_ms
            self._evento_parcial(1, q)
        if v["p1"] is not None and v["p2"] is None and 2 / 3 <= q.npos < 0.95:
            v["p2"] = q.atual_ms
            self._evento_parcial(2, q)
        v["vel_max"] = max(v["vel_max"], q.vel)
        if t - v["t_amostra"] >= AMOSTRA_S:
            v["t_amostra"] = t
            xz = (q.x, q.z)
            if v["ult_xz"] is not None:
                d = math.dist(xz, v["ult_xz"])
                if d < 60:
                    v["dist"] += d
            v["ult_xz"] = xz
            v["amostras"].append([round(q.npos, 5), int(q.atual_ms), round(q.vel, 1), round(q.acel, 2),
                                  round(q.freio, 2), int(q.marcha), round(q.x, 1), round(q.z, 1)])

    def _evento_parcial(self, n, q):
        d = self._delta(q)
        if d is not None and self.v["limpo"] and not self.v["motivos"]:
            self._evento("parcial", parcial=n, delta_ms=d, volta=self.num + 1)

    def _fechar_volta(self, q):
        pd = self.pendente
        self.pendente = None
        v = pd["v"]
        tempo = pd["tempo_antes"]
        if q.ultima_ms > 0 and abs(q.ultima_ms - pd["tempo_antes"]) < 1500:
            tempo = q.ultima_ms
        motivos = set(v["motivos"])
        if not v["limpo"]:
            motivos.add("saida")
        valida = not motivos
        motivo = next((MOTIVOS[m] for m in ORDEM_MOTIVOS if m in motivos), None)
        p1 = v["p1"]
        p2 = (v["p2"] - v["p1"]) if (v["p1"] and v["p2"]) else None
        p3 = (tempo - v["p2"]) if v["p2"] else None
        if p3 is not None and p3 <= 0:
            p1 = p2 = p3 = None
        dist = q.extensao_m if (q.extensao_m and v["limpo"]) else v["dist"]
        comb = v["comb0"] - pd["comb_fim"]
        self.num += 1
        amostras = v["amostras"]
        if amostras:
            amostras.append([1.0, int(tempo)] + amostras[-1][2:])
        xz = [(a[6], a[7]) for a in amostras if len(a) > 7]
        if len(xz) > 20:
            xs, zs = [p[0] for p in xz], [p[1] for p in xz]
            if max(xs) - min(xs) > 50 or max(zs) - min(zs) > 50:
                passo = max(1, len(xz) // 160)
                self._contorno = [[round(x, 1), round(z, 1)] for x, z in xz[::passo]]
        recorde_pessoal = False
        if valida:
            ant = self.banco.q1(
                "SELECT MIN(v.tempo_ms) m FROM voltas v JOIN sessoes s ON s.id=v.sessao_id"
                " WHERE v.valida=1 AND s.jogo=? AND s.carro=? AND s.pista=?", self.chave[:3])
            recorde_pessoal = ant is None or ant["m"] is None or tempo < ant["m"]
        self.banco.nova_volta(self.sessao, {
            "numero": self.num, "tempo_ms": int(tempo), "valida": valida, "motivo": motivo,
            "p1": p1, "p2": p2, "p3": p3, "distancia_m": round(dist, 1),
            "combustivel": round(comb, 2) if 0 < comb < 50 else None, "vel_max": round(v["vel_max"], 1),
            "quando": v["quando"], "amostras": amostras})
        recorde_sessao = False
        if valida and (self.melhor_ms is None or tempo < self.melhor_ms):
            recorde_sessao = self.melhor_ms is not None
            self.melhor_ms = int(tempo)
            curva = [(a[0], a[1]) for a in amostras]
            curva.sort()
            self.melhor_curva = ([c[0] for c in curva], [c[1] for c in curva])
        melhor_antes = self.melhor_ms if not recorde_sessao else None
        with self.trava:
            self.evento += 1
            self.ultimo_evento = {"id": self.evento, "numero": self.num, "tempo_ms": int(tempo), "valida": valida,
                                  "motivo": motivo, "recorde_sessao": recorde_sessao,
                                  "recorde_pessoal": recorde_pessoal and valida}
        self._evento("volta", **{k: v for k, v in self.ultimo_evento.items() if k != "id"},
                     delta_melhor_ms=(int(tempo) - self.melhor_ms) if (valida and self.melhor_ms and melhor_antes) else None)
        # combustível: média das últimas voltas completas
        if 0 < comb < 50 and v["limpo"]:
            self._comb_por_volta = (self._comb_por_volta + [comb])[-5:]
            media = sum(self._comb_por_volta) / len(self._comb_por_volta)
            if media > 0 and pd["comb_fim"] > 0:
                self._evento("combustivel", voltas=round(pd["comb_fim"] / media, 1), por_volta=round(media, 2))
        # ritmo: a cada 3 voltas válidas, a média contra a melhor
        if valida:
            self._voltas_validas.append(int(tempo))
            if len(self._voltas_validas) % 3 == 0 and self.melhor_ms:
                ult = self._voltas_validas[-3:]
                self._evento("ritmo", delta_ms=int(sum(ult) / 3 - self.melhor_ms))
        log.info("volta %s: %s ms valida=%s %s", self.num, tempo, valida, motivo or "")

    def _delta(self, q):
        if not self.melhor_curva or not self.v or not self.v["limpo"]:
            return None
        xs, ts = self.melhor_curva
        if len(xs) < 5:
            return None
        k = bisect.bisect_left(xs, q.npos)
        if k <= 0 or k >= len(xs):
            return None
        x0, x1, t0, t1 = xs[k - 1], xs[k], ts[k - 1], ts[k]
        tb = t0 if x1 == x0 else t0 + (t1 - t0) * (q.npos - x0) / (x1 - x0)
        return int(q.atual_ms - tb)

    def _atualizar_ao_vivo(self, q):
        v = self.v
        motivo = None
        if v["motivos"] or not v["limpo"]:
            ms = set(v["motivos"]) | ({"saida"} if not v["limpo"] else set())
            motivo = next(MOTIVOS[m] for m in ORDEM_MOTIVOS if m in ms)
        with self.trava:
            self.ao_vivo = {
                "jogo": q.jogo, "carro": q.carro, "pista": q.pista, "tipo": q.tipo, "sessao_id": self.sessao,
                "vel": round(q.vel), "marcha": q.marcha, "rpm": q.rpm, "acel": round(q.acel, 2),
                "freio": round(q.freio, 2), "combustivel": round(q.combustivel, 1), "atual_ms": q.atual_ms,
                "npos": round(q.npos, 4), "volta": self.num + 1, "volta_valida": motivo is None, "motivo": motivo,
                "melhor_ms": self.melhor_ms, "delta_ms": self._delta(q), "p1": v["p1"],
                "p2": (v["p2"] - v["p1"]) if v["p1"] and v["p2"] else None,
                "ultima_ms": q.ultima_ms or None, "info": self._info_vivo(q),
            }

    def _info_vivo(self, q):
        """Dados extras do carro e da sessão para a tela Ao vivo (cada jogo manda o que tem)."""
        x = {k: v for k, v in (q.extra or {}).items() if k not in ("outros",) and v is not None}
        v = self.v or {}
        x["vel_max"] = round(v.get("vel_max", 0) or 0)
        if "previsao_ms" not in x and self.melhor_ms:
            d = self._delta(q)
            if d is not None:
                x["previsao_ms"] = int(self.melhor_ms + d)
        if "comb_por_volta" not in x and self._comb_por_volta:
            x["comb_por_volta"] = round(sum(self._comb_por_volta) / len(self._comb_por_volta), 2)
        cpv = x.get("comb_por_volta")
        if "voltas_comb" not in x and cpv and q.combustivel > 0:
            x["voltas_comb"] = round(q.combustivel / cpv, 1)
        if "voltas_restantes" not in x and x.get("voltas_total"):
            x["voltas_restantes"] = max(0, int(x["voltas_total"]) - self.num)
        contorno = getattr(self, "_contorno", None)
        completo = bool(contorno)
        if not contorno and v.get("amostras"):
            pts = [(a[6], a[7]) for a in v["amostras"] if len(a) > 7]
            passo = max(1, len(pts) // 160)
            contorno = [[round(a, 1), round(b, 1)] for a, b in pts[::passo]] if len(pts) > 5 else None
        if contorno and (q.x or q.z):
            x["mapa"] = {"contorno": contorno, "completo": completo, "eu": [round(q.x, 1), round(q.z, 1)],
                         "outros": (q.extra or {}).get("outros") or []}
        return x

    # ------------------------------------------------------------------ relatório
    def relatorio(self, texto):
        pasta = os.path.join(self.pasta, "relatorios")
        os.makedirs(pasta, exist_ok=True)
        nome = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".zip"
        caminho = os.path.join(pasta, nome)
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("descricao.txt", texto or "")
            z.writestr("status.json", json.dumps(self.foto_status(), ensure_ascii=False, indent=1, default=str))
            z.writestr("ao_vivo.json", json.dumps(self.foto_ao_vivo(), ensure_ascii=False, indent=1, default=str))
            arq_log = os.path.join(self.pasta, "axtel.log")
            if os.path.exists(arq_log):
                z.write(arq_log, "axtel.log")
            leitores = [self.ativo] if self.ativo else self.leitores
            for l in leitores:
                try:
                    if l is self.ativo or l.abrir():
                        for n, dados in l.despejo().items():
                            z.writestr(f"memoria/{n}.bin", dados)
                        if l is not self.ativo:
                            l.fechar()
                except Exception as e:
                    z.writestr(f"memoria/erro_{l.__class__.__name__}.txt", repr(e))
        log.info("relatório salvo: %s", caminho)
        return caminho
