"""Conector de Convocatorias de empleo del Ayuntamiento de Córdoba (capital).

La sede ``cordoba.es`` (Drupal) sirve la sección «Convocatorias abiertas» como
un acordeón CKEditor: ``<dl class="styled">`` con un ``<dt>`` (título, incluye el
código ``[RHU03-2026-01]``) y un ``<dd>`` con detalles (plazas, enlaces y
«Plazo de presentación: DD/MM/AAAA … al DD/MM/AAAA»).

Solo salen aquí las convocatorias ABIERTAS (el histórico está en un portal
JavaScript aparte, no raspable). Cada ``<dt>`` es un anuncio; la referencia es
el código de la convocatoria y la fecha, el inicio del plazo de presentación.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Callable, Optional

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible


class ConectorCordoba(ConectorBase):
    codigo = "AYTCOR"
    ORGANISMO = "Ayuntamiento de Córdoba"
    URL = "https://www.cordoba.es/sede/tramites/empleo/convocatorias"
    COD_RE = re.compile(r"\[([A-Z0-9]{2,}-\d{4}-\d{2,3})\]")
    FECHA_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

    def fetch(self) -> str:
        resp = requests.get(
            self.URL, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text

    def parse_html(self, html: str) -> list[AnuncioNormalizado]:
        if not html:
            return []
        from bs4 import BeautifulSoup  # import perezoso

        soup = BeautifulSoup(html, "html.parser")
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        # OJO: en el HTML EN VIVO (sin JS) el acordeón es un <dl> plano; la clase
        # "styled" y los adornos (toggler, "active") los añade el JavaScript. Por
        # eso NO nos atamos a "dl.styled": recorremos todos los <dt> y nos
        # quedamos con los que son una convocatoria (código [XXX-AAAA-NN] o cuyo
        # <dd> trae "Plazo de presentación").
        for dt in soup.find_all("dt"):
            for sp in dt.select(".ckeditor-accordion-toggle"):
                sp.extract()  # quita el icono del acordeón si el JS lo insertó
            titulo = re.sub(r"\s+", " ", dt.get_text(" ", strip=True)).strip()
            if len(titulo) < 4:
                continue
            dd = dt.find_next_sibling("dd")
            dd_text = dd.get_text(" ", strip=True) if dd else ""
            cod = self.COD_RE.search(titulo)
            if not cod and "plazo de presentaci" not in dd_text.lower():
                continue  # no parece una convocatoria
            ref = "COR-" + (
                cod.group(1) if cod else hashlib.md5(titulo.lower().encode("utf-8")).hexdigest()[:12]
            )
            if ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=self.ORGANISMO,
                    fecha_publicacion=self._fecha_inicio(dd),
                    url_html=self.URL,
                    url_pdf=None,
                )
            )
        return anuncios

    def _fecha_inicio(self, dd) -> Optional[date]:
        """Inicio del plazo de presentación (primera fecha del <dd>)."""
        if dd is None:
            return None
        m = self.FECHA_RE.search(dd.get_text(" ", strip=True))
        if not m:
            return None
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        # Córdoba refleja el estado actual de «Convocatorias Abiertas» (lista viva,
        # no un boletín por fecha). 0 abiertas es un estado válido: se devuelve
        # lista vacía (el resumen mostrará «0/0»), NO «no hay publicación».
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        return self.parse_html(html)
