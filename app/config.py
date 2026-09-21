"""Configuração central do projeto: caminhos e nomes fixos.

Os dados de origem em ``dados/`` são somente leitura (estado inicial do
condomínio, fornecido pelo enunciado). Tudo o que o assistente grava em
tempo de execução vai para ``.data/`` (fora do controle de versão), separado
por design: assim é possível restaurar reservas/visitantes ao estado inicial
sem tocar em ``dados/``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = BASE_DIR / "dados"
RUNTIME_DIR = BASE_DIR / ".data"
RUNTIME_DIR.mkdir(exist_ok=True)

APARTAMENTOS_JSON = DADOS_DIR / "apartamentos.json"
AREAS_JSON = DADOS_DIR / "areas.json"
RESERVAS_JSON = DADOS_DIR / "reservas.json"
VISITANTES_JSON = DADOS_DIR / "visitantes.json"
REGULAMENTO_MD = DADOS_DIR / "regulamento.md"

CONDOMINIO_DB_PATH = RUNTIME_DIR / "condominio.db"
SESSIONS_DB_PATH = RUNTIME_DIR / "sessoes.db"
SESSIONS_DB_URL = f"sqlite+aiosqlite:///{SESSIONS_DB_PATH}"

APP_NAME = "residencial-aurora"

ADK_MODEL = os.environ.get("ADK_MODEL", "gemini-2.5-flash")
