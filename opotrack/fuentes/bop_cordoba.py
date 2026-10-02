"""Conectores de BOP sobre la plataforma «BOP Digit@l» de las Diputaciones
(Córdoba, Jaén…).

La página de un día es `.../{ruta}/DD-MM-AAAA` (HTML servido solo a navegadores).
Cada anuncio es un `<li class="announcement">` con su texto descriptivo y un
enlace a su PDF; la referencia es el código del PDF (p. ej. BOP-A-AAAA-NNNN) o,
si no aparece, el propio nombre del enlace. Las subclases solo cambian la URL.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible
from .bop_granada import _fecha_date, _fecha_ddmmaaaa


class ConectorBOPCO(ConectorBase):
    codigo = "BOPCO"
    URL = "https://bop.dipucordoba.es/dia/{fecha}"
    REF = re.compile(r"BOP-A-\d{4}-\d+", re.IGNORECASE)

    def fetch_dia(self, fecha) -> str:
        """Descarga el HTML del BOP para un día. '' si no hay (404). El sitio
        solo responde a un User-Agent de navegador."""
        url = self.URL.format(fecha=_fecha_ddmmaaaa(fecha))
        resp = requests.get(
            url, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text

    def parse_html(self, html: str, fecha=None) -> list[AnuncioNormalizado]:
        if not html:
            return []
        from bs4 import BeautifulSoup  # import perezoso

        soup = BeautifulSoup(html, "html.parser")
        f = _fecha_date(fecha)
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for li in soup.find_all("li", class_="announcement"):
            a = li.find("a", href=True)
            href = a["href"] if a else None
            if not href:
                continue
            m = self.REF.search(li.get_text(" ", strip=True)) or self.REF.search(href)
            # Referencia: el código del anuncio si aparece; si no, el id del enlace.
            ref = m.group(0).upper() if m else href.rstrip("/").rsplit("/", 1)[-1]
            if ref in vistos:
                continue
            vistos.add(ref)
            for x in li.find_all("a"):        # quita los enlaces del texto del título
                x.extract()
            titulo = re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip() or ref
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo,
                    organismo=None,
                    fecha_publicacion=f,
                    url_html=href,
                    url_pdf=href,
                )
            )
        return anuncios

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        html = fetch_fn(fecha) if fetch_fn else self.fetch_dia(fecha)
        anuncios = self.parse_html(html, fecha)
        if not anuncios:
            # Un boletín válido siempre trae anuncios; 0 = no hay boletín ese día
            # → se marca "sin publicación" en el resumen.
            raise SumarioNoDisponible(
                f"El BOP ({self.codigo}) del {_fecha_ddmmaaaa(fecha)} no está publicado."
            )
        return anuncios


class ConectorBOPJA(ConectorBOPCO):
    """BOP de la provincia de Jaén. Comparte la marca «BOP Digit@l» con Córdoba,
    pero su HTML es distinto: el sumario cuelga de ``<div id='sumarioBoletin'>``,
    con un ``<p class='subseccion'>`` por organismo y un ``<article>`` por
    anuncio (título en ``<p class='edicto'>`` y enlace al PDF ``descargarws.dip``).
    La referencia es BOP-AAAA-NNNN (sin la «A» de Córdoba). Reutiliza
    ``fetch_dia``/``buscar`` de la base y solo cambia el parser, la URL y la
    referencia."""

    codigo = "BOPJ"
    URL = "https://bop.dipujaen.es/bop/{fecha}"
    REF = re.compile(r"BOP-\d{4}-\d+", re.IGNORECASE)

    def parse_html(self, html: str, fecha=None) -> list[AnuncioNormalizado]:
        if not html:
            return []
        from bs4 import BeautifulSoup  # import perezoso

        soup = BeautifulSoup(html, "html.parser")
        cont = soup.find("div", id="sumarioBoletin")
        if cont is None:
            return []
        f = _fecha_date(fecha)
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        organismo = None
        # Recorremos p y article en orden para arrastrar el organismo vigente.
        for el in cont.find_all(["p", "article"]):
            if el.name == "p":
                if "subseccion" in (el.get("class") or []):
                    organismo = el.get_text(" ", strip=True) or organismo
                continue
            # el.name == "article": un anuncio (edicto)
            tit = el.find("p", class_="edicto")
            titulo = re.sub(r"\s+", " ", tit.get_text(" ", strip=True)).strip() if tit else ""
            a = el.find("a", href=True)
            href = a["href"] if a else None
            texto = el.get_text(" ", strip=True)
            m = self.REF.search(texto) or (self.REF.search(href) if href else None)
            if m:
                ref = m.group(0).upper()
            elif href:
                ej = re.search(r"ejercicioBop=(\d+)", href)
                num = re.search(r"numeroEdicto=(\d+)", href)
                ref = f"BOP-{ej.group(1)}-{num.group(1)}" if (ej and num) else None
            else:
                ref = None
            if not ref or ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo or ref,
                    organismo=organismo,
                    fecha_publicacion=f,
                    url_html=href,
                    url_pdf=href,
                )
            )
        return anuncios
