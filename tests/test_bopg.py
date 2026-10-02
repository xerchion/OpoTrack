"""Pruebas del conector del BOP de Granada (parseo del HTML, sin red)."""

from opotrack import config
from opotrack.fuentes.bop_granada import ConectorBOPG


def _html():
    with open(config.FIXTURE_BOPG, encoding="utf-8") as f:
        return f.read()


def test_parser_extrae_anuncios():
    anuncios = ConectorBOPG().parse_html(_html(), "20260423")
    refs = [a.referencia_oficial for a in anuncios]
    assert len(anuncios) == 5
    # El CVE del boletín (3 dígitos) no debe colarse como anuncio.
    assert "BOP-GRA-2026-076" not in refs
    assert "BOP-GRA-2026-076003" in refs


def test_titulos_traen_el_puesto():
    anuncios = {a.referencia_oficial: a for a in ConectorBOPG().parse_html(_html(), "20260423")}
    info = anuncios["BOP-GRA-2026-076003"]
    assert "INFORMÁTICO" in info.titulo.upper()
    assert info.url_html.endswith("/BASES-PLAZA-TECNICO-INFORMATICO-LA-ZUBIA/")
    assert info.fecha_publicacion is not None and info.fecha_publicacion.year == 2026


def test_extraccion_sobre_titulo_bopg():
    from opotrack import extraccion
    anuncios = {a.referencia_oficial: a for a in ConectorBOPG().parse_html(_html(), "20260423")}
    d = extraccion.extraer(anuncios["BOP-GRA-2026-076003"])
    assert d["puesto"] and "INFORM" in d["puesto"].upper()
    assert d["tipo_personal"] == "funcionario"
    assert d["sistema_acceso"] == "oposición"
