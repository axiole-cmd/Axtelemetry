"""Teste de ponta a ponta: imita a memória compartilhada dos jogos e roda o Axtel de verdade.
Uso: python simulador.py PASTA_DADOS PORTA"""
import ctypes as C
import math
import os
import random
import sys
import threading
import time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, RAIZ)

from axtel_app import estruturas as E  # noqa: E402
from axtel_app.banco import Banco  # noqa: E402
from axtel_app.coletor import Coletor  # noqa: E402
from axtel_app.memoria import SIMULADOS  # noqa: E402
from axtel_app.config import Config  # noqa: E402
from axtel_app.servidor import Api, criar_servidor  # noqa: E402
from axtel_app.sistema import Backups  # noqa: E402
from axtel_app.voz import Voz  # noqa: E402

ESCALA = 10  # 1 s real = 10 s de jogo (voltas de ~9 s reais viram ~1:30)


def pista(npos):
    a = npos * 2 * math.pi
    return 600 * math.cos(a) + 120 * math.cos(3 * a), 380 * math.sin(a) + 60 * math.sin(2 * a)


def vel(npos, ritmo):
    return (150 + 90 * abs(math.sin(npos * 2 * math.pi * 3))) * ritmo


def put8(arr, s):
    b = s.encode()[: len(arr) - 1]
    for i in range(len(arr)):
        arr[i] = b[i] if i < len(b) else 0


def put16(arr, s):
    b = s.encode("utf-16-le")
    vals = [b[i] | (b[i + 1] << 8) for i in range(0, len(b), 2)][: len(arr) - 1]
    for i in range(len(arr)):
        arr[i] = vals[i] if i < len(vals) else 0


class Evo:
    def __init__(self, carro, pista_, sessao):
        self.g = E.GraficosEvo()
        self.s = E.EstaticoEvo()
        put8(self.g.car_model_name, carro)
        put8(self.s.track, pista_)
        put8(self.s.session_name, sessao)
        self.s.track_length_m = 4309
        self.g.player_car_id_a = 7
        self.g.car_ids[0][0] = 7
        self.g.active_cars = 1

    def escrever(self, st):
        g = self.g
        g.packet_id += 1
        g.status = st["status"]
        g.npos = st["npos"]
        g.current_lap_time_ms = st["cur"]
        g.last_laptime_ms = st["last"]
        g.best_laptime_ms = st["best"]
        g.total_lap_count = st["voltas"]
        g.is_valid_lap = st["valida"]
        g.is_in_pit_lane = st["box"]
        g.display_speed_kmh = int(st["vel"])
        g.gear_int = st["marcha"]
        g.gas_percent = st["acel"]
        g.brake_percent = st["freio"]
        g.fuel_liter_current_quantity = st["comb"]
        import math as _m
        curva = _m.sin(st["npos"] * 2 * _m.pi * 5)
        g.rpm = int(4500 + 3500 * st["acel"])
        g.rpm_percent = g.rpm / 9250
        g.steering_percent = curva * 0.35
        g.steer_degrees = int(curva * 0.35 * 450)
        g.clutch_percent = 0.0
        g.current_pos, g.total_drivers = 4, 18
        g.session_state.total_lap = 20
        g.session_state.time_left_ms = max(0, 1800000 - st["voltas"] * 90000 - st["cur"])
        g.gap_ahead, g.gap_behind = 1.204, 0.688
        g.flag = 7
        g.electronics.tc_level, g.electronics.abs_level, g.electronics.brake_bias = 3, 2, 0.56
        g.water_temperature_c, g.oil_temperature_c, g.air_temperature_c = 88, 104.0, 24
        for k, t in enumerate((g.tyre_lf, g.tyre_rf, g.tyre_lr, g.tyre_rr)):
            t.tyre_temperature_c = (86, 94, 82, 88)[k]
            t.tyre_pressure = (27.4, 27.9, 27.1, 27.5)[k]
            t.brake_temperature_c = (420, 445, 310, 330)[k]
        g.fuel_per_lap, g.max_fuel = 2.9, 90.0
        self.s.starting_ground_temperature_c = 32.0
        x, z = pista(st["npos"])
        g.car_coordinates[0][0] = x
        g.car_coordinates[0][2] = z
        g.active_cars = 3
        for k, dn in ((1, 0.08), (2, -0.05)):
            ox, oz = pista((st["npos"] + dn) % 1.0)
            g.car_coordinates[k][0], g.car_coordinates[k][2] = ox, oz
        SIMULADOS["Local\\acevo_pmf_graphics"] = bytearray(bytes(g))
        SIMULADOS["Local\\acevo_pmf_static"] = bytearray(bytes(self.s))


