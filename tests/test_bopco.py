"""Conector del BOP de Córdoba (bop.dipucordoba.es), sin red."""

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.bop_cordoba import ConectorBOPCO


def _html():
    with open(config.FIXTURE_BOPCO, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("BOPCO")).__name__ == "ConectorBOPCO"


def test_parse_cordoba():
    a = {x.referencia_oficial: x for x in ConectorBOPCO().parse_html(_html(), "20260813")}
    assert "BOP-A-2026-2759" in a and "BOP-A-2026-2766" in a
    e = a["BOP-A-2026-2759"]
    assert "INFORMÁTICA" in e.titulo.upper()
    assert "PDF BOP-A" not in e.titulo        # el texto del enlace no queda en el título
    assert e.url_html.endswith("BOP-A-2026-2759.pdf")
    assert e.fecha_publicacion.isoformat() == "2026-08-13"


def test_jaen_registrado():
    # Jaén se registra igual, pero tiene su propio parser (ver test_bopja.py).
    assert type(get_conector("BOPJ")).__name__ == "ConectorBOPJA"
