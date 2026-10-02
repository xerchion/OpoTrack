"""Conector para el BOP de Granada (bop.dipgra.es).

La página de un día (`.../buscador/BOP-DD-MM-AAAA/`) es HTML servido por el
servidor y lista todos los anuncios con su título, código CVE (identificador
único) y enlace al detalle. A diferencia del BOE, los títulos del BOP sí
incluyen la denominación del puesto, así que la extracción funciona mejor aquí.
"""

from __future__ import annotations

import datetime as dt
import re
from datetime import date
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from .base import AnuncioNormalizado, ConectorBase

_URL = "https://bop.dipgra.es/publica/consulta-de-bops/buscador/BOP-{fecha}/"
_BASE = "https://bop.dipgra.es/"
_DETALLE = "/buscador-anuncios/anuncio/"
# CVE de un anuncio: BOP-GRA-AAAA-NNNNNN (6+ dígitos; el del boletín solo tiene 3).
_CVE_RE = re.compile(r"BOP-GRA-\d{4}-\d{6,}")


def _fecha_ddmmaaaa(fecha) -> str:
    if isinstance(fecha, (date, dt.datetime)):
        return fecha.strftime("%d-%m-%Y")
    s = str(fecha)
    if re.fullmatch(r"\d{8}", s):          # AAAAMMDD -> DD-MM-AAAA
        return f"{s[6:8]}-{s[4:6]}-{s[0:4]}"
    return s


def _fecha_date(fecha) -> Optional[date]:
    if isinstance(fecha, date):
        return fecha
    s = str(fecha)
    try:
        if re.fullmatch(r"\d{8}", s):
            return dt.datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        pass
    return None


class ConectorBOPG(ConectorBase):
    """BOP provincial sobre la plataforma de las Diputaciones (Granada, Sevilla…).
    Las subclases solo cambian el dominio y el patrón del CVE."""

    codigo = "BOPG"
    URL = "https://bop.dipgra.es/publica/consulta-de-bops/buscador/BOP-{fecha}/"
    BASE = "https://bop.dipgra.es/"
    DETALLE = "/buscador-anuncios/anuncio/"
    # CVE de un anuncio: BOP-GRA-AAAA-NNNNNN (6+ dígitos; el del boletín solo tiene 3).
    CVE_RE = re.compile(r"BOP-GRA-\d{4}-\d{6,}")

    def fetch_dia(self, fecha) -> str:
        """Descarga el HTML del BOP para un día. Cadena vacía si no hay boletín (404)."""
        url = self.URL.format(fecha=_fecha_ddmmaaaa(fecha))
        resp = requests.get(url, headers={"User-Agent": "OpoTrack/0.1"}, timeout=30)
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text

    def parse_html(self, html: str, fecha=None) -> list[AnuncioNormalizado]:
        if not html:
            return []
        from bs4 import BeautifulSoup  # import perezoso: no obliga a tener bs4 salvo al usarlo

        soup = BeautifulSoup(html, "html.parser")
        f = _fecha_date(fecha)
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if self.DETALLE not in href:
                continue
            titulo = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
            if not titulo:
                continue
            # Referencia: el CVE del MISMO contenedor del anuncio (no por posición);
            # si no hay CVE, un id estable a partir del propio enlace.
            cont = a.find_parent("li") or a.parent
            m = self.CVE_RE.search(cont.get_text(" ", strip=True)) if cont else None
            ref = m.group(0) if m else href.rstrip("/").rsplit("/", 1)[-1]
            if not ref or ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=None,
                    fecha_publicacion=f,
                    # Absolutiza los enlaces relativos (si no, apuntarían al
                    # propio servidor de OpoTrack); los absolutos quedan igual.
                    url_html=urljoin(self.BASE, href),
                )
            )
        return anuncios

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch_dia(fecha)
        return self.parse_html(html, fecha)


class ConectorBOPS(ConectorBOPG):
    """BOP de la provincia de Sevilla (misma plataforma que Granada)."""

    codigo = "BOPS"
    URL = "https://bopsevilla.dipusevilla.es/publica/consulta-de-bops/buscador/BOP-{fecha}/"
    BASE = "https://bopsevilla.dipusevilla.es/"
    # CVE del BOP de Sevilla (formato por confirmar en real); si no casa, se usa
    # el id del enlace como referencia, así el conector nunca queda vacío.
    CVE_RE = re.compile(r"BOP-SE-\d{4}-\d{4,}", re.I)
