"""Conector del Empleo Público del Ayuntamiento de Antequera (Málaga).

La web ``antequera.es`` es OpenCms, HTML servido por servidor. Bajo
``/ayuntamiento/tablon-de-anuncios/Empleo-Publico/`` hay tres listados con la
misma plantilla: ``oposiciones/``, ``Concursos/`` y ``bolsas-de-empleo/``. Cada
proceso es una tarjeta:

    <div>
      <div><h3><a href="…/Empleo-Publico/oposiciones/SLUG/">TÍTULO</a></h3>
           <p>descripción</p></div>
      <div class="time start-time"><time datetime="2026-02-26T…">…</time></div>
      <div class="time end-time"><time datetime="2026-03-25T…">…</time></div>
    </div>

Tratamos cada tarjeta como un anuncio. La referencia estable sale del *slug* de
la URL de detalle; la fecha de publicación, del ``start-time`` (si lo hay).
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


class ConectorAntequera(ConectorBase):
    codigo = "AYTANT"
    ORGANISMO = "Ayuntamiento de Antequera"
    SITE = "https://www.antequera.es"
    BASE = "https://www.antequera.es/ayuntamiento/tablon-de-anuncios/Empleo-Publico/"
    URLS = [BASE + "oposiciones/", BASE + "Concursos/", BASE + "bolsas-de-empleo/"]
    # El slug debe empezar por carácter alfanumérico: así se excluyen los enlaces
    # de salto/menú/cookies que apuntan a ".../oposiciones/#content-interior",
    # ".../oposiciones/#menuprincipal-…" o ".../oposiciones/#".
    DETALLE_RE = re.compile(
        r"/Empleo-Publico/(?:oposiciones|Concursos|bolsas-de-empleo)/([A-Za-z0-9][^/#?]*?)/?$"
    )
    _NO_SLUG = {"oposiciones", "concursos", "bolsas-de-empleo", "index.html"}

    def fetch(self, url: str) -> str:
        resp = requests.get(
            url, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
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
            if slug.lower() in self._NO_SLUG:
                continue
            titulo = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip() or (a.get("title") or "").strip()
            if not titulo:
                continue
            ref = "ANT-" + hashlib.md5(slug.lower().encode("utf-8")).hexdigest()[:12]
            if ref in vistos:
                continue
            vistos.add(ref)
            # En la web EN VIVO los href son relativos a la raíz (/ayuntamiento/…);
            # hay que resolverlos a absolutos o el enlace apunta a localhost.
            url = urljoin(self.SITE + "/", a["href"])
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=self.ORGANISMO,
                    fecha_publicacion=self._fecha_tarjeta(a),
                    url_html=url,
                    url_pdf=None,
                )
            )
        return anuncios

    def _fecha_tarjeta(self, a) -> Optional[date]:
        """Fecha de la ``start-time`` de la tarjeta del enlace, acotando la
        búsqueda al propio ítem (nunca a un contenedor con varias tarjetas)."""
        node = a
        for _ in range(4):
            node = node.parent
            if node is None or getattr(node, "name", None) in ("body", "main", "section", "nav"):
                return None
            if len(node.select('h3 a[href*="/Empleo-Publico/"]')) > 1:
                return None  # es el contenedor del listado, no un ítem
            t = node.select_one('div.start-time time[datetime]') or node.select_one('div.end-time time[datetime]')
            if t:
                return self._iso(t["datetime"])
        return None

    @staticmethod
    def _iso(s: str) -> Optional[date]:
        try:
            return date.fromisoformat((s or "")[:10])
        except ValueError:
            return None

    def _obtener(self, url, fetch_fn):
        try:
            return fetch_fn(url) if fetch_fn else self.fetch(url)
        except Exception:  # noqa: BLE001
            return None

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        # Las tres páginas (oposiciones, concursos, bolsas) se descargan EN
        # PARALELO en vivo: así el tiempo es el de la más lenta, no la suma.
        if fetch_fn is not None:
            htmls = [self._obtener(u, fetch_fn) for u in self.URLS]
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(self.URLS)) as ex:
                htmls = list(ex.map(lambda u: self._obtener(u, None), self.URLS))
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for html in htmls:
            if not html:
                continue
            for an in self.parse_html(html):
                if an.referencia_oficial in vistos:
                    continue
                vistos.add(an.referencia_oficial)
                anuncios.append(an)
        if not anuncios:
            raise SumarioNoDisponible("El portal de empleo de Antequera no devolvió resultados.")
        return anuncios
