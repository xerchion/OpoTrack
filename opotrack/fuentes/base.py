"""Interfaz común de los conectores de boletines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional


@dataclass
class AnuncioNormalizado:
    """Un anuncio de un boletín, en forma homogénea e independiente de la fuente."""

    referencia_oficial: str            # identificador oficial (p. ej. BOE-A-2026-14786)
    titulo: str
    organismo: Optional[str] = None    # departamento / organismo convocante
    fecha_publicacion: Optional[date] = None
    url_pdf: Optional[str] = None
    url_html: Optional[str] = None
    url_xml: Optional[str] = None
    seccion: Optional[str] = None
    epigrafe: Optional[str] = None
    cuerpo: Optional[str] = None        # texto del anuncio (se rellena bajo demanda)


class SumarioNoDisponible(Exception):
    """El sumario del día solicitado aún no está publicado (p. ej. HTTP 404)."""


class ConectorBase(ABC):
    """Contrato que cumplen todos los conectores de boletines."""

    codigo: str = ""   # código de la fuente (BOE, BOPMA, ...)

    @abstractmethod
    def buscar(
        self,
        fecha,
        fetch_fn: Optional[Callable] = None,
    ) -> list[AnuncioNormalizado]:
        """Devuelve los anuncios de oposiciones del día `fecha`.

        Si se pasa `fetch_fn`, se usa en lugar de la descarga real (para pruebas
        con datos de ejemplo, sin acceso a la red).
        """
        raise NotImplementedError
