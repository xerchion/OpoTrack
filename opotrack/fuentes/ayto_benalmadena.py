"""Conector del portal de «Convocatorias de Personal» del Ayuntamiento de
Benalmádena (Málaga).

La página ``.../contenido.php?...&s=convocatorias-de-personal`` es HTML estático:
una tabla con una fila por convocatoria (fecha «Actualizado» + título + enlace).
Cada enlace apunta a ``/convocatorias-de-personal/C<NNN>/<slug>.html``; la
referencia única de cada convocatoria es ese código ``C<NNN>``.

La página NO es por fechas: muestra las convocatorias vigentes. El motor se
queda con las nuevas (por referencia), así que sirve igual: cada búsqueda trae
las que no se hubieran visto antes.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible


class ConectorBenalmadena(ConectorBase):
    codigo = "AYTBEN"
    ORGANISMO = "Ayuntamiento de Benalmádena"
    URL = (
        "https://www.benalmadena.es/contenido.php"
        "?m=benalmadena-delegaciones&s=convocatorias-de-personal"
    )
    REF_RE = re.compile(r"/convocatorias-de-personal/(C\d+)/", re.IGNORECASE)
    FECHA_RE = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$")

    def fetch(self) -> str:
        """Descarga la página de convocatorias (HTML). Solo responde bien a un
        User-Agent de navegador."""
        resp = requests.get(
            self.URL, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text

    def parse_html(self, html: str) -> list[AnuncioNormalizado]:
        if not html:
            return []
        from bs4 import BeautifulSoup  # import perezoso

        soup = BeautifulSoup(html, "html.parser")
        # Cada convocatoria aparece como dos enlaces a la misma URL (fecha y
        # título). Agrupamos por referencia (C<NNN>) y quedamos con ambos datos.
        por_ref: dict[str, dict] = {}
        for a in soup.find_all("a", href=True):
            m = self.REF_RE.search(a["href"])
            if not m:
                continue
            ref = m.group(1).upper()
            d = por_ref.setdefault(
                ref, {"url": urljoin(self.URL, a["href"]), "titulo": None, "fecha": None}
            )
            texto = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            fm = self.FECHA_RE.match(texto)
            if fm:
                try:
                    d["fecha"] = date(int(fm.group(3)), int(fm.group(2)), int(fm.group(1)))
                except ValueError:
                    pass
            elif texto and (d["titulo"] is None or len(texto) > len(d["titulo"])):
                d["titulo"] = texto

        anuncios: list[AnuncioNormalizado] = []
        for ref, d in por_ref.items():
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=d["titulo"] or self._titulo_desde_url(d["url"]) or ref,
                    organismo=self.ORGANISMO,
                    fecha_publicacion=d["fecha"],
                    url_html=d["url"],
                    url_pdf=None,
                )
            )
        return anuncios

    @staticmethod
    def _titulo_desde_url(url: str) -> str:
        """Título legible a partir del slug de la URL (solo como último recurso)."""
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if slug.endswith(".html"):
            slug = slug[:-5]
        return re.sub(r"[-_]+", " ", slug).strip()

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        anuncios = self.parse_html(html)
        if not anuncios:
            raise SumarioNoDisponible(
                "El portal de convocatorias de Benalmádena no devolvió resultados."
            )
        return anuncios
