"""Leitores dos outros jogos: iRacing, Automobilista 2, F1 25 e Forza.

iRacing e AMS2 usam memória compartilhada do Windows (como o Assetto Corsa).
F1 25 e Forza mandam a telemetria por UDP: o jogo precisa estar configurado
para enviar ao PC (veja o guia).
"""
import ctypes as C
import logging
import re
import socket
import struct
import threading
import time
import zlib

from .leitores import Leitor, Quadro, bonito, legivel, pct, volante
from .memoria import Pagina

log = logging.getLogger("axtel")


# =====================================================================
# iRacing — memória "Local\IRSDKMemMapFileName" (o mapa se descreve sozinho)
# =====================================================================
class LeitorIRacing(Leitor):
    jogo = "iRacing"
    TIPOS = {0: ("c", 1), 1: ("?", 1), 2: ("i", 4), 3: ("I", 4), 4: ("f", 4), 5: ("d", 8)}

    def __init__(self):
        super().__init__()
        self.mapa = Pagina("Local\\IRSDKMemMapFileName", 8 * 1024 * 1024)
        self.paginas = [self.mapa]
        self.vars = {}
        self._info_ver = -1
        self.info = {"carro": "", "pista": "", "sessoes": {}, "rpm_max": None, "carros": None}
        self._incidentes0 = None

    def fechar(self):
        super().fechar()
        self.vars = {}
        self._info_ver = -1

    def despejo(self):
        cab = self.mapa.ler_trecho(0, 112) or b""
        return {"irsdk_cabecalho": cab}

    def _cabecalho(self):
        b = self.mapa.ler_trecho(0, 112)
        if not b or len(b) < 112:
            return None
        v = struct.unpack_from("<10i", b, 0)
        bufs = [struct.unpack_from("<2i", b, 48 + 16 * k) for k in range(4)]
        return {"ver": v[0], "status": v[1], "info_ver": v[3], "info_len": v[4], "info_ofs": v[5],
                "nvars": v[6], "vars_ofs": v[7], "nbuf": v[8], "buflen": v[9], "bufs": bufs}

    def _carregar_vars(self, h):
        bruto = self.mapa.ler_trecho(h["vars_ofs"], 144 * h["nvars"]) or b""
        self.vars = {}
        for k in range(h["nvars"]):
            tipo, ofs, cont = struct.unpack_from("<3i", bruto, 144 * k)
            nome = bruto[144 * k + 16:144 * k + 48].split(b"\x00", 1)[0].decode("latin-1")
            self.vars[nome] = (tipo, ofs, cont)

    def _carregar_info(self, h):
        txt = (self.mapa.ler_trecho(h["info_ofs"], h["info_len"]) or b"").split(b"\x00", 1)[0].decode("latin-1", "ignore")
        def campo(nome, base=txt):
            m = re.search(r"^[ \t]*" + nome + r":[ \t]*(.*)$", base, re.M)
            return m.group(1).strip() if m else ""
        pista = campo("TrackDisplayName")
        config = campo("TrackConfigName")
        if config and config.lower() not in pista.lower():
            pista = f"{pista} {config}"
        carro = ""
        m = re.search(r"DriverCarIdx:[ \t]*(\d+)", txt)
        if m:
            idx = m.group(1)
            bloco = re.search(r"-[ \t]*CarIdx:[ \t]*" + idx + r"\b(.*?)(?=\n\s*-\s*CarIdx:|\Z)", txt, re.S)
            if bloco:
                carro = campo("CarScreenName", bloco.group(1))
        sessoes = {}
        for m in re.finditer(r"-\s*SessionNum:\s*(\d+)(.*?)(?=\n\s*-\s*SessionNum:|\Z)", txt, re.S):
            t = re.search(r"SessionType:[ \t]*(.*)", m.group(2))
            if t:
                sessoes[int(m.group(1))] = t.group(1).strip()
        rl = re.search(r"DriverCarRedLine:[ \t]*([\d.]+)", txt)
        carros = len(set(re.findall(r"-[ \t]*CarIdx:[ \t]*(\d+)", txt)))
        self.info = {"carro": carro, "pista": pista, "sessoes": sessoes,
                     "rpm_max": int(float(rl.group(1))) if rl else None, "carros": (carros - 1) if carros > 1 else None}
        self._info_ver = h["info_ver"]

    def _valor(self, buf, nome, padrao=0):
        v = self.vars.get(nome)
        if not v:
            return padrao
        tipo, ofs, _ = v
        fmt, n = self.TIPOS.get(tipo, ("i", 4))
        if ofs + n > len(buf):
            return padrao
        return struct.unpack_from("<" + fmt, buf, ofs)[0]

    def ler(self):
        h = self._cabecalho()
        if not h or h["nvars"] <= 0 or h["buflen"] <= 0:
            return None
        if not self.vars:
            self._carregar_vars(h)
        if h["info_ver"] != self._info_ver:
            self._carregar_info(h)
        tick, ofs = max(h["bufs"][:max(1, min(4, h["nbuf"]))], key=lambda x: x[0])
        buf = self.mapa.ler_trecho(ofs, h["buflen"]) or b""
        g = lambda n, d=0: self._valor(buf, n, d)
        conectado = bool(h["status"] & 1)
        if not conectado:
            status = "OFF"
        elif g("IsReplayPlaying", False):
            status = "REPLAY"
        elif g("IsOnTrack", False):
            status = "LIVE"
        else:
            status = "OFF"
        from .leitores import tipo_por_nome
        tipo = tipo_por_nome(self.info["sessoes"].get(int(g("SessionNum", 0)), ""))
        inc = int(g("PlayerCarMyIncidentCount", 0))
        superficie = int(g("PlayerTrackSurface", 3))
        ang = g("SteeringWheelAngle", None)
        ang_max = g("SteeringWheelAngleMax", None)
        flags = int(g("SessionFlags", 0) or 0)
        bandeira = ("quadriculada" if flags & 0x1 else "vermelha" if flags & 0x10 else "amarela" if flags & 0x4008 else
                    "azul" if flags & 0x20 else "branca" if flags & 0x2 else "verde" if flags & 0x4 else None)
        restante = g("SessionTimeRemain", None)
        voltas_rest = g("SessionLapsRemainEx", None)
        nn = lambda v: None if v is None else v
        extra = {
            "incidentes": inc,
            # no iRacing o ângulo positivo é para a esquerda; no Axtel, positivo é para a direita
            "volante": volante(-ang / ang_max) if ang is not None and ang_max else None,
            "volante_graus": int(round(-ang * 57.2958)) if ang is not None else None,
            "embreagem": pct(1.0 - g("Clutch", 1.0)), "rpm_max": self.info.get("rpm_max"),
            "posicao": int(g("PlayerCarPosition", 0)) or None, "carros": self.info.get("carros"),
            "tempo_restante_s": float(restante) if restante is not None and 0 < restante < 604800 else None,
            "voltas_restantes": int(voltas_rest) if voltas_rest is not None and 0 <= voltas_rest < 10000 else None,
            "bandeira": bandeira, "tc": nn(g("dcTractionControl", None)), "abs": nn(g("dcABS", None)),
            "bias_freio": (g("dcBrakeBias", 0) / 100.0) if 20 < (g("dcBrakeBias", 0) or 0) < 90 else None,
            "agua": round(g("WaterTemp", 0.0), 1) or None, "oleo": round(g("OilTemp", 0.0), 1) or None,
            "pista_temp": round(g("TrackTempCrew", 0.0), 1) or None, "ar_temp": round(g("AirTemp", 0.0), 1) or None,
            "comb_capacidade": round(g("FuelLevel", 0.0) / g("FuelLevelPct", 1.0), 1) if g("FuelLevelPct", 0.0) > 0.01 else None,
            "limitador": bool(int(g("EngineWarnings", 0) or 0) & 0x10),
        }
        return Quadro(
            jogo=self.jogo, status=status, pacote=int(tick), carro=self.info["carro"] or "Carro", pista=self.info["pista"] or "Pista",
            tipo=tipo, contador_voltas=int(g("LapCompleted", 0)), atual_ms=int(max(0.0, g("LapCurrentLapTime", 0.0)) * 1000),
            ultima_ms=int(max(0.0, g("LapLastLapTime", 0.0)) * 1000), melhor_ms=int(max(0.0, g("LapBestLapTime", 0.0)) * 1000),
            npos=float(g("LapDistPct", 0.0)) % 1.0, valida_jogo=None, pneus_fora=3 if superficie == 0 else 0,
            no_box=bool(g("OnPitRoad", False)), vel=float(g("Speed", 0.0)) * 3.6, acel=pct(g("Throttle", 0.0)),
            freio=pct(g("Brake", 0.0)), marcha=int(g("Gear", 0)), rpm=int(g("RPM", 0.0)), combustivel=float(g("FuelLevel", 0.0)),
            x=0.0, z=0.0, extra=extra,
        )