class Classico:
    def __init__(self, carro, pista_, sessao):
        self.f = E.FisicaAC()
        self.g = E.GraficosAC()
        self.s = E.EstaticoAC()
        put16(self.s.carModel, carro)
        put16(self.s.track, pista_)
        self.g.session = sessao

    def escrever(self, st):
        f, g = self.f, self.g
        f.packetId += 1
        g.packetId += 1
        g.status = st["status"]
        g.normalizedCarPosition = st["npos"]
        g.iCurrentTime = st["cur"]
        # Repique real do AC/ACC (visto no PC do Léo): logo depois de zerar na linha, um quadro ainda
        # traz o tempo da volta anterior. Reproduzimos isso para garantir que a volta seguinte fica válida.
        ant = getattr(self, "cur_ant", 0)
        if getattr(self, "repique", 0):
            g.iCurrentTime = self.repique
            self.repique = 0
        elif st["cur"] < 500 and ant > 10000:
            self.repique = ant + 20
        self.cur_ant = st["cur"]
        g.iLastTime = st["last"]
        g.iBestTime = st["best"]
        g.completedLaps = st["voltas"]
        g.isInPit = 1 if st["box"] else 0
        f.numberOfTyresOut = 0 if st["valida"] else 3
        f.speedKmh = st["vel"]
        f.gear = st["marcha"] + 1
        f.gas = st["acel"]
        f.brake = st["freio"]
        f.fuel = st["comb"]
        x, z = pista(st["npos"])
        g.carCoordinates[0] = x
        g.carCoordinates[2] = z
        gb = bytearray(C.sizeof(E.GraficosACC))
        gb[: C.sizeof(g)] = bytes(g)
        SIMULADOS["Local\\acpmf_physics"] = bytearray(bytes(f))
        SIMULADOS["Local\\acpmf_graphics"] = gb
        SIMULADOS["Local\\acpmf_static"] = bytearray(bytes(self.s))


def correr(jogo, voltas, ritmos, invalidas=(), passo=0.02):
    st = {"status": 2, "npos": 0.82, "cur": 0, "last": 0, "best": 0, "voltas": 0, "valida": True, "box": True,
          "vel": 60, "marcha": 2, "acel": 0.5, "freio": 0, "comb": 60.0}
    volta = 0  # 0 = volta de saída
    ritmo = 0.8
    while volta <= voltas:
        v = vel(st["npos"], ritmo)
        # avança: velocidade relativa -> fração da volta
        st["npos"] += (v / 200) * passo * ESCALA / 95 * 1.0
        st["cur"] += int(passo * 1000 * ESCALA)
        st["vel"] = v
        st["box"] = volta == 0 and st["npos"] < 0.9
        curva = math.sin(st["npos"] * 2 * math.pi * 3)
        st["acel"] = max(0.0, min(1.0, 0.5 + curva))
        st["freio"] = max(0.0, min(1.0, -curva - 0.4))
        st["marcha"] = max(1, min(6, int(v / 45)))
        st["comb"] -= 0.0004
        st["valida"] = not (volta in invalidas and 0.4 < st["npos"] < 0.45)
        if st["npos"] >= 1.0:
            st["npos"] -= 1.0
            st["last"] = st["cur"]
            if volta > 0 and volta not in invalidas and (not st["best"] or st["cur"] < st["best"]):
                st["best"] = st["cur"]
            st["cur"] = 0
            st["voltas"] += 1
            volta += 1
            ritmo = ritmos[min(volta - 1, len(ritmos) - 1)] if volta >= 1 else 0.8
            st["valida"] = True
        jogo.escrever(st)
        time.sleep(passo)
    # sai para o menu
    st["status"] = 0
    jogo.escrever(st)


# ---------------------------------------------------------------- jogos novos
import socket as _socket
import struct as _st
from axtel_app import leitores_extra as X  # noqa: E402


class AMS2:
    def __init__(self, carro, pista):
        self.m = X._MemoriaAMS2()
        put8(self.m.mCarName, carro)
        put8(self.m.mTrackLocation, pista)
        self.m.mTrackLength = 4309.0
        self.m.mNumParticipants = 1
        self.m.mSessionState = 1
        self.m.mFuelCapacity = 100.0
        self.n = 0

    def escrever(self, st):
        m = self.m
        self.n += 1
        m.mGameState = 2 if st["status"] == 2 else 1
        m.mCurrentTime = st["cur"] / 1000
        m.mLastLapTime = st["last"] / 1000
        m.mBestLapTime = st["best"] / 1000
        m.mLapInvalidated = not st["valida"]
        m.mPitMode = 1 if st["box"] else 0
        m.mSpeed = st["vel"] / 3.6
        m.mGear = st["marcha"]
        m.mThrottle = st["acel"]
        m.mBrake = st["freio"]
        m.mFuelLevel = st["comb"] / 100
        m.mRpm = 6000 + self.n % 7
        m.mMaxRPM = 8500.0
        m.mSteering = 0.3 * math.sin(st["npos"] * 31)
        m.mParticipantData[0].mRacePosition = 5
        p = m.mParticipantData[0]
        p.mIsActive = True
        p.mLapsCompleted = st["voltas"]
        p.mCurrentLapDistance = st["npos"] * 4309.0
        x, z = pista(st["npos"])
        p.mWorldPosition[0] = x
        p.mWorldPosition[2] = z
        SIMULADOS["$pcars2$"] = bytearray(bytes(m))


