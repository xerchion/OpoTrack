"""Conector del Ayuntamiento de Loja (empleo público), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_loja import ConectorLoja
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTLOJA, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTLOJA")).__name__ == "ConectorLoja"


def test_parse_loja():
    anuncios = ConectorLoja().parse_html(_html())
    # 7 PDFs en el contenido -> 7 anuncios (el PDF del menú de navegación se ignora).
    assert len(anuncios) == 7
    assert all("acoso_laboral" not in (a.url_pdf or "").lower() for a in anuncios)
    for a in anuncios:
        assert a.referencia_oficial.startswith("LOJA-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Loja"
        assert a.url_pdf and a.url_pdf.endswith(".pdf")
    textos = " ; ".join(a.titulo for a in anuncios)
    # Casos administrativos (deben poder casar el perfil de Granada).
    assert "auxiliar administrativo" in textos.lower()
    # Un título genérico («Descargar Bases.») se sustituye por el nombre del archivo.
    assert any("educadoras sociales" in a.titulo.lower() for a in anuncios)
    # Fecha extraída del texto del enlace.
    aux = [a for a in anuncios if "boe 1 auxiliar" in a.titulo.lower()][0]
    assert aux.fecha_publicacion and aux.fecha_publicacion.isoformat() == "2026-06-10"


def test_referencia_estable():
    # La misma página parseada dos veces da las mismas referencias (dedupe fiable).
    r1 = {a.referencia_oficial for a in ConectorLoja().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorLoja().parse_html(_html())}
    assert r1 == r2 and len(r1) == 7


def test_buscar_sin_resultados_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorLoja().buscar("20260820", fetch_fn=lambda f: "<html><body>nada</body></html>")
