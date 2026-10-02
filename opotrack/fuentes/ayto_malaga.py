"""Conector de Ofertas de Empleo Público del Ayuntamiento de Málaga (capital).

La web ``malaga.eu`` es HTML servido por servidor. El listado de «Convocatorias
en trámite» es un ``<ul>`` con un ``<li class="articulo">`` por convocatoria:

    <li class="articulo">
      <h3 class="item-title">AUXILIAR ADMINISTRATIVO</h3>
      <div class="info-wrapper">
        <dl><dt>Especialidad:</dt><dd>…</dd></dl>
        <dl><dt>Subgrupo:</dt><dd>C2</dd></dl>
        <dl><dt>Vínculo:</dt><dd>FUNCIONARIO DE CARRERA</dd></dl>
        <dl><dt>Trámite:</dt><dd>Abierto plazo de presentación de solicitudes</dd></dl>
      </div>
      <div class="actions"><a href="…/detalle-de-la-convocatoria/index.html?id=260">Detalle</a></div>
    </li>

Se trata cada ``<li>`` como un anuncio; la referencia es el ``id`` de la ficha.
**Se omiten los procesos cuyo Trámite indica «Cerrado…»** (petición del usuario:
la lista completa es enorme y la mayoría son procesos ya cerrados).
"""

from __future__ import annotations

import re
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible


class ConectorMalaga(ConectorBase):
    codigo = "AYTMLG"
    ORGANISMO = "Ayuntamiento de Málaga"
    SITE = "https://www.malaga.eu"
    URL = "https://www.malaga.eu/el-ayuntamiento/ofertas-de-empleo-publico/ayuntamiento-de-malaga/"
    ID_RE = re.compile(r"[?&]id=(\d+)")

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
        for li in soup.select("li.articulo"):
            a = li.select_one('a[href*="detalle-de-la-convocatoria"][href*="id="]')
            if not a:
                continue
            m = self.ID_RE.search(a["href"])
            if not m:
                continue
            idc = m.group(1)
            campos = self._campos(li)
            tramite = campos.get("trámite") or campos.get("tramite") or ""
            if "cerrado" in tramite.lower():
                continue  # proceso cerrado: se omite
            ref = "MLG-" + idc
            if ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=self._titulo(li, campos, idc),
                    organismo=self.ORGANISMO,
                    fecha_publicacion=None,
                    url_html=urljoin(self.SITE + "/", a["href"]),
                    url_pdf=None,
                    epigrafe=tramite or None,
                )
            )
        return anuncios

    @staticmethod
    def _campos(li) -> dict:
        """Diccionario {etiqueta_minúsculas: valor} de los <dl><dt>/<dd> de la tarjeta."""
        campos: dict[str, str] = {}
        for dl in li.select("dl"):
            dt, dd = dl.find("dt"), dl.find("dd")
            if dt and dd:
                clave = re.sub(r"\s+", " ", dt.get_text(" ", strip=True)).rstrip(":").strip().lower()
                campos[clave] = re.sub(r"\s+", " ", dd.get_text(" ", strip=True)).strip()
        return campos

    def _titulo(self, li, campos: dict, idc: str) -> str:
        h = li.find(["h3", "h2"])
        titulo = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip() if h else ""
        esp = campos.get("especialidad")
        if esp and esp.lower() not in titulo.lower():
            titulo = f"{titulo} — {esp}" if titulo else esp
        return titulo or ("Convocatoria " + idc)

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        anuncios = self.parse_html(html)
        if not anuncios:
            raise SumarioNoDisponible(
                "El portal de empleo de Málaga no devolvió convocatorias abiertas."
            )
        return anuncios