class IRacing:
    VARS = [("SessionNum", 2), ("IsOnTrack", 1), ("IsReplayPlaying", 1), ("LapCompleted", 2), ("LapCurrentLapTime", 4),
            ("LapLastLapTime", 4), ("LapBestLapTime", 4), ("LapDistPct", 4), ("OnPitRoad", 1), ("Speed", 4), ("Throttle", 4),
            ("Brake", 4), ("Gear", 2), ("RPM", 4), ("FuelLevel", 4), ("PlayerCarMyIncidentCount", 2), ("PlayerTrackSurface", 2),
            ("PlayerCarPosition", 2), ("WaterTemp", 4), ("SteeringWheelAngle", 4), ("SteeringWheelAngleMax", 4)]
    FMT = {1: "?", 2: "i", 4: "f"}

    def __init__(self, carro, pista_):
        info = ("WeekendInfo:\n TrackDisplayName: %s\n TrackConfigName: \nDriverInfo:\n DriverCarIdx: 0\n Drivers:\n"
                " - CarIdx: 0\n   CarScreenName: %s\nSessionInfo:\n Sessions:\n - SessionNum: 0\n   SessionType: Practice\n") % (pista_, carro)
        self.info = info.encode("latin-1")
        self.ofs = {}
        o = 0
        for nome, t in self.VARS:
            self.ofs[nome] = o
            o += 4
        self.buflen = o
        self.tick = 0
        self.inc = 0

    def escrever(self, st):
        self.tick += 1
        h_vars, h_info, h_buf = 112, 112 + 144 * len(self.VARS), 4096
        b = bytearray(h_buf + self.buflen * 2)
        _st.pack_into("<10i", b, 0, 2, 1 if st["status"] == 2 else 0, 60, 1, len(self.info), h_info, len(self.VARS), h_vars, 1, self.buflen)
        _st.pack_into("<2i", b, 48, self.tick, h_buf)
        for k, (nome, t) in enumerate(self.VARS):
            _st.pack_into("<3i", b, h_vars + 144 * k, t, self.ofs[nome], 1)
            b[h_vars + 144 * k + 16:h_vars + 144 * k + 16 + len(nome)] = nome.encode()
        b[h_info:h_info + len(self.info)] = self.info
        if not st["valida"]:
            self.inc_volta = True
        v = {"SessionNum": 0, "IsOnTrack": st["status"] == 2, "IsReplayPlaying": False, "LapCompleted": st["voltas"],
             "LapCurrentLapTime": st["cur"] / 1000, "LapLastLapTime": st["last"] / 1000, "LapBestLapTime": st["best"] / 1000,
             "LapDistPct": st["npos"], "OnPitRoad": st["box"], "Speed": st["vel"] / 3.6, "Throttle": st["acel"], "Brake": st["freio"],
             "Gear": st["marcha"], "RPM": 6500.0, "FuelLevel": st["comb"], "PlayerCarMyIncidentCount": self.inc + (0 if st["valida"] else 1),
             "PlayerTrackSurface": 3, "PlayerCarPosition": 2, "WaterTemp": 91.0,
             "SteeringWheelAngle": 0.6 * math.sin(st["npos"] * 31), "SteeringWheelAngleMax": 7.85}
        if not st["valida"]:
            self.inc += 1
        for nome, t in self.VARS:
            _st.pack_into("<" + self.FMT[t], b, h_buf + self.ofs[nome], v[nome])
        SIMULADOS["Local\\IRSDKMemMapFileName"] = b


