"""Conector de Ofertas de Empleo del Ayuntamiento de Motril (Granada).

La web ``motril.es`` es WordPress (Elementor), HTML servido. La página
``/recursos-humanos/oferta-empleo-publico/ofertas-empleo/`` lista las
convocatorias agrupadas por año y tipo; cada una es un enlace de detalle:

    <h3 class="elementor-post__title">
      <a href="https://motril.es/oferta-empleo/expediente-3928-2026-4-plazas-auxiliar-administrativo…/">
         Expediente 3928/2026, 4 plazas Auxiliar administrativo…</a>
    </h3>

Se trata cada enlace ``/oferta-empleo/<slug>/`` como un anuncio (expediente o
resumen de OEP). La referencia es un hash estable del *slug*. El listado no trae
fechas; el motor se queda con lo nuevo por referencia.
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible


class ConectorMotril(ConectorBase):
    codigo = "AYTMOT"
    ORGANISMO = "Ayuntamiento de Motril"
    SITE = "https://motril.es"
    URL = "https://motril.es/recursos-humanos/oferta-empleo-publico/ofertas-empleo/"
    DETALLE_RE = re.compile(r"/oferta-empleo/([^/?#]+)/?$")

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
        for a in soup.find_all("a", href=True):
            m = self.DETALLE_RE.search(a["href"])
            if not m:
                continue
            slug = m.group(1)
            titulo = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            if len(titulo) < 4:
                continue
            ref = "MOT-" + hashlib.md5(slug.lower().encode("utf-8")).hexdigest()[:12]
            if ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=self.ORGANISMO,
                    fecha_publicacion=None,
                    url_html=urljoin(self.SITE + "/", a["href"]),
                    url_pdf=None,
                )
            )
        return anuncios

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        anuncios = self.parse_html(html)
        if not anuncios:
            raise SumarioNoDisponible("El portal de empleo de Motril no devolvió resultados.")
        return anuncios
