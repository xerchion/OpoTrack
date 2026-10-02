"""Conector del portal de Empleo Público del Ayuntamiento de Loja (Granada).

La página ``aytoloja.org/empleo/empleopublico.htm`` es HTML estático: titulares
de procesos con enlaces a PDF debajo. No hay un identificador limpio por
convocatoria, pero cada documento es un PDF en ``/empleo/doc/<archivo>.pdf`` con
nombre descriptivo y estable. Tratamos cada PDF como un anuncio: la referencia
es un hash del nombre del archivo (las columnas de referencia son de 40 car.), y
el título sale del texto del enlace o, si es genérico, del propio nombre del PDF.

La página no es por fechas: lista lo vigente y el motor se queda con lo nuevo
(por referencia).
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible

_GENERICOS = {
    "", "descargar bases", "anuncio", "acta", "acta seleccion", "acta selección",
    "bases", "pdf", "descargar", "anexo",
}


class ConectorLoja(ConectorBase):
    codigo = "AYTLOJA"
    ORGANISMO = "Ayuntamiento de Loja"
    URL = "http://www.aytoloja.org/empleo/empleopublico.htm"
    DOC_RE = re.compile(r"(?:^|/)doc/([^/?#]+)\.pdf", re.IGNORECASE)
    FECHA_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{2})[/-](\d{2})[/-](\d{4})")

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
        # El listado real está en <div id="content">; así evitamos los PDF de los
        # menús de navegación (p. ej. el Protocolo de Acoso Laboral).
        cont = soup.find(id="content") or soup
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for a in cont.find_all("a", href=True):
            m = self.DOC_RE.search(a["href"])
            if not m:
                continue
            archivo = m.group(1)
            ref = "LOJA-" + hashlib.md5(archivo.lower().encode("utf-8")).hexdigest()[:12]
            if ref in vistos:
                continue
            vistos.add(ref)
            url = urljoin(self.URL, a["href"])
            texto = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            # La fecha puede ir dentro del enlace o justo después (texto hermano).
            sib = a.next_sibling if isinstance(a.next_sibling, str) else ""
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=self._titulo(texto, archivo),
                    organismo=self.ORGANISMO,
                    fecha_publicacion=self._fecha(texto) or self._fecha(sib) or self._fecha(archivo),
                    url_html=url,
                    url_pdf=url,
                )
            )
        return anuncios

    def _titulo(self, texto: str, archivo: str) -> str:
        base = re.sub(r"^\d{4}[_-]", "", archivo)      # quita el año inicial (2026_)
        base = re.sub(r"[_-]+", " ", base).strip()
        base = (base[:1].upper() + base[1:]) if base else archivo
        limpio = texto.rstrip(". ").strip()
        # Usa el texto del enlace si es más descriptivo que el nombre del archivo.
        if limpio and limpio.lower() not in _GENERICOS and len(limpio) >= 12:
            return limpio
        return base

    def _fecha(self, s: str) -> Optional[date]:
        m = self.FECHA_RE.search(s or "")
        if not m:
            return None
        try:
            if m.group(1):  # AAAA-MM-DD
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))  # DD-MM-AAAA / DD/MM/AAAA
        except ValueError:
            return None

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        anuncios = self.parse_html(html)
        if not anuncios:
            raise SumarioNoDisponible("El portal de empleo de Loja no devolvió resultados.")
        return anuncios
