"""Conector del portal «Convocatorias de empleo público» del Ayuntamiento de
Huétor Tájar (Granada).

La página ``huetortajar.org/ayuntamiento/convocatorias-de-empleo-publico/`` es
HTML estático (WordPress): dentro de ``<section class="entry-content">`` hay un
``<h2 class="wp-block-heading">`` por convocatoria/plaza y, debajo, un párrafo
por documento con el formato ``AAAA-MM-DD: <a href="…pdf">Título</a>``, del más
reciente al más antiguo. Tratamos cada ENCABEZADO como un anuncio (la
convocatoria), no cada PDF: la página guarda todo el histórico de trámites de
cada proceso y un anuncio por PDF inundaría la bandeja.

- Referencia estable = ``"HT-" + md5(título_normalizado)[:12]`` (las columnas de
  referencia son de 40 caracteres).
- Enlace = el PDF de las «bases» si se reconoce; si no, el más antiguo del bloque
  (que suele ser el de la convocatoria).
- Fecha = la más antigua del bloque (origen de la convocatoria).

La página NO es por fechas: lista todo y el motor se queda con lo nuevo (por
referencia). Los encabezados separadores sin PDFs (p. ej. «CONSOLIDACIÓN:
CONCURSO») se ignoran.
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


class ConectorHuetorTajar(ConectorBase):
    codigo = "AYTHT"
    ORGANISMO = "Ayuntamiento de Huétor Tájar"
    URL = "https://huetortajar.org/ayuntamiento/convocatorias-de-empleo-publico/"
    ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
    DMY_RE = re.compile(r"(\d{2})[/-](\d{2})[/-](\d{4})")
    BASES_RE = re.compile(r"bases", re.IGNORECASE)

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
        # El listado real vive en <section class="entry-content">; así se ignoran
        # los PDFs de menús, cabeceras o pies de página.
        cont = soup.find("section", class_="entry-content") or soup
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for h in cont.find_all("h2", class_="wp-block-heading"):
            titulo = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
            titulo = titulo.rstrip(":").strip()
            if not titulo:
                continue
            enlaces: list = []
            fechas: list[date] = []
            for sib in h.next_siblings:
                nombre = getattr(sib, "name", None)
                if nombre == "h2" and "wp-block-heading" in (sib.get("class") or []):
                    break  # empieza el bloque de la siguiente convocatoria
                if nombre:
                    for a in sib.find_all("a", href=True):
                        if a["href"].split("?")[0].lower().endswith(".pdf"):
                            enlaces.append(a)
                    fechas += self._fechas(sib.get_text(" ", strip=True))
                elif isinstance(sib, str):
                    fechas += self._fechas(sib)
            if not enlaces:
                continue  # encabezado separador sin documentos (p. ej. «CONSOLIDACIÓN…»)
            ref = "HT-" + hashlib.md5(titulo.lower().encode("utf-8")).hexdigest()[:12]
            if ref in vistos:
                continue
            vistos.add(ref)
            url = urljoin(self.URL, self._mejor_enlace(enlaces)["href"])
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=self.ORGANISMO,
                    fecha_publicacion=min(fechas) if fechas else None,
                    url_html=url,
                    url_pdf=url,
                )
            )
        return anuncios

    def _mejor_enlace(self, enlaces: list):
        """Devuelve el PDF de las bases si se reconoce; si no, el más antiguo del
        bloque (el último en el documento, porque van de nuevo a viejo), que
        suele ser el de la convocatoria."""
        for a in enlaces:
            if self.BASES_RE.search(a.get_text(" ", strip=True)) or self.BASES_RE.search(a["href"]):
                return a
        return enlaces[-1]

    def _fechas(self, s: str) -> list[date]:
        out: list[date] = []
        for y, m, d in self.ISO_RE.findall(s or ""):
            try:
                out.append(date(int(y), int(m), int(d)))
            except ValueError:
                pass
        for d, m, y in self.DMY_RE.findall(s or ""):
            try:
                out.append(date(int(y), int(m), int(d)))
            except ValueError:
                pass
        return out

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        anuncios = self.parse_html(html)
        if not anuncios:
            raise SumarioNoDisponible(
                "El portal de empleo de Huétor Tájar no devolvió resultados."
            )
        return anuncios
