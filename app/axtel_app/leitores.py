"""Leitores por jogo. Cada leitor transforma as páginas de memória em um Quadro
(um retrato do carro naquele instante), igual para todos os jogos."""
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from . import estruturas as E
from .memoria import Pagina

STATUS = {0: "OFF", 1: "REPLAY", 2: "LIVE", 3: "PAUSE"}


@dataclass
class Quadro:
    jogo: str
    status: str
    pacote: int
    carro: str
    pista: str
    tipo: str
    contador_voltas: Optional[int]
    atual_ms: int
    ultima_ms: int
    melhor_ms: int
    npos: float
    valida_jogo: Optional[bool]   # o jogo diz se a volta é válida (None = jogo não informa)
    pneus_fora: Optional[int]     # quantos pneus fora da pista (None = jogo não informa)
    no_box: bool
    vel: float
    acel: float
    freio: float
    marcha: int                   # -1 ré, 0 neutro, 1.. marchas
    rpm: int
    combustivel: float
    x: float
    z: float
    extensao_m: float = 0.0
    extra: dict = field(default_factory=dict)


def texto16(arr):
    bruto = bytes(bytearray(memoryview(arr).cast("B")))
    return bruto.decode("utf-16-le", "ignore").split("\x00", 1)[0].strip()


def texto8(arr):
    return bytes(arr).split(b"\x00", 1)[0].decode("utf-8", "ignore").strip()


def legivel(s):
    return bool(s) and len(s) < 64 and all(ch.isprintable() for ch in s)


def volante(v):
    """Posição do volante de -1 (tudo para a esquerda) a 1 (tudo para a direita)."""
    v = float(v)
    if abs(v) > 1.5:
        v /= 100.0
    return max(-1.0, min(1.0, v))


def pct(v):
    v = float(v)
    if v > 1.5:
        v /= 100.0
    return max(0.0, min(1.0, v))


def bonito(nome):
    """ks_porsche_911_gt3_rs -> Porsche 911 Gt3 Rs (mantém nomes já bonitos)."""
    if not nome or " " in nome:
        return nome
    partes = [p for p in nome.replace("-", "_").split("_") if p and p.lower() not in ("ks", "rss")]
    return " ".join(p.upper() if len(p) <= 3 and any(c.isdigit() for c in p) else p.capitalize() for p in partes) or nome


TIPOS_AC = {0: "Treino", 1: "Classificação", 2: "Corrida", 3: "Hotlap", 4: "Time attack", 5: "Drift", 6: "Drag"}
TIPOS_ACC = {0: "Treino", 1: "Classificação", 2: "Corrida", 3: "Hotlap", 4: "Hotstint", 5: "Superpole"}


def tipo_por_nome(nome):
    n = (nome or "").lower()
    for chave, rot in (("practice", "Treino"), ("treino", "Treino"), ("qualif", "Classificação"),
                       ("race", "Corrida"), ("corrida", "Corrida"), ("hot", "Hotlap"),
                       ("time attack", "Time attack"), ("trial", "Time attack")):
        if chave in n:
            return rot
    return nome.strip().capitalize() if legivel(nome or "") else "Sessão"


class Leitor:
    jogo = "?"

    def __init__(self):
        self.paginas = []

    def abrir(self):
        return all(p.abrir() for p in self.paginas)

    def fechar(self):
        for p in self.paginas:
            p.fechar()

    @property
    def acesso_negado(self):
        """O jogo criou a memória, mas o Windows não deixou o Axtel abrir (jogo rodando como administrador)."""
        return any(getattr(p, "erro", 0) == 5 for p in getattr(self, "paginas", []))

    def despejo(self):
        """Bytes crus das páginas, para o relatório de problema."""
        return {p.nome.split("\\")[-1]: (p.ler() or b"") for p in self.paginas}

    def ler(self) -> Optional[Quadro]:
        raise NotImplementedError


def _processo_rodando(nome_exe):
    if sys.platform != "win32":
        return False
    try:
        saida = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {nome_exe}", "/NH"], capture_output=True,
                               text=True, timeout=5, creationflags=0x08000000).stdout
        return nome_exe.lower() in saida.lower()
    except Exception:
        return None  # não deu para saber


