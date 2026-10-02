"""Conector para el BOE (API oficial de datos abiertos).

Descarga el sumario de un día y extrae los anuncios de la sección de
oposiciones ("2B"). La descarga real usa `requests` con la cabecera Accept;
para pruebas se puede inyectar un `fetch_fn` que devuelva el JSON de ejemplo.
"""

from __future__ import annotations

import datetime as dt
import re
from datetime import date
from typing import Callable, Optional

import requests

from .. import config
from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible


def _fecha_str(fecha) -> str:
    """Normaliza la fecha a 'AAAAMMDD'."""
    if isinstance(fecha, (date, dt.datetime)):
        return fecha.strftime("%Y%m%d")
    return str(fecha)


def _parse_fecha_boe(valor) -> Optional[date]:
    try:
        return dt.datetime.strptime(str(valor), "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _as_list(valor):
    """El JSON del BOE usa un objeto cuando hay un solo elemento y una lista
    cuando hay varios; esto lo homogeneiza siempre a lista."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _texto_url(campo):
    """`url_pdf` viene como objeto {'texto': ...}; `url_html`/`url_xml` como str."""
    if isinstance(campo, dict):
        return campo.get("texto")
    return campo


class ConectorBOE(ConectorBase):
    codigo = config.FUENTE_BOE

    def fetch_sumario(self, fecha) -> dict:
        """Descarga real del sumario del BOE para `fecha` (formato AAAAMMDD)."""
        url = config.BOE_API_SUMARIO.format(fecha=_fecha_str(fecha))
        resp = requests.get(
            url,
            headers={"Accept": config.BOE_ACCEPT},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 404:
            raise SumarioNoDisponible(
                f"El BOE del {_fecha_str(fecha)} aún no está disponible."
            )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as e:
            raise SumarioNoDisponible(
                f"El BOE del {_fecha_str(fecha)} no devolvió un sumario válido."
            ) from e
        self._verificar_disponible(data, fecha)
        return data

    @staticmethod
    def _verificar_disponible(data, fecha) -> None:
        """La API puede responder 200 aunque no haya boletín ese día (fines de
        semana, festivos o fechas futuras): el aviso llega en el envoltorio
        ('status.code' != 200) o simplemente no viene 'sumario'. En esos casos
        lo tratamos como 'no disponible' para no confundirlo con «0 anuncios»."""
        envoltorio = data or {}
        codigo = str((envoltorio.get("status") or {}).get("code") or "200")
        sumario = (envoltorio.get("data") or {}).get("sumario")
        if codigo != "200" or not sumario:
            raise SumarioNoDisponible(
                f"El BOE del {_fecha_str(fecha)} no está disponible (sin boletín)."
            )

    def parse_sumario(self, data: dict) -> list[AnuncioNormalizado]:
        """Extrae los anuncios de la sección de oposiciones del JSON del sumario."""
        anuncios: list[AnuncioNormalizado] = []
        sumario = (data or {}).get("data", {}).get("sumario", {})
        meta = sumario.get("metadatos", {})
        fecha_pub = _parse_fecha_boe(meta.get("fecha_publicacion"))

        for diario in _as_list(sumario.get("diario")):
            for seccion in _as_list(diario.get("seccion")):
                if str(seccion.get("codigo")) != config.SECCION_OPOSICIONES:
                    continue
                for departamento in _as_list(seccion.get("departamento")):
                    self._recolectar_items(
                        departamento, departamento.get("nombre"), None,
                        fecha_pub, seccion, anuncios,
                    )
        return anuncios

    def _recolectar_items(self, nodo, organismo, epigrafe, fecha_pub, seccion, anuncios) -> None:
        """Recoge todos los <item> que cuelgan de `nodo` (departamento, epígrafe
        o el envoltorio 'texto'), bajando de forma recursiva. Robusto ante los
        niveles de agrupación extra de la sección de oposiciones: en el BOE real
        el departamento (p. ej. «ADMINISTRACIÓN LOCAL») envuelve los epígrafes en
        un nodo 'texto' (departamento → texto → epígrafe → item)."""
        if not isinstance(nodo, dict):
            return
        for item in _as_list(nodo.get("item")):
            if isinstance(item, dict):
                anuncios.append(self._to_anuncio(item, organismo, fecha_pub, seccion, epigrafe))
        # 'texto' es un envoltorio transparente: se recorre sin cambiar el contexto.
        for contenedor in _as_list(nodo.get("texto")):
            self._recolectar_items(contenedor, organismo, epigrafe, fecha_pub, seccion, anuncios)
        for ep in _as_list(nodo.get("epigrafe")):
            if isinstance(ep, dict):
                self._recolectar_items(
                    ep, organismo, ep.get("nombre") or epigrafe, fecha_pub, seccion, anuncios
                )
        for dep in _as_list(nodo.get("departamento")):
            if isinstance(dep, dict):
                self._recolectar_items(
                    dep, dep.get("nombre") or organismo, epigrafe, fecha_pub, seccion, anuncios
                )

    @staticmethod
    def _to_anuncio(item, organismo, fecha_pub, seccion, epigrafe) -> AnuncioNormalizado:
        return AnuncioNormalizado(
            referencia_oficial=item.get("identificador"),
            titulo=item.get("titulo") or "",
            organismo=organismo,
            fecha_publicacion=fecha_pub,
            url_pdf=_texto_url(item.get("url_pdf")),
            url_html=_texto_url(item.get("url_html")),
            url_xml=_texto_url(item.get("url_xml")),
            seccion=seccion.get("nombre"),
            epigrafe=epigrafe,
        )

    def buscar(self, fecha, fetch_fn: Optional[Callable] = None) -> list[AnuncioNormalizado]:
        data = fetch_fn(fecha) if fetch_fn else self.fetch_sumario(fecha)
        return self.parse_sumario(data)

    @staticmethod
    def _limpiar_texto(html: str) -> str:
        """Convierte el HTML de un anuncio en texto plano (sin scripts ni tags)."""
        from bs4 import BeautifulSoup  # import perezoso

        soup = BeautifulSoup(html or "", "html.parser")
        for t in soup(["script", "style"]):
            t.extract()
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    def fetch_texto(self, id_boe: str) -> str:
        """Descarga el texto del anuncio del BOE (txt.php) en limpio, acotado a
        los primeros ~8000 caracteres (donde se describe la convocatoria y el
        puesto). Uso BAJO DEMANDA (no en cada búsqueda: el cuerpo es muy largo)."""
        url = f"https://www.boe.es/diario_boe/txt.php?id={id_boe}"
        resp = requests.get(
            url, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return self._limpiar_texto(resp.text)[:8000]
