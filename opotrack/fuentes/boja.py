"""Conector para el BOJA (Boletín Oficial de la Junta de Andalucía) vía RSS.

La web del BOJA carga el sumario con JavaScript (el HTML servido a un programa
no trae los enlaces del boletín), así que no se puede scrapear como Granada.
Pero la Junta publica feeds RSS por sección: /boja/distribucion/sXX.xml. La
sección 2.2 (Oposiciones, concursos y otras convocatorias) es la s53. Este
conector descarga ese RSS (XML estático) y extrae los items.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase

# Feed RSS de la sección 2.2 "Oposiciones, concursos y otras convocatorias".
RSS_OPOSICIONES = "https://www.juntadeandalucia.es/boja/distribucion/s53.xml"

_LOCALES = ("item", "entry")   # RSS y Atom


def _fecha_date(fecha) -> Optional[date]:
    if isinstance(fecha, date):
        return fecha
    s = str(fecha)
    if re.fullmatch(r"\d{8}", s):
        try:
            return dt.datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _parse_pubdate(txt: str) -> Optional[date]:
    if not txt:
        return None
    try:
        return parsedate_to_datetime(txt).date()   # RFC-822: "Wed, 06 Aug 2026 ..."
    except (TypeError, ValueError, IndexError):
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", txt) or re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if not m:
        return None
    try:
        if "-" in m.group(0):
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _tag(elem) -> str:
    return elem.tag.split("}")[-1]


def _campo(item, *nombres) -> str:
    for ch in item:
        if _tag(ch) in nombres:
            valor = (ch.text or ch.get("href") or "").strip()
            if valor:
                return valor
    return ""


class ConectorBOJA(ConectorBase):
    codigo = "BOJA"

    def fetch_rss(self) -> str:
        resp = requests.get(
            RSS_OPOSICIONES, headers={"User-Agent": config.USER_AGENT}, timeout=30
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text

    def parse_rss(self, xml_text: str, fecha=None) -> list[AnuncioNormalizado]:
        if not xml_text:
            return []
        try:
            root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        except ET.ParseError:
            return []

        f = _fecha_date(fecha)
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for item in (e for e in root.iter() if _tag(e) in _LOCALES):
            titulo = _campo(item, "title")
            link = _campo(item, "link")
            desc = _campo(item, "description", "summary")
            pub = _campo(item, "pubDate", "date", "published", "updated")
            if not titulo and not desc:
                continue
            fpub = _parse_pubdate(pub) or f
            ref = self._referencia(link, titulo)
            if ref in vistos:
                continue
            vistos.add(ref)
            anuncios.append(
                AnuncioNormalizado(
                    referencia_oficial=ref,
                    titulo=titulo or desc,
                    organismo=self._organismo(item),
                    fecha_publicacion=fpub,
                    url_html=link or None,
                )
            )
        return anuncios

    @staticmethod
    def _referencia(link: str, titulo: str) -> str:
        m = re.search(r"/(?:e)?boja/(\d+)/(\d+)/([\w.-]+)", link or "")
        if m:
            return f"BOJA-{m.group(1)}-{m.group(2)}-{m.group(3).split('.')[0]}"
        m = re.search(r"(\d{6,})", link or "")
        if m:
            return f"BOJA-{m.group(1)}"
        return link or titulo[:60]

    @staticmethod
    def _organismo(item) -> Optional[str]:
        """El organismo va dentro del <content> del entry: 'Organismo: Consejería…'."""
        for ch in item:
            if _tag(ch) == "content":
                texto = " ".join(t.strip() for t in ch.itertext() if t and t.strip())
                m = re.search(
                    r"Organismo:\s*(.+?)\s*(?:Administraci|Secci[oó]n|Bolet[ií]n|$)", texto
                )
                if m and m.group(1).strip():
                    return m.group(1).strip()
        return None

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        xml_text = fetch_fn(fecha) if fetch_fn is not None else self.fetch_rss()
        return self.parse_rss(xml_text, fecha)