class LeitorACClassico(Leitor):
    """Assetto Corsa (1) e Assetto Corsa Competizione — mesmas páginas acpmf_*."""

    def __init__(self):
        super().__init__()
        self.fis = Pagina("Local\\acpmf_physics", E.ctypes_sizeof(E.FisicaAC))
        self.gra = Pagina("Local\\acpmf_graphics", E.ctypes_sizeof(E.GraficosACC))
        self.est = Pagina("Local\\acpmf_static", E.ctypes_sizeof(E.EstaticoAC))
        self.paginas = [self.fis, self.gra, self.est]
        self._acc = None
        self._acc_quando = 0
        self.jogo = "Assetto Corsa"

    def _e_acc(self):
        # Uma vez visto o ACC, fica ACC até a memória ser solta: uma falha momentânea do
        # tasklist não pode trocar o nome do jogo no meio da volta (isso abria outra sessão).
        agora = time.time()
        if not self._acc and (self._acc is None or agora - self._acc_quando > 15):
            r = _processo_rodando("AC2-Win64-Shipping.exe")
            if r is not None:
                self._acc = r
            self._acc_quando = agora
        return bool(self._acc)

    def fechar(self):
        super().fechar()
        self._acc = None

    def ler(self):
        bf, bg, bs = self.fis.ler(), self.gra.ler(), self.est.ler()
        if bf is None or bg is None or bs is None:
            return None
        acc = self._e_acc()
        self.jogo = "ACC" if acc else "Assetto Corsa"
        fi = E.FisicaAC.from_buffer_copy(bf)
        if acc:
            g = E.GraficosACC.from_buffer_copy(bg)
            idx = 0
            for k in range(max(0, min(60, g.activeCars))):
                if g.carID[k] == g.playerCarID:
                    idx = k
                    break
            x, z = g.carCoordinates[idx][0], g.carCoordinates[idx][2]
            tipos = TIPOS_ACC
        else:
            g = E.GraficosAC.from_buffer_copy(bg[:E.ctypes_sizeof(E.GraficosAC)])
            x, z = g.carCoordinates[0], g.carCoordinates[2]
            tipos = TIPOS_AC
        s = E.EstaticoAC.from_buffer_copy(bs)
        lista = lambda a: [round(float(v), 1) for v in a]
        extra = {
            "volante": volante(fi.steerAngle),
            "posicao": int(g.position) or None, "voltas_total": int(g.numberOfLaps) or None,
            "tempo_restante_s": (g.sessionTimeLeft / 1000.0) if g.sessionTimeLeft > 0 else None,
            "pneus_temp": lista(fi.tyreCoreTemperature) if any(fi.tyreCoreTemperature) else None,
            "pneus_psi": lista(fi.wheelsPressure) if any(fi.wheelsPressure) else None,
            "composto": texto16(g.tyreCompound) or None, "limitador": bool(fi.pitLimiterOn),
        }
        return Quadro(
            jogo=self.jogo, status=STATUS.get(g.status, "OFF"), pacote=g.packetId,
            carro=bonito(texto16(s.carModel)), pista=bonito(texto16(s.track)),
            tipo=tipos.get(g.session, "Sessão"), contador_voltas=g.completedLaps,
            atual_ms=g.iCurrentTime, ultima_ms=g.iLastTime, melhor_ms=g.iBestTime,
            npos=float(g.normalizedCarPosition), valida_jogo=None, pneus_fora=fi.numberOfTyresOut,
            no_box=bool(g.isInPit), vel=float(fi.speedKmh), acel=pct(fi.gas), freio=pct(fi.brake),
            marcha=fi.gear - 1, rpm=fi.rpms, combustivel=float(fi.fuel), x=float(x), z=float(z), extra=extra,
        )


