"""Conector para el BOP de Málaga (BOPMA) vía datos abiertos de la Diputación.

El sumario web de bopmalaga.es se genera con JavaScript, pero la Diputación
publica los edictos como datos abiertos (opendata.malaga.es, CKAN). Este conector
consulta la API `datastore_search` filtrando por fecha; si no hay red, usa como
respaldo un CSV local que el usuario coloque en `config.BOPMA_CSV`.

Campos del recurso (mismos en API y CSV): edicto, ejercicio, boletin, procedencia,
provincia, municipio, tema, resumen, fecha_publicacion (DD/MM/AAAA), ...
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from datetime import date
from typing import Callable, Optional

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase

# API CKAN de datos abiertos de Málaga y recurso "Edictos del BOPMA".
_API = "https://opendata.malaga.es/api/action/datastore_search"
_RESOURCE_EDICTOS = "038cb9ca-70bd-4d28-a89e-e00bea05016a"


def _fecha_buscada(fecha) -> Optional[date]:
    if isinstance(fecha, date):
        return fecha
    s = str(fecha)
    if re.fullmatch(r"\d{8}", s):
        try:
            return dt.datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _ddmmaaaa(fecha) -> str:
    f = _fecha_buscada(fecha)
    return f.strftime("%d/%m/%Y") if f else str(fecha)


def _ddmmaaaa_guion(fecha) -> str:
    """DD-MM-AAAA para el parámetro ?fecha= del sumario del BOPMA."""
    f = _fecha_buscada(fecha)
    return f.strftime("%d-%m-%Y") if f else str(fecha)


def _parse_fecha_pub(valor) -> Optional[date]:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime((valor or "").strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


class ConectorBOPMA(ConectorBase):
    codigo = "BOPMA"

    # --- Fuentes de datos -------------------------------------------------
    def fetch_api(self, fecha) -> list[dict]:
        """Consulta la API CKAN filtrando por fecha_publicacion. Devuelve los
        registros (lista de dicts)."""
        params = {
            "resource_id": _RESOURCE_EDICTOS,
            "filters": json.dumps({"fecha_publicacion": _ddmmaaaa(fecha)}),
            "limit": 1000,
        }
        resp = requests.get(_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("records", []) or []

    def leer_csv(self) -> str:
        """Lee el CSV local si existe (detecta codificación; los datos abiertos
        de Málaga vienen en Latin-1/cp1252)."""
        ruta = config.BOPMA_CSV
        if not ruta.exists():
            return ""
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return ruta.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return ruta.read_text(encoding="cp1252", errors="replace")

    def fetch_sumario(self, fecha) -> str:
        """Descarga el HTML del sumario del BOP de Málaga para un día (la 'vía
        del día'). El sitio solo responde a un User-Agent de navegador; a otros
        les devuelve una página vacía. Cadena vacía si no hay boletín (404)."""
        resp = requests.get(
            config.BOPMA_SUMARIO,
            params={"fecha": _ddmmaaaa_guion(fecha)},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text

    def parse_sumario(self, html: str, fecha=None) -> list[AnuncioNormalizado]:
        """Extrae los edictos del HTML del sumario. Cada edicto es un <article>
        dentro de una <section> (cuyo <h3> es la categoría/procedencia); el <p>
        lleva el municipio en <b>, el resumen y el enlace [Edicto NNNN/AAAA]."""
        if not html:
            return []
        from bs4 import BeautifulSoup  # import perezoso

        soup = BeautifulSoup(html, "html.parser")
        f = _fecha_buscada(fecha)
        anuncios: list[AnuncioNormalizado] = []
        vistos: set[str] = set()
        for sec in soup.find_all("section"):
            h3 = sec.find("h3")
            seccion = h3.get_text(" ", strip=True) if h3 else ""
            for art in sec.find_all("article"):
                p = art.find("p")
                if not p:
                    continue
                a = p.find("a", href=re.compile(r"edicto", re.I))
                if not a:
                    continue
                etiqueta = a.get("title") or a.get_text(" ", strip=True) or ""
                m = re.search(r"(\d+)\s*/\s*(\d{4})", etiqueta)
                if not m:
                    continue
                edicto, anio = m.group(1), m.group(2)
                ref = f"BOPMA-{anio}-{edicto}"
                if ref in vistos:
                    continue
                vistos.add(ref)
                b = p.find("b")
                municipio = b.get_text(" ", strip=True) if b else ""
                href = a.get("href") or ""
                url = href if href.startswith("http") else "https://www.bopmalaga.es/" + href.lstrip("/")
                for t in p.find_all(["a", "b"]):   # deja solo el texto del resumen
                    t.extract()
                resumen = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip(" .[]·-")
                if not resumen:
                    resumen = etiqueta
                organismo = " · ".join(x for x in (seccion, municipio) if x) or None
                anuncios.append(
                    AnuncioNormalizado(
                        referencia_oficial=ref,
                        titulo=resumen,
                        organismo=organismo,
                        fecha_publicacion=f,
                        url_html=url,
                    )
                )
        return anuncios

    # --- Mapeo y parseo ---------------------------------------------------
    @staticmethod
    def _row_to_anuncio(row) -> Optional[AnuncioNormalizado]:
        resumen = (row.get("resumen") or "").strip()
        if not resumen:
            return None
        ref = "BOPMA-{}-{}-{}".format(
            str(row.get("ejercicio") or "").strip(),
            str(row.get("boletin") or "").strip(),
            str(row.get("edicto") or "").strip(),
        )
        procedencia = (row.get("procedencia") or "").strip()
        municipio = (row.get("municipio") or "").strip()
        organismo = " · ".join(p for p in (procedencia, municipio) if p) or None
        return AnuncioNormalizado(
            referencia_oficial=ref,
            titulo=resumen,
            organismo=organismo,
            fecha_publicacion=_parse_fecha_pub(row.get("fecha_publicacion")),
            url_html=None,
        )

    def parse_rows(self, rows, fecha=None) -> list[AnuncioNormalizado]:
        objetivo = _fecha_buscada(fecha)
        anuncios: list[AnuncioNormalizado] = []
        for row in rows:
            a = self._row_to_anuncio(row)
            if a is None:
                continue
            if objetivo and a.fecha_publicacion != objetivo:
                continue
            anuncios.append(a)
        return anuncios

    def parse_csv(self, texto: str, fecha=None) -> list[AnuncioNormalizado]:
        if not texto:
            return []
        return self.parse_rows(csv.DictReader(io.StringIO(texto)), fecha)

    # --- Interfaz ---------------------------------------------------------
    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        if fetch_fn is not None:
            datos = fetch_fn(fecha)
            if isinstance(datos, str):
                # Puede ser el HTML del sumario del día o un CSV de datos abiertos.
                if "<article" in datos or "edicto.php" in datos:
                    return self.parse_sumario(datos, fecha)
                return self.parse_csv(datos, fecha)
            return self.parse_rows(datos or [], fecha)  # registros de la API
        # Real: 1) sumario del día (bopmalaga.es, sin desfase); 2) API CKAN de
        # datos abiertos (histórico, con desfase); 3) CSV local de respaldo.
        try:
            anuncios = self.parse_sumario(self.fetch_sumario(fecha), fecha)
            if anuncios:
                return anuncios
        except Exception:
            pass
        try:
            records = self.fetch_api(fecha)
            if records:
                return self.parse_rows(records, fecha)
        except Exception:
            pass
        return self.parse_csv(self.leer_csv(), fecha)
