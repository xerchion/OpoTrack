"""Conector del BOP de Sevilla (misma plataforma que Granada), sin red."""

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.bop_granada import ConectorBOPS


def _html():
    with open(config.FIXTURE_BOPS, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("BOPS")).__name__ == "ConectorBOPS"


def test_parse_sevilla():
    anuncios = {a.referencia_oficial: a for a in ConectorBOPS().parse_html(_html(), "20260812")}
    assert "BOP-SE-2026-01234" in anuncios              # CVE de Sevilla detectado
    assert "APROBACION-PRESUPUESTO-ECIJA" in anuncios   # sin CVE -> id del enlace
    e = anuncios["BOP-SE-2026-01234"]
    assert e.url_html.startswith("https://bopsevilla.dipusevilla.es/")
    assert "INFORMÁTICA" in e.titulo.upper()
    assert e.fecha_publicacion.isoformat() == "2026-08-12"