class LeitorACEvo(Leitor):
    jogo = "AC EVO"

    def __init__(self):
        super().__init__()
        self.gra = Pagina("Local\\acevo_pmf_graphics", E.ctypes_sizeof(E.GraficosEvo))
        self.est = Pagina("Local\\acevo_pmf_static", E.ctypes_sizeof(E.EstaticoEvo))
        self.fis = Pagina("Local\\acevo_pmf_physics", 1024)  # só para o relatório de problema
        self.paginas = [self.gra, self.est]

    def despejo(self):
        d = super().despejo()
        if self.fis.abrir():
            d["acevo_pmf_physics"] = self.fis.ler() or b""
        return d

    def fechar(self):
        super().fechar()
        self.fis.fechar()

    def ler(self):
        bg, bs = self.gra.ler(), self.est.ler()
        if bg is None or bs is None:
            return None
        g = E.GraficosEvo.from_buffer_copy(bg)
        s = E.EstaticoEvo.from_buffer_copy(bs)
        idx = 0
        n = max(1, min(60, int(g.active_cars) or 60))
        for k in range(n):
            if g.car_ids[k][0] == g.player_car_id_a and g.car_ids[k][1] == g.player_car_id_b and g.player_car_id_a:
                idx = k
                break
        pista = texto8(s.track)
        config = texto8(s.track_configuration)
        if config and legivel(config) and config.lower() not in pista.lower():
            pista = f"{pista} {config}"
        invalida = bool(g.timing_state.is_invalid) or not bool(g.is_valid_lap)
        pneus = [g.tyre_lf, g.tyre_rf, g.tyre_lr, g.tyre_rr]
        r1 = lambda v: round(float(v), 1)
        el = g.electronics
        bandeiras = {0: None, 1: "azul", 2: "amarela", 3: "preta", 4: "branca", 5: "quadriculada", 6: "penalidade", 7: "verde"}
        outros = []
        for k in range(min(60, int(g.active_cars or 0))):
            if k != idx:
                outros.append([round(float(g.car_coordinates[k][0]), 1), round(float(g.car_coordinates[k][2]), 1)])
        extra = {
            "volante": volante(g.steering_percent), "volante_graus": int(g.steer_degrees) if g.steer_degrees else None,
            "embreagem": pct(g.clutch_percent), "rpm_max": int(round(g.rpm / g.rpm_percent / 10.0) * 10) if g.rpm_percent > 0.05 else None,
            "posicao": int(g.current_pos) or None, "carros": int(g.total_drivers) or None,
            "voltas_total": int(g.session_state.total_lap) or None,
            "tempo_restante_s": g.session_state.time_left_ms / 1000.0 if g.session_state.time_left_ms > 0 else None,
            "gap_frente_ms": int(g.gap_ahead * 1000) if g.gap_ahead > 0 else None,
            "gap_tras_ms": int(g.gap_behind * 1000) if g.gap_behind > 0 else None,
            "bandeira": bandeiras.get(int(g.flag)), "tc": int(el.tc_level) or None, "abs": int(el.abs_level) or None,
            "bias_freio": float(el.brake_bias) if 0.2 < el.brake_bias < 0.9 else None,
            "agua": int(g.water_temperature_c) or None, "oleo": r1(g.oil_temperature_c) or None,
            "pneus_temp": [r1(t.tyre_temperature_c) for t in pneus], "pneus_psi": [r1(t.tyre_pressure) for t in pneus],
            "freios_temp": [round(float(t.brake_temperature_c)) for t in pneus],
            "composto": texto8(g.tyre_lf.tyre_compound_front) or None,
            "ar_temp": int(g.air_temperature_c) or None, "pista_temp": r1(s.starting_ground_temperature_c) or None,
            "comb_por_volta": r1(g.fuel_per_lap) if g.fuel_per_lap > 0 else None,
            "comb_capacidade": r1(g.max_fuel) if g.max_fuel > 0 else None,
            "previsao_ms": int(g.predicted_lap_time_ms) if g.predicted_lap_time_ms > 0 else None,
            "limitador": bool(el.is_pitlimiter_on), "outros": outros[:40],
        }
        return Quadro(
            jogo=self.jogo, status=STATUS.get(g.status, "OFF"), pacote=g.packet_id,
            carro=bonito(texto8(g.car_model_name)), pista=bonito(pista),
            tipo=tipo_por_nome(texto8(s.session_name)), contador_voltas=g.total_lap_count,
            atual_ms=g.current_lap_time_ms, ultima_ms=g.last_laptime_ms, melhor_ms=g.best_laptime_ms,
            npos=float(g.npos), valida_jogo=not invalida, pneus_fora=None,
            no_box=bool(g.is_in_pit_box or g.is_in_pit_lane), vel=float(g.display_speed_kmh),
            acel=pct(g.gas_percent), freio=pct(g.brake_percent), marcha=int(g.gear_int), rpm=int(g.rpm),
            combustivel=float(g.fuel_liter_current_quantity), x=float(g.car_coordinates[idx][0]),
            z=float(g.car_coordinates[idx][2]), extensao_m=float(s.track_length_m) if 100 < s.track_length_m < 40000 else 0.0,
            extra=extra,
        )


def todos_os_leitores(portas=None):
    # A ordem importa: o EVO vem primeiro (os Assetto Corsa compartilham o formato).
    from .leitores_extra import LeitorAMS2, LeitorF1, LeitorForza, LeitorIRacing
    portas = portas or {}
    return [LeitorACEvo(), LeitorACClassico(), LeitorIRacing(), LeitorAMS2(),
            LeitorF1(portas.get("f1")), LeitorForza(portas.get("forza"))]


JOGOS_SUPORTADOS = ["AC EVO", "Assetto Corsa", "ACC", "iRacing", "Automobilista 2", "F1 25", "Forza"]
JOGOS_FUTUROS = []
