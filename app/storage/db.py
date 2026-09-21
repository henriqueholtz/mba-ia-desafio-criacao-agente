"""Acesso ao SQLite que guarda reservas e visitantes gravados pelo assistente.

Este é o coração da Garantia 5 (dois moradores, uma reserva): a exclusividade
de "no máximo uma reserva ativa por área e data" é um índice único parcial do
SQLite (``idx_reservas_area_data_ativa``), e não uma checagem feita em Python
antes de gravar. Duas inserções concorrentes para a mesma área/data são
serializadas pelo próprio arquivo do banco; a que perder o `INSERT` recebe um
``sqlite3.IntegrityError`` no exato instante da gravação, nunca antes. Também
sustenta a Garantia 3 (nada se perde no reinício): o arquivo ``.data/condominio.db``
sobrevive a reinícios da API, ao contrário de qualquer estado em memória.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from app.config import CONDOMINIO_DB_PATH, RESERVAS_JSON, VISITANTES_JSON

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reservas (
    codigo TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    area TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ativa'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reservas_area_data_ativa
    ON reservas(area, data)
    WHERE status = 'ativa';

CREATE TABLE IF NOT EXISTS visitantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL,
    nome TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(CONDOMINIO_DB_PATH, timeout=5)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Garante que as tabelas existam. Não mexe em dados já gravados."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
        row = conn.execute("SELECT COUNT(*) FROM reservas").fetchone()
        if row[0] == 0:
            _seed(conn)
            conn.commit()


def restore_db() -> None:
    """Restaura reservas e visitantes ao estado inicial de ``dados/``.

    Comando de restauração pedido pelo enunciado. Apaga tudo o que o
    assistente gravou e recarrega exatamente o conteúdo de
    ``dados/reservas.json`` e ``dados/visitantes.json``. Não toca nas sessões
    do ADK (elas moram em outro arquivo, ``.data/sessoes.db``).
    """
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM reservas")
        conn.execute("DELETE FROM visitantes")
        conn.commit()
        _seed(conn)
        conn.commit()


def _seed(conn: sqlite3.Connection) -> None:
    reservas = json.loads(RESERVAS_JSON.read_text(encoding="utf-8"))
    for r in reservas:
        conn.execute(
            "INSERT INTO reservas (codigo, apartamento, area, data, status)"
            " VALUES (?, ?, ?, ?, 'ativa')",
            (r["codigo"], r["apartamento"], r["area"], r["data"]),
        )
    visitantes = json.loads(VISITANTES_JSON.read_text(encoding="utf-8"))
    for v in visitantes:
        conn.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (v["apartamento"], v["nome"], v["data"]),
        )


# --- Reservas -----------------------------------------------------------


def listar_reservas_do_apartamento(apartamento: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND status = 'ativa'"
            " ORDER BY data",
            (apartamento,),
        ).fetchall()
    return [{"codigo": c, "area": a, "data": d} for c, a, d in rows]


def area_esta_livre(area: str, data: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ? AND status = 'ativa'",
            (area, data),
        ).fetchone()
    return row is None


def criar_reserva(apartamento: str, area: str, data: str) -> str | None:
    """Grava uma reserva de forma atômica.

    Retorna o código da nova reserva, ou ``None`` quando a área já estava
    ocupada nessa data no instante exato do INSERT (é isso, e não uma
    consulta prévia, que garante a exclusividade sob concorrência).
    """
    for _ in range(5):
        codigo = f"RSV-{uuid.uuid4().hex[:8].upper()}"
        try:
            with _connect() as conn:
                conn.execute(
                    "INSERT INTO reservas (codigo, apartamento, area, data, status)"
                    " VALUES (?, ?, ?, ?, 'ativa')",
                    (codigo, apartamento, area, data),
                )
                conn.commit()
            return codigo
        except sqlite3.IntegrityError as exc:
            if "reservas.codigo" in str(exc):
                # Colisão (extremamente improvável) no código gerado: tenta outro.
                continue
            # Violou o índice único de (area, data) ativa: outra reserva venceu.
            return None
    raise RuntimeError("Não foi possível gerar um código de reserva único.")


def cancelar_reserva(apartamento: str, area: str, data: str) -> str | None:
    """Cancela a reserva ativa do PRÓPRIO apartamento para área/data.

    Retorna o código cancelado, ou ``None`` se o apartamento não tiver uma
    reserva ativa correspondente (inclusive quando a reserva existe, mas é de
    outro apartamento — nunca é cancelada por essa chamada).
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT codigo FROM reservas"
            " WHERE apartamento = ? AND area = ? AND data = ? AND status = 'ativa'",
            (apartamento, area, data),
        ).fetchone()
        if row is None:
            return None
        codigo = row[0]
        conn.execute(
            "UPDATE reservas SET status = 'cancelada'"
            " WHERE codigo = ? AND apartamento = ?",
            (codigo, apartamento),
        )
        conn.commit()
    return codigo


# --- Visitantes -----------------------------------------------------------


def listar_visitantes_do_apartamento(apartamento: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data",
            (apartamento,),
        ).fetchall()
    return [{"nome": n, "data": d} for n, d in rows]


def autorizar_visitante(apartamento: str, nome: str, data: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome, data),
        )
        conn.commit()
