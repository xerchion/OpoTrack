"""Conector del Ayuntamiento de Benalmádena (convocatorias de personal), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_benalmadena import ConectorBenalmadena
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTBEN, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTBEN")).__name__ == "ConectorBenalmadena"


def test_parse_benalmadena():
    a = {x.referencia_oficial: x for x in ConectorBenalmadena().parse_html(_html())}
    assert set(a) == {"C264", "C286", "C273", "C248"}
    info = a["C286"]
    assert "INFORMÁTICA" in info.titulo.upper()
    assert info.organismo == "Ayuntamiento de Benalmádena"
    assert info.url_html.endswith("OEP-2022.html")
    assert info.fecha_publicacion.isoformat() == "2026-05-27"
    # El título es el nombre de la convocatoria, no la fecha.
    assert "/" not in a["C264"].titulo
    assert "AUXILIAR DE BIBLIOTECA" in a["C264"].titulo.upper()


def test_buscar_con_fixture():
    assert len(ConectorBenalmadena().buscar("20260820", fetch_fn=lambda f: _html())) == 4


def test_buscar_sin_resultados_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorBenalmadena().buscar(
            "20260820", fetch_fn=lambda f: "<html><body>nada</body></html>"
        )
