"""Acesso ao regulamento interno por capítulo (Garantia 4).

O regulamento inteiro nunca entra na conversa. Ele é dividido em capítulos
uma vez, em memória, e o especialista em regulamento só pode puxar UM
capítulo por vez através de ``consultar_regulamento``. É esse texto de um
único capítulo — nunca o documento inteiro — que vira o resultado da tool e,
por consequência, o único trecho do regulamento que chega aos eventos da
sessão.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.config import REGULAMENTO_MD

_CAPITULO_RE = re.compile(r"^##\s+(Cap[íi]tulo[^\n]*)$", re.MULTILINE)


@dataclass(frozen=True)
class Capitulo:
    id: str
    titulo: str
    texto: str


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def _slug(titulo: str) -> str:
    slug = _normalizar(titulo)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


@lru_cache(maxsize=1)
def listar_capitulos() -> tuple[Capitulo, ...]:
    conteudo = REGULAMENTO_MD.read_text(encoding="utf-8")
    matches = list(_CAPITULO_RE.finditer(conteudo))
    capitulos = []
    for i, m in enumerate(matches):
        inicio = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(conteudo)
        titulo = m.group(1).strip()
        texto = conteudo[inicio:fim].strip()
        capitulos.append(Capitulo(id=_slug(titulo), titulo=titulo, texto=texto))
    return tuple(capitulos)


def indice_capitulos() -> list[dict]:
    """Só os títulos, para as instruções do especialista (não é 'trecho')."""
    return [{"id": c.id, "titulo": c.titulo} for c in listar_capitulos()]


_STOPWORDS = {
    "a",
    "o",
    "as",
    "os",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "um",
    "uma",
    "para",
    "por",
    "com",
    "que",
    "no",
    "na",
    "nos",
    "nas",
    "ao",
    "aos",
    "se",
    "sua",
    "seu",
    "minha",
    "meu",
    "qual",
    "quais",
    "quanto",
    "quantos",
    "quando",
    "horas",
    "hora",
    "ate",
    "funciona",
    "pode",
    "posso",
    "tem",
    "sao",
}


def _tokens(texto: str) -> set[str]:
    palavras = re.findall(r"[a-z0-9]+", _normalizar(texto))
    return {p for p in palavras if len(p) > 2 and p not in _STOPWORDS}


def buscar_capitulo(pergunta: str) -> Capitulo:
    """Encontra o capítulo mais relevante para a pergunta por sobreposição de termos."""
    termos = _tokens(pergunta)
    capitulos = listar_capitulos()
    if not termos:
        return capitulos[0]
    melhor = capitulos[0]
    melhor_pontos = -1
    for capitulo in capitulos:
        pontos = len(termos & _tokens(capitulo.texto))
        if pontos > melhor_pontos:
            melhor_pontos = pontos
            melhor = capitulo
    return melhor


def obter_capitulo(capitulo_id: str) -> Capitulo | None:
    for c in listar_capitulos():
        if c.id == capitulo_id:
            return c
    return None
