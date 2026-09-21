"""Dados de referência do condomínio: apartamentos e áreas comuns.

Estes arquivos são o estado inicial do condomínio e nunca são alterados pelo
assistente (regra do enunciado), por isso são apenas lidos, uma vez, para a
memória do processo.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.config import AREAS_JSON, APARTAMENTOS_JSON


@dataclass(frozen=True)
class Apartamento:
    numero: str
    morador: str


@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: float


@lru_cache(maxsize=1)
def listar_apartamentos() -> tuple[Apartamento, ...]:
    dados = json.loads(APARTAMENTOS_JSON.read_text(encoding="utf-8"))
    return tuple(Apartamento(**item) for item in dados)


@lru_cache(maxsize=1)
def listar_areas() -> tuple[Area, ...]:
    dados = json.loads(AREAS_JSON.read_text(encoding="utf-8"))
    return tuple(Area(**item) for item in dados)


def apartamento_existe(numero: str) -> bool:
    return any(a.numero == numero for a in listar_apartamentos())


def obter_area(area_id: str) -> Area | None:
    for area in listar_areas():
        if area.id == area_id:
            return area
    return None


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def resolver_area(texto: str) -> Area | None:
    """Encontra a área a partir do id (``salao-de-festas``) ou do nome livre
    que o modelo eventualmente usar (``salão de festas``, ``Salão de Festas``).

    As tools de reserva sempre passam o texto do parâmetro ``area`` por aqui
    antes de consultar ou gravar qualquer coisa, porque o id exato usado no
    catálogo não é garantido ser o que o modelo escreve.
    """
    if not texto:
        return None
    alvo = _slug(texto)
    for area in listar_areas():
        if _slug(area.id) == alvo or _slug(area.nome) == alvo:
            return area
    return None


def taxa_da_area(area_id: str) -> float:
    area = obter_area(area_id)
    return area.taxa if area else 0.0
