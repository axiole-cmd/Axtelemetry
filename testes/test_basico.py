"""Testes rápidos do Axtel (sem navegador). Rodam no GitHub a cada envio.

    python -m unittest discover -s testes -v
"""
import ctypes as C
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from axtel_app import telemetria_jogos  # noqa: E402
from axtel_app.banco import Banco  # noqa: E402
from axtel_app.coletor import Coletor  # noqa: E402
from axtel_app.leitores import Quadro, todos_os_leitores, volante  # noqa: E402
from axtel_app.leitores_extra import _MemoriaAMS2  # noqa: E402


def quadro(npos, atual, ultima, voltas, jogo="Assetto Corsa"):
    return Quadro(jogo=jogo, status="LIVE", pacote=0, carro="Carro", pista="Pista", tipo="Treino",
                  contador_voltas=voltas, atual_ms=atual, ultima_ms=ultima, melhor_ms=0, npos=npos, valida_jogo=None,
                  pneus_fora=0, no_box=False, vel=200, acel=1, freio=0, marcha=4, rpm=7000, combustivel=50, x=0, z=0)


class TestVoltas(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.banco = Banco(os.path.join(self.pasta, "t.db"))
        self.c = Coletor(self.banco, self.pasta)

    def rodar(self, repique):
        t, L, ultima = 1000.0, 50000, 0
        for volta in range(4):
            for k in range(0, L, 20):
                t += 0.02
                self.c.processar(quadro(k / L, k, ultima, volta), t)
            ultima = L
            t += 0.02
            self.c.processar(quadro(0.0004, 10, ultima, volta + 1), t)
            if repique:  # AC/ACC: um quadro com o tempo da volta anterior logo depois de zerar
                t += 0.02
                self.c.processar(quadro(0.0006, L + 30, ultima, volta + 1), t)
        for _ in range(40):
            t += 0.02
            self.c.processar(quadro(0.5, 25000, ultima, 4), t)
        return self.banco.q("SELECT numero, valida, motivo FROM voltas ORDER BY numero")

    def test_voltas_limpas_sao_validas(self):
        voltas = self.rodar(repique=False)
        self.assertEqual(len(voltas), 4)
        self.assertTrue(all(v["valida"] for v in voltas), voltas)

    def test_repique_na_linha_nao_invalida(self):
        voltas = self.rodar(repique=True)
        self.assertEqual(len(voltas), 4, "o repique não pode criar nem apagar voltas")
        self.assertTrue(all(v["valida"] for v in voltas), voltas)


class TestLeitores(unittest.TestCase):
    def test_ams2_tem_12_parciais(self):
        # layout do Project CARS 2 / AMS2: 3 atuais + 3 mais rápidas + 3 pessoais + 3 mundiais
        nomes = [n for n, _ in _MemoriaAMS2._fields_ if n.startswith("mSetor")]
        self.assertEqual(len(nomes), 12)
        self.assertEqual(_MemoriaAMS2.mSpeed.offset - _MemoriaAMS2.mFuelCapacity.offset, 4)

    def test_volante_normalizado(self):
        self.assertEqual(volante(0.5), 0.5)
        self.assertEqual(volante(-80), -0.8)   # jogos que mandam em porcentagem
        self.assertEqual(volante(150), 1.0)    # nunca passa do batente
        self.assertEqual(volante(-1.2), -1.0)

    def test_todos_os_jogos(self):
        jogos = [l.jogo for l in todos_os_leitores({"f1": 0, "forza": 0})]
        for j in ("AC EVO", "iRacing", "Automobilista 2", "F1 25", "Forza"):
            self.assertIn(j, jogos)


class TestTelemetriaDosJogos(unittest.TestCase):
    def setUp(self):
        self.docs = tempfile.mkdtemp()
        self.original = telemetria_jogos.pasta_documentos
        telemetria_jogos.pasta_documentos = lambda: self.docs

    def tearDown(self):
        telemetria_jogos.pasta_documentos = self.original

    def test_iracing_liga_telemetria(self):
        os.makedirs(os.path.join(self.docs, "iRacing"))
        ini = os.path.join(self.docs, "iRacing", "app.ini")
        open(ini, "w", encoding="latin-1").write("[Misc]\nirsdkEnableMem=0 ; telemetria\n")
        ok, _ = telemetria_jogos.ajustar("iracing", {})
        self.assertTrue(ok)
        self.assertIn("irsdkEnableMem=1", open(ini, encoding="latin-1").read())
        self.assertTrue(os.path.exists(ini + ".axtel-bak"))

    def test_f1_liga_udp(self):
        pasta = os.path.join(self.docs, "My Games", "F1 25", "hardwaresettings")
        os.makedirs(pasta)
        xml = os.path.join(pasta, "hardware_settings_config.xml")
        open(xml, "w").write('<x><motion><udp enabled="false" broadcast="true" ip="10.0.0.2" port="20000" sendRate="20" format="2024" /></motion></x>')
        ok, _ = telemetria_jogos.ajustar("f1", {"f1": 20777})
        self.assertTrue(ok)
        txt = open(xml).read()
        for esperado in ('enabled="true"', 'broadcast="false"', 'ip="127.0.0.1"', 'port="20777"', 'sendRate="60"', 'format="2025"'):
            self.assertIn(esperado, txt)

    def test_ams2_so_pelo_jogo(self):
        ok, _ = telemetria_jogos.ajustar("ams2", {})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