# =====================================================================
# Automobilista 2 — memória "$pcars2$" (formato do Project CARS 2)
# =====================================================================
class _ParticipanteAMS2(C.Structure):
    _fields_ = [("mIsActive", C.c_bool), ("mName", C.c_ubyte * 64), ("mWorldPosition", C.c_float * 3),
                ("mCurrentLapDistance", C.c_float), ("mRacePosition", C.c_uint32), ("mLapsCompleted", C.c_uint32),
                ("mCurrentLap", C.c_uint32), ("mCurrentSector", C.c_int32)]


class _MemoriaAMS2(C.Structure):
    _fields_ = [
        ("mVersion", C.c_uint32), ("mBuildVersionNumber", C.c_uint32), ("mGameState", C.c_uint32),
        ("mSessionState", C.c_uint32), ("mRaceState", C.c_uint32), ("mViewedParticipantIndex", C.c_int32),
        ("mNumParticipants", C.c_int32), ("mParticipantData", _ParticipanteAMS2 * 64),
        ("mUnfilteredThrottle", C.c_float), ("mUnfilteredBrake", C.c_float), ("mUnfilteredSteering", C.c_float),
        ("mUnfilteredClutch", C.c_float), ("mCarName", C.c_ubyte * 64), ("mCarClassName", C.c_ubyte * 64),
        ("mLapsInEvent", C.c_uint32), ("mTrackLocation", C.c_ubyte * 64), ("mTrackVariation", C.c_ubyte * 64),
        ("mTrackLength", C.c_float), ("mNumSectors", C.c_int32), ("mLapInvalidated", C.c_bool),
        ("mBestLapTime", C.c_float), ("mLastLapTime", C.c_float), ("mCurrentTime", C.c_float),
        ("mSplitTimeAhead", C.c_float), ("mSplitTimeBehind", C.c_float), ("mSplitTime", C.c_float),
        ("mEventTimeRemaining", C.c_float), ("mPersonalFastestLapTime", C.c_float), ("mWorldFastestLapTime", C.c_float),
    ] + [(f"mSetor{k}", C.c_float) for k in range(12)] + [  # 3 atuais, 3 mais rápidos, 3 pessoais, 3 mundiais
        ("mHighestFlagColour", C.c_uint32), ("mHighestFlagReason", C.c_uint32), ("mPitMode", C.c_uint32),
        ("mPitSchedule", C.c_uint32), ("mCarFlags", C.c_uint32), ("mOilTempCelsius", C.c_float),
        ("mOilPressureKPa", C.c_float), ("mWaterTempCelsius", C.c_float), ("mWaterPressureKPa", C.c_float),
        ("mFuelPressureKPa", C.c_float), ("mFuelLevel", C.c_float), ("mFuelCapacity", C.c_float), ("mSpeed", C.c_float),
        ("mRpm", C.c_float), ("mMaxRPM", C.c_float), ("mBrake", C.c_float), ("mThrottle", C.c_float),
        ("mClutch", C.c_float), ("mSteering", C.c_float), ("mGear", C.c_int32), ("mNumGears", C.c_int32),
    ]


