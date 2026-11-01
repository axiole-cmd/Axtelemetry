"""Banco SQLite do Axtel (dados/axtel.db)."""
import json
import os
import sqlite3
import threading
from datetime import datetime

ESQUEMA = """
CREATE TABLE IF NOT EXISTS sessoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jogo TEXT NOT NULL, carro TEXT NOT NULL, pista TEXT NOT NULL, tipo TEXT NOT NULL,
  inicio TEXT NOT NULL, fim TEXT,
  voltas INTEGER DEFAULT 0, validas INTEGER DEFAULT 0,
  melhor_ms INTEGER, distancia_m REAL DEFAULT 0, tempo_s REAL DEFAULT 0,
  aberta INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS voltas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sessao_id INTEGER NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
  numero INTEGER NOT NULL, tempo_ms INTEGER NOT NULL,
  valida INTEGER NOT NULL, motivo TEXT,
  p1 INTEGER, p2 INTEGER, p3 INTEGER,
  distancia_m REAL, combustivel REAL, vel_max REAL,
  quando TEXT, amostras TEXT
);
CREATE INDEX IF NOT EXISTS ix_voltas_sessao ON voltas(sessao_id);
CREATE INDEX IF NOT EXISTS ix_sessoes_jogo ON sessoes(jogo);
CREATE TABLE IF NOT EXISTS pendencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  texto TEXT NOT NULL, nota TEXT DEFAULT '',
  feita INTEGER DEFAULT 0, criada TEXT NOT NULL, concluida TEXT
);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS setups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jogo TEXT NOT NULL, carro TEXT NOT NULL, pista TEXT NOT NULL, nome TEXT NOT NULL,
  parametros TEXT DEFAULT '[]', notas TEXT DEFAULT '', criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS desafios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL, jogo TEXT NOT NULL, carro TEXT NOT NULL, pista TEXT NOT NULL,
  alvo REAL NOT NULL, titulo TEXT NOT NULL, criado TEXT NOT NULL, concluido TEXT
);
"""

# O Axtel começa sem nenhuma anotação: o histórico é só o que você criar.
PENDENCIAS_INICIAIS = []


class Banco:
    def __init__(self, caminho):
        self.caminho = caminho
        self.trava = threading.RLock()
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(ESQUEMA)
        # Sessões que ficaram abertas (o app foi fechado no meio) são encerradas.
        self.con.execute("UPDATE sessoes SET aberta=0 WHERE aberta=1")
        self.con.execute("DELETE FROM sessoes WHERE voltas=0")
        colunas = [r[1] for r in self.con.execute("PRAGMA table_info(sessoes)")]
        if "setup_id" not in colunas:
            self.con.execute("ALTER TABLE sessoes ADD COLUMN setup_id INTEGER")
        if not self.con.execute("SELECT 1 FROM meta WHERE chave='pendencias_iniciais'").fetchone():
            agora = datetime.now().isoformat(timespec="seconds")
            self.con.executemany("INSERT INTO pendencias(texto,nota,criada) VALUES(?,?,?)",
                                 [(t, n, agora) for t, n in PENDENCIAS_INICIAIS])
            self.con.execute("INSERT INTO meta VALUES('pendencias_iniciais','1')")
        self.con.commit()

    # ---------- escrita ----------
    def nova_sessao(self, jogo, carro, pista, tipo, inicio):
        with self.trava:
            cur = self.con.execute(
                "INSERT INTO sessoes(jogo,carro,pista,tipo,inicio,fim) VALUES(?,?,?,?,?,?)",
                (jogo, carro, pista, tipo, inicio, inicio))
            self.con.commit()
            return cur.lastrowid

    def nova_volta(self, sessao_id, v):
        with self.trava:
            self.con.execute(
                "INSERT INTO voltas(sessao_id,numero,tempo_ms,valida,motivo,p1,p2,p3,distancia_m,combustivel,vel_max,quando,amostras)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sessao_id, v["numero"], v["tempo_ms"], 1 if v["valida"] else 0, v.get("motivo"),
                 v.get("p1"), v.get("p2"), v.get("p3"), v.get("distancia_m"), v.get("combustivel"),
                 v.get("vel_max"), v.get("quando"), json.dumps(v.get("amostras") or [], separators=(",", ":"))))
            self._recalcular(sessao_id)
            self.con.commit()

    def _recalcular(self, sid):
        r = self.con.execute(
            "SELECT COUNT(*) n, SUM(valida) v, MIN(CASE WHEN valida=1 THEN tempo_ms END) m,"
            " COALESCE(SUM(distancia_m),0) d, COALESCE(SUM(tempo_ms),0)/1000.0 t FROM voltas WHERE sessao_id=?",
            (sid,)).fetchone()
        self.con.execute("UPDATE sessoes SET voltas=?, validas=?, melhor_ms=?, distancia_m=?, tempo_s=? WHERE id=?",
                         (r["n"], r["v"] or 0, r["m"], r["d"], r["t"], sid))

    def encerrar_sessao(self, sid, fim):
        with self.trava:
            self.con.execute("UPDATE sessoes SET fim=?, aberta=0 WHERE id=?", (fim, sid))
            self.con.execute("DELETE FROM sessoes WHERE id=? AND voltas=0", (sid,))
            self.con.commit()

    def tocar_sessao(self, sid, fim):
        with self.trava:
            self.con.execute("UPDATE sessoes SET fim=? WHERE id=?", (fim, sid))
            self.con.commit()

    def apagar_sessao(self, sid):
        with self.trava:
            self.con.execute("DELETE FROM voltas WHERE sessao_id=?", (sid,))
            self.con.execute("DELETE FROM sessoes WHERE id=?", (sid,))
            self.con.commit()

    # ---------- pendências ----------
    def nova_pendencia(self, texto, nota=""):
        with self.trava:
            cur = self.con.execute("INSERT INTO pendencias(texto,nota,criada) VALUES(?,?,?)",
                                   (texto, nota, datetime.now().isoformat(timespec="seconds")))
            self.con.commit()
            return cur.lastrowid

    def editar_pendencia(self, pid, campos):
        with self.trava:
            if "feita" in campos:
                feita = 1 if campos["feita"] else 0
                self.con.execute("UPDATE pendencias SET feita=?, concluida=? WHERE id=?",
                                 (feita, datetime.now().isoformat(timespec="seconds") if feita else None, pid))
            for k in ("texto", "nota"):
                if k in campos:
                    self.con.execute(f"UPDATE pendencias SET {k}=? WHERE id=?", (str(campos[k]), pid))
            self.con.commit()

    def apagar_pendencia(self, pid):
        with self.trava:
            self.con.execute("DELETE FROM pendencias WHERE id=?", (pid,))
            self.con.commit()

    # ---------- comandos simples (setups, desafios) ----------
    def executar(self, sql, args=()):
        with self.trava:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur.lastrowid

    # ---------- backup ----------
    def backup(self, pasta, manter=14):
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, "axtel-" + datetime.now().strftime("%Y-%m-%d") + ".db")
        with self.trava:
            alvo = sqlite3.connect(destino)
            try:
                self.con.backup(alvo)
            finally:
                alvo.close()
        copias = sorted(f for f in os.listdir(pasta) if f.startswith("axtel-") and f.endswith(".db"))
        for velho in copias[:-max(1, int(manter))]:
            try:
                os.remove(os.path.join(pasta, velho))
            except OSError:
                pass
        return destino

    # ---------- leitura ----------
    def q(self, sql, args=()):
        with self.trava:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def q1(self, sql, args=()):
        r = self.q(sql, args)
        return r[0] if r else None