class F1:
    def __init__(self, porta):
        self.s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        self.porta = porta
        self.frame = 0

    def cab(self, pid):
        self.frame += 1
        return bytearray(_st.pack("<HBBBBBQfIIBB", 2025, 25, 1, 0, 1, pid, 777, self.frame / 60, self.frame, self.frame, 0, 255))

    def env(self, b):
        self.s.sendto(bytes(b), ("127.0.0.1", self.porta))

    def escrever(self, st):
        if st["status"] != 2:
            return
        b = self.cab(1) + bytearray(724)
        _st.pack_into("<BbbBHBb", b, 29, 0, 30, 22, 5, 4309, 18, 16)
        self.env(b)
        lap = bytearray(57)
        _st.pack_into("<II", lap, 0, st["last"], st["cur"])
        _st.pack_into("<f", lap, 20, st["npos"] * 4309.0)
        lap[32] = 3
        lap[33] = st["voltas"] + 1
        lap[34] = 1 if st["box"] else 0
        lap[37] = 0 if st["valida"] else 1
        self.env(self.cab(2) + lap + bytes(57 * 21) + b"\xff\xff")
        tel = bytearray(60)
        _st.pack_into("<Hfff", tel, 0, int(st["vel"]), st["acel"], 0.0, st["freio"])
        _st.pack_into("<b", tel, 15, st["marcha"])
        _st.pack_into("<H", tel, 16, 11000)
        self.env(self.cab(6) + tel + bytes(60 * 21) + b"\xff\x00\x00")
        x, z = pista(st["npos"])
        mov = bytearray(60)
        _st.pack_into("<fff", mov, 0, x, 0.0, z)
        self.env(self.cab(0) + mov + bytes(60 * 21))
        cs = bytearray(55)
        _st.pack_into("<f", cs, 5, st["comb"])
        self.env(self.cab(7) + cs + bytes(55 * 21))
        par = bytearray(1 + 57 * 22)
        par[0] = 20
        par[1 + 3] = 1
        self.env(self.cab(4) + par)


class Forza:
    def __init__(self, porta):
        self.s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        self.porta = porta
        self.ts = 0
        self.dist = 0.0
        self.npos_ant = None

    def escrever(self, st):
        self.ts += 20
        if self.npos_ant is not None:
            d = st["npos"] - self.npos_ant
            self.dist += (d if d >= 0 else d + 1) * 4309.0
        self.npos_ant = st["npos"]
        b = bytearray(331)
        _st.pack_into("<iIfff", b, 0, 1 if st["status"] == 2 else 0, self.ts, 8000.0, 900.0, 6500.0)
        _st.pack_into("<i", b, 212, 3456)
        base = 232
        x, z = pista(st["npos"])
        _st.pack_into("<ffff", b, base, x, 0.0, z, st["vel"] / 3.6)
        _st.pack_into("<5f", b, base + 44, st["comb"] / 100, self.dist, st["best"] / 1000, st["last"] / 1000, st["cur"] / 1000)
        _st.pack_into("<H", b, base + 68, st["voltas"])
        b[base + 71] = int(st["acel"] * 255)
        b[base + 72] = int(st["freio"] * 255)
        b[base + 75] = max(1, st["marcha"])
        _st.pack_into("<i", b, base + 95, 12)
        self.s.sendto(bytes(b), ("127.0.0.1", self.porta))


def limpar():
    for k in list(SIMULADOS):
        del SIMULADOS[k]


def main():
    pasta, porta = sys.argv[1], int(sys.argv[2])
    os.makedirs(pasta, exist_ok=True)
    banco = Banco(os.path.join(pasta, "axtel.db"))
    config = Config(pasta)
    col = Coletor(banco, pasta, config)
    import axtel_app.coletor as mc
    mc.FECHA_SESSAO = 3
    col.start()
    api = Api(banco, col, porta, config=config, voz=Voz(pasta, config), backups=Backups(banco, pasta, config), pasta_app=RAIZ, pasta_dados=pasta)
    srv = criar_servidor(api, os.path.join(RAIZ, "painel"), porta)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api.desligar = lambda: threading.Thread(target=srv.shutdown, daemon=True).start()
    print("servidor pronto", flush=True)
    random.seed(3)
    correr(Evo("Porsche 911 GT3 RS", "Interlagos", "Practice"), 5, [1.0, 1.03, 1.05, 1.02, 1.06], invalidas=(3,))
    time.sleep(5)
    for k in list(SIMULADOS):
        del SIMULADOS[k]
    time.sleep(2)
    correr(Classico("ks_ferrari_488_gt3", "monza", 3), 3, [1.0, 1.04, 1.02], invalidas=(2,))
    time.sleep(5)
    limpar()
    if os.environ.get("AXTEL_SIM_RAPIDO") != "1":
        for nome, jogo in (("iRacing", IRacing("Mazda MX-5 Cup", "Okayama")), ("AMS2", AMS2("Stock Car Pro", "Interlagos")),
                           ("F1 25", F1(config["portas"]["f1"])), ("Forza", Forza(config["portas"]["forza"]))):
            print("simulando", nome, flush=True)
            time.sleep(2)
            correr(jogo, 3, [1.0, 1.03, 1.01], invalidas=(2,))
            time.sleep(4)
            limpar()
            time.sleep(13)  # deixa o coletor soltar o jogo (sem dados novos)
    print("simulação terminada", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