class LeitorAMS2(Leitor):
    jogo = "Automobilista 2"
    ESTADOS = {2: "LIVE", 3: "PAUSE", 4: "PAUSE", 5: "OFF", 6: "REPLAY", 7: "REPLAY"}
    TIPOS = {1: "Treino", 2: "Teste", 3: "Classificação", 4: "Volta de apresentação", 5: "Corrida", 6: "Time attack"}

    def __init__(self):
        super().__init__()
        self.mem = Pagina("$pcars2$", C.sizeof(_MemoriaAMS2))
        self.paginas = [self.mem]

    def ler(self):
        b = self.mem.ler()
        if b is None:
            return None
        m = _MemoriaAMS2.from_buffer_copy(b)
        i = m.mViewedParticipantIndex if 0 <= m.mViewedParticipantIndex < 64 else 0
        p = m.mParticipantData[i]
        txt = lambda a: bytes(a).split(b"\x00", 1)[0].decode("utf-8", "ignore").strip()
        pista = txt(m.mTrackLocation)
        var = txt(m.mTrackVariation)
        if var and legivel(var) and var.lower() not in pista.lower():
            pista = f"{pista} {var}"
        ext = m.mTrackLength if 100 < m.mTrackLength < 40000 else 0.0
        npos = (p.mCurrentLapDistance / ext) % 1.0 if ext else 0.0
        seg = lambda x: int(x * 1000) if x and x > 0 else 0
        comb = m.mFuelLevel * m.mFuelCapacity if m.mFuelCapacity > 0 else m.mFuelLevel
        bandeiras = {1: "verde", 2: "azul", 3: "branca", 4: "branca", 5: "vermelha", 6: "amarela", 7: "amarela",
                     8: "preta", 9: "preta", 10: "preta", 11: "quadriculada"}
        resta = m.mEventTimeRemaining
        if resta > 86400:
            resta /= 1000.0
        extra = {
            "volante": volante(m.mSteering), "embreagem": pct(m.mClutch),
            "rpm_max": int(m.mMaxRPM) if m.mMaxRPM > 1000 else None,
            "posicao": int(p.mRacePosition) or None, "carros": int(m.mNumParticipants) if m.mNumParticipants > 0 else None,
            "voltas_total": int(m.mLapsInEvent) or None, "tempo_restante_s": float(resta) if resta > 0 else None,
            "gap_frente_ms": int(m.mSplitTimeAhead * 1000) if m.mSplitTimeAhead > 0 else None,
            "gap_tras_ms": int(m.mSplitTimeBehind * 1000) if m.mSplitTimeBehind > 0 else None,
            "bandeira": bandeiras.get(int(m.mHighestFlagColour)),
            "agua": round(m.mWaterTempCelsius, 1) or None, "oleo": round(m.mOilTempCelsius, 1) or None,
            "comb_capacidade": round(m.mFuelCapacity, 1) if m.mFuelCapacity > 0 else None,
            "classe": txt(m.mCarClassName) or None,
        }
        return Quadro(
            jogo=self.jogo, status=self.ESTADOS.get(m.mGameState, "OFF"), pacote=zlib.crc32(b[:7000]),
            carro=txt(m.mCarName) or "Carro", pista=bonito(pista) or "Pista", tipo=self.TIPOS.get(m.mSessionState, "Sessão"),
            contador_voltas=int(p.mLapsCompleted), atual_ms=seg(m.mCurrentTime), ultima_ms=seg(m.mLastLapTime),
            melhor_ms=seg(m.mBestLapTime), npos=float(npos), valida_jogo=not m.mLapInvalidated, pneus_fora=None,
            no_box=m.mPitMode in (1, 2, 3, 4, 5), vel=float(m.mSpeed) * 3.6, acel=pct(m.mThrottle), freio=pct(m.mBrake),
            marcha=int(m.mGear), rpm=int(m.mRpm), combustivel=float(comb), x=float(p.mWorldPosition[0]),
            z=float(p.mWorldPosition[2]), extensao_m=ext, extra=extra,
        )


