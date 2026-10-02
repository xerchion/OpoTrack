"""Conector del tablón de empleo del Ayuntamiento de Nerja (Málaga).

La sede ``sedeelectronica.nerja.es`` publica el empleo en un «tablón virtual»
(servlet Java) servido por servidor. La sección de empleo (``subseccion=DEP.EMP``)
es una tabla con una fila por expediente:

    <tr class="Lista2LineaPar" id="exp_158502">
      <td>2026</td><td>10</td>
      <td>Procesos selectivos de personal laboral (indefinido y temporal)</td>
      <td><a href="…/tablonVirtual.do?expId=158502&…">CONVOCATORIA Y BASES…</a></td>
      <td>15/06/2026</td>   <!-- inicio de exposición -->
      <td>14/07/2026</td>   <!-- fin de exposición -->
    </tr>

Se trata cada fila (``expId``) como un anuncio. La referencia es el ``expId`` y
la fecha, el inicio de exposición. NB: la fecha de fin es de exposición en el
tablón (no el plazo del proceso, que puede seguir vivo), así que NO se filtra por
ella. Se descartan las filas que no son convocatorias (p. ej. sesiones de junta
de gobierno). El motor se queda con lo nuevo por referencia.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible


class ConectorNerja(ConectorBase):
    codigo = "AYTNER"
    ORGANISMO = "Ayuntamiento de Nerja"
    SITE = "https://sedeelectronica.nerja.es"
    LANDING = SITE + "/portal/tablonVirtual.do?subseccion=DEP.EMP&opc_id=175&ent_id=1&idioma=1"
    URL = SITE + "/portal/tablonVirtual.do?subseccion=DEP.EMP&opc_id=175&pes_cod=5&ent_id=1&idioma=1"
    FECHA_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
    EXCLUIR_CATEGORIA = re.compile(r"junta de gobierno", re.IGNORECASE)

    def fetch(self) -> str:
        # El servlet puede exigir una sesión: visitamos primero la vista de la
        # sección (establece cookies) y luego pedimos el tablón de empleo.
        s = requests.Session()
        s.headers["User-Agent"] = config.USER_AGENT
        # Visita corta a la landing solo para tomar la cookie de sesión; si tarda,
        # se sigue igual (no debe dominar el tiempo de la búsqueda).
        try:
            s.get(self.LANDING, timeout=6)
        except requests.RequestException:
            pass
        resp = s.get(self.URL, timeout=config.HTTP_TIMEOUT)
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
        for tr in soup.select('tr[id^="exp_"]'):
            a = tr.find("a", href=re.compile(r"expId=\d+"))
            if not a:
                continue
            m = re.search(r"expId=(\d+)", a["href"])
            if not m:
                continue
            eid = m.group(1)
            tds = tr.find_all("td", recursive=False)
            categoria = re.sub(r"\s+", " ", tds[2].get_text(" ", strip=True)) if len(tds) > 2 else ""
            if self.EXCLUIR_CATEGORIA.search(categoria):
                continue  # p. ej. «Expedientes de la junta de gobierno»: no es convocatoria
            titulo = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            if len(titulo) < 4:
                continue
            ref = "NER-" + eid
            if ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=self.ORGANISMO,
                    fecha_publicacion=self._fecha(tr),
                    url_html=urljoin(self.SITE + "/", a["href"]),
                    url_pdf=None,
                )
            )
        return anuncios

    def _fecha(self, tr) -> Optional[date]:
        """Fecha de inicio de exposición (primera fecha DD/MM/AAAA de la fila)."""
        m = self.FECHA_RE.search(tr.get_text(" ", strip=True))
        if not m:
            return None
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch()
        anuncios = self.parse_html(html)
        if not anuncios:
            raise SumarioNoDisponible("El tablón de empleo de Nerja no devolvió resultados.")
        return anuncios
