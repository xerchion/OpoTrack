"""Conector del BOP de Jaén (bop.dipujaen.es), sin red.

Estructura real: <div id='sumarioBoletin'> con <p class='subseccion'> por
organismo y un <article> por anuncio (título en <p class='edicto'> y enlace al
PDF descargarws.dip). Referencia BOP-AAAA-NNNN.
"""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.base import SumarioNoDisponible
from opotrack.fuentes.bop_cordoba import ConectorBOPJA


def _html():
    with open(config.FIXTURE_BOPJA, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("BOPJ")).__name__ == "ConectorBOPJA"


def test_parse_jaen():
    a = {x.referencia_oficial: x for x in ConectorBOPJA().parse_html(_html(), "20260820")}
    assert set(a) == {"BOP-2026-3979", "BOP-2026-3973", "BOP-2026-3823"}
    # La oposición de Mengíbar: título, organismo y enlace correctos.
    op = a["BOP-2026-3823"]
    assert "concurso-oposición" in op.titulo.lower()
    assert "plaza" in op.titulo.lower()
    assert op.organismo == "AYUNTAMIENTO DE MENGÍBAR (JAÉN)"
    assert "numeroEdicto=3823" in op.url_pdf
    assert op.fecha_publicacion.isoformat() == "2026-08-20"
    # Cada anuncio arrastra su organismo (subsección) vigente.
    assert a["BOP-2026-3973"].organismo == "AYUNTAMIENTO DE FUERTE DEL REY (JAÉN)"
    assert a["BOP-2026-3979"].organismo == "DIPUTACIÓN PROVINCIAL DE JAÉN"
    # El texto del enlace (nombre del PDF) no ensucia el título.
    assert "BOP-2026-3823" not in op.titulo


def test_buscar_con_fixture():
    assert len(ConectorBOPJA().buscar("20260820", fetch_fn=lambda f: _html())) == 3


def test_buscar_sin_boletin_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorBOPJA().buscar("20260823", fetch_fn=lambda f: "<html><body>sin sumario</body></html>")
