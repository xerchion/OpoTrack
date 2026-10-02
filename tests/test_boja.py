"""Pruebas del conector del BOJA (feed Atom de la sección de oposiciones)."""

from opotrack import config, extraccion
from opotrack.fuentes.boja import ConectorBOJA


def _xml():
    with open(config.FIXTURE_BOJA, encoding="utf-8") as f:
        return f.read()


def test_parser_extrae_items():
    anuncios = ConectorBOJA().parse_rss(_xml(), "20260806")
    refs = [a.referencia_oficial for a in anuncios]
    assert len(anuncios) == 2
    assert "BOJA-2026-151-32" in refs         # referencia limpia, sin .html ni URL larga
    assert all(a.fecha_publicacion.isoformat() == "2026-08-06" for a in anuncios)


def test_url_titulo_y_organismo():
    anuncios = {a.referencia_oficial: a for a in ConectorBOJA().parse_rss(_xml(), "20260806")}
    a = anuncios["BOJA-2026-151-32"]
    assert a.url_html.endswith("/boja/2026/151/32.html")
    assert "Universidad de Jaén" in a.titulo
    assert a.organismo == "Universidades"     # extraído del <content> del feed


def test_extraccion_sobre_item():
    anuncios = {a.referencia_oficial: a for a in ConectorBOJA().parse_rss(_xml(), "20260806")}
    d = extraccion.extraer(anuncios["BOJA-2026-151-32"])
    assert d["puesto"] and "PROFESOR" in d["puesto"].upper()
    assert d["sistema_acceso"] == "concurso"