# =====================================================================
# Leitores por UDP (F1 25 e Forza): uma linha de recepção por jogo
# =====================================================================
class LeitorUDP(Leitor):
    porta = 0

    def __init__(self, porta=None):
        super().__init__()
        self.porta = porta or self.porta
        self.ultimo = 0.0
        self.trava = threading.Lock()
        self.erro = None
        self.recebidos = 0
        self._amostra = b""
        threading.Thread(target=self._receber, daemon=True, name=f"udp-{self.porta}").start()

    def _receber(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", self.porta))
        except OSError as e:
            self.erro = f"A porta {self.porta} já está em uso por outro programa ({e})."
            log.warning("%s: %s", self.jogo, self.erro)
            return
        log.info("%s: ouvindo UDP na porta %s", self.jogo, self.porta)
        while True:
            try:
                dados, _ = s.recvfrom(4096)
            except OSError:
                time.sleep(0.5)
                continue
            with self.trava:
                try:
                    self.pacote_recebido(dados)
                    self.recebidos += 1
                    self.ultimo = time.time()
                    self._amostra = dados
                except Exception:
                    log.exception("%s: pacote não entendido", self.jogo)

    def abrir(self):
        return time.time() - self.ultimo < 2.0

    def fechar(self):
        pass

    def despejo(self):
        with self.trava:
            return {f"{self.jogo.replace(' ', '_')}_ultimo_pacote": self._amostra}


# ---------------- F1 25 (porta 20777, formato 2025) ----------------
PISTAS_F1 = {0: "Melbourne", 1: "Paul Ricard", 2: "Xangai", 3: "Bahrein", 4: "Barcelona", 5: "Mônaco", 6: "Montreal",
             7: "Silverstone", 8: "Hockenheim", 9: "Hungaroring", 10: "Spa-Francorchamps", 11: "Monza", 12: "Singapura",
             13: "Suzuka", 14: "Abu Dhabi", 15: "Austin", 16: "Interlagos", 17: "Red Bull Ring", 18: "Sochi",
             19: "Cidade do México", 20: "Baku", 21: "Bahrein (curto)", 22: "Silverstone (curto)", 23: "Austin (curto)",
             24: "Suzuka (curto)", 25: "Hanói", 26: "Zandvoort", 27: "Ímola", 28: "Portimão", 29: "Jeddah", 30: "Miami",
             31: "Las Vegas", 32: "Losail", 39: "Silverstone (invertido)", 40: "Red Bull Ring (invertido)",
             41: "Zandvoort (invertido)"}
EQUIPES_F1 = {0: "Mercedes", 1: "Ferrari", 2: "Red Bull", 3: "Williams", 4: "Aston Martin", 5: "Alpine", 6: "Racing Bulls",
              7: "Haas", 8: "McLaren", 9: "Sauber"}


def tipo_f1(n):
    if 1 <= n <= 4:
        return "Treino"
    if 5 <= n <= 14:
        return "Classificação"
    if 15 <= n <= 17:
        return "Corrida"
    if n == 18:
        return "Time trial"
    return "Sessão"


class LeitorF1(LeitorUDP):
    jogo = "F1 25"
    porta = 20777
    CAB = 29  # tamanho do cabeçalho

    def __init__(self, porta=None):
        self.s = {"pista": "Pista", "tipo": "Sessão", "ext": 0.0, "equipe": "", "lap": None, "tel": None, "pos": (0.0, 0.0),
                  "comb": 0.0, "frame": 0, "x": {}}
        super().__init__(porta)

    def pacote_recebido(self, d):
        if len(d) < self.CAB:
            return
        formato, = struct.unpack_from("<H", d, 0)
        pid = d[6]
        eu = d[27]
        self.s["frame"] = struct.unpack_from("<I", d, 23)[0]
        if formato != 2025 or eu > 21:
            return
        if pid == 1 and len(d) >= 37:  # sessão
            ext, = struct.unpack_from("<H", d, 33)
            self.s["ext"] = float(ext)
            self.s["tipo"] = tipo_f1(d[35])
            tid = struct.unpack_from("<b", d, 36)[0]
            self.s["pista"] = PISTAS_F1.get(tid, f"Pista {tid}")
            clima = {0: "Céu limpo", 1: "Poucas nuvens", 2: "Nublado", 3: "Chuva fraca", 4: "Chuva forte", 5: "Tempestade"}
            pista_t, ar_t = struct.unpack_from("<bb", d, 30)
            restante, = struct.unpack_from("<H", d, 38) if len(d) >= 40 else (0,)
            self.s["x"].update(clima=clima.get(d[29]), pista_temp=pista_t, ar_temp=ar_t, voltas_total=d[32] or None,
                               tempo_restante_s=restante or None)
        elif pid == 2:  # voltas: 57 bytes por carro
            o = self.CAB + 57 * eu
            if len(d) >= o + 57:
                ult, atual = struct.unpack_from("<II", d, o)
                dist, = struct.unpack_from("<f", d, o + 20)
                self.s["lap"] = {"ultima": ult, "atual": atual, "dist": dist, "volta": d[o + 33], "box": d[o + 34],
                                 "invalida": d[o + 37]}
                ms_f, min_f = struct.unpack_from("<HB", d, o + 14)
                self.s["x"].update(posicao=d[o + 32] or None, gap_frente_ms=(min_f * 60000 + ms_f) or None)
        elif pid == 6:  # telemetria: 60 bytes por carro
            o = self.CAB + 60 * eu
            if len(d) >= o + 60:
                vel, acel, vol, freio = struct.unpack_from("<Hfff", d, o)
                marcha, = struct.unpack_from("<b", d, o + 15)
                rpm, = struct.unpack_from("<H", d, o + 16)
                self.s["tel"] = (vel, acel, freio, marcha, rpm)
                ordem = (2, 3, 0, 1)  # o F1 manda TE, TD, DE, DD; o Axtel usa DE, DD, TE, TD
                freios = struct.unpack_from("<4H", d, o + 22)
                sup = d[o + 30:o + 34]
                psi = struct.unpack_from("<4f", d, o + 40)
                self.s["x"].update(volante=volante(vol), embreagem=d[o + 14] / 100.0, agua=struct.unpack_from("<H", d, o + 38)[0] or None,
                                   freios_temp=[freios[k] for k in ordem], pneus_temp=[sup[k] for k in ordem],
                                   pneus_psi=[round(psi[k], 1) for k in ordem])
        elif pid == 0:  # movimento: 60 bytes por carro
            o = self.CAB + 60 * eu
            if len(d) >= o + 12:
                x, _, z = struct.unpack_from("<fff", d, o)
                self.s["pos"] = (x, z)
        elif pid == 7:  # status do carro: 55 bytes por carro
            o = self.CAB + 55 * eu
            if len(d) >= o + 9:
                self.s["comb"], = struct.unpack_from("<f", d, o + 5)
            if len(d) >= o + 27:
                cap, voltas_comb = struct.unpack_from("<ff", d, o + 9)
                rpm_max, = struct.unpack_from("<H", d, o + 17)
                compostos = {16: "macio", 17: "médio", 18: "duro", 7: "intermediário", 8: "chuva"}
                self.s["x"].update(tc=d[o] or None, abs=d[o + 1] or None, bias_freio=d[o + 3] / 100.0 if d[o + 3] else None,
                                   limitador=bool(d[o + 4]), comb_capacidade=round(cap, 1) if cap > 0 else None,
                                   voltas_comb=round(voltas_comb, 1) if voltas_comb else None, rpm_max=rpm_max or None,
                                   composto=compostos.get(d[o + 26]))
        elif pid == 4:  # participantes: 57 bytes por carro, depois de 1 byte
            o = self.CAB + 1 + 57 * eu
            if len(d) >= o + 4:
                self.s["equipe"] = EQUIPES_F1.get(d[o + 3], "")
                self.s["x"]["carros"] = d[self.CAB] or None

    def ler(self):
        with self.trava:
            s = dict(self.s)
            s["x"] = dict(self.s["x"])
        lap, tel = s["lap"], s["tel"]
        if not lap or not tel:
            return None
        ext = s["ext"]
        npos = (lap["dist"] / ext) % 1.0 if ext and lap["dist"] >= 0 else 0.0
        return Quadro(
            jogo=self.jogo, status="LIVE", pacote=s["frame"], carro=f"F1 · {s['equipe']}" if s["equipe"] else "F1",
            pista=s["pista"], tipo=s["tipo"], contador_voltas=max(0, lap["volta"] - 1), atual_ms=lap["atual"],
            ultima_ms=lap["ultima"], melhor_ms=0, npos=npos, valida_jogo=not lap["invalida"], pneus_fora=None,
            no_box=lap["box"] != 0, vel=float(tel[0]), acel=pct(tel[1]), freio=pct(tel[2]), marcha=int(tel[3]),
            rpm=int(tel[4]), combustivel=float(s["comb"]), x=float(s["pos"][0]), z=float(s["pos"][1]), extensao_m=ext,
            extra=s["x"],
        )


# ---------------- Forza (Data Out, porta 5300) ----------------
class LeitorForza(LeitorUDP):
    jogo = "Forza"
    porta = 5300

    def __init__(self, porta=None):
        self.ultimo_pacote = None
        self.versao = ""
        self.inicio_volta_m = 0.0
        self.ext_volta = 0.0
        self.volta_ant = None
        super().__init__(porta)

    def pacote_recebido(self, d):
        n = len(d)
        if n == 311 or n == 331:      # Forza Motorsport 7 / Forza Motorsport (2023)
            base, self.versao = 232, "Forza Motorsport"
        elif n == 324:                # Forza Horizon 4 e 5
            base, self.versao = 244, "Forza Horizon"
        else:
            return
        corrida, = struct.unpack_from("<i", d, 0)
        rpm, = struct.unpack_from("<f", d, 16)
        carro, = struct.unpack_from("<i", d, 212)
        x, _, z = struct.unpack_from("<fff", d, base)
        vel, = struct.unpack_from("<f", d, base + 12)
        comb, dist, melhor, ultima, atual = struct.unpack_from("<5f", d, base + 44)
        volta, = struct.unpack_from("<H", d, base + 68)
        acel, freio = d[base + 71], d[base + 72]
        marcha = d[base + 75]
        rpm_max, = struct.unpack_from("<f", d, 8)
        pneus_f = struct.unpack_from("<4f", d, base + 24)
        vol = struct.unpack_from("<b", d, base + 76)[0]
        extra = {"volante": volante(vol / 127.0), "embreagem": d[base + 73] / 255.0, "rpm_max": int(rpm_max) if rpm_max > 1000 else None,
                 "posicao": d[base + 70] or None,
                 "pneus_temp": [round((t - 32) / 1.8, 1) for t in pneus_f] if any(pneus_f) else None}
        pista = struct.unpack_from("<i", d, base + 95)[0] if n == 331 else None
        if self.volta_ant is not None and volta == self.volta_ant + 1:
            self.ext_volta = dist - self.inicio_volta_m if dist - self.inicio_volta_m > 200 else self.ext_volta
            self.inicio_volta_m = dist
        elif self.volta_ant is None or volta < self.volta_ant:
            self.inicio_volta_m = dist
        self.volta_ant = volta
        self.ultimo_pacote = {"corrida": corrida, "rpm": rpm, "carro": carro, "x": x, "z": z, "vel": vel, "comb": comb,
                              "dist": dist, "melhor": melhor, "ultima": ultima, "atual": atual, "volta": volta,
                              "acel": acel, "freio": freio, "marcha": marcha, "pista": pista, "extra": extra,
                              "ts": struct.unpack_from("<I", d, 4)[0]}

    def ler(self):
        with self.trava:
            p = dict(self.ultimo_pacote) if self.ultimo_pacote else None
            ext = self.ext_volta
            ini = self.inicio_volta_m
        if not p:
            return None
        npos = ((p["dist"] - ini) / ext) % 1.0 if ext > 0 else 0.0
        ms = lambda s: int(s * 1000) if s and s > 0 else 0
        marcha = -1 if p["marcha"] == 0 else int(p["marcha"])
        return Quadro(
            jogo=self.jogo, status="LIVE" if p["corrida"] else "OFF", pacote=p["ts"],
            carro=f"{self.versao} · carro {p['carro']}", pista=f"Pista {p['pista']}" if p["pista"] is not None else self.versao,
            tipo="Sessão", contador_voltas=int(p["volta"]), atual_ms=ms(p["atual"]), ultima_ms=ms(p["ultima"]),
            melhor_ms=ms(p["melhor"]), npos=npos, valida_jogo=None, pneus_fora=None, no_box=False,
            vel=float(p["vel"]) * 3.6, acel=p["acel"] / 255.0, freio=p["freio"] / 255.0, marcha=marcha,
            rpm=int(p["rpm"]), combustivel=float(p["comb"]) * 100.0, x=float(p["x"]), z=float(p["z"]), extensao_m=0.0,
            extra=p.get("extra") or {},
        )
