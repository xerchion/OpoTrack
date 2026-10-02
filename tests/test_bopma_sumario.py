"""Pruebas del sumario diario del BOP de Málaga (parseo del HTML, sin red)."""

from opotrack import config
from opotrack.fuentes.bop_malaga import ConectorBOPMA


def _html():
    with open(config.FIXTURE_BOPMA_SUMARIO, encoding="utf-8") as f:
        return f.read()


def test_sumario_extrae_edictos():
    anuncios = ConectorBOPMA().parse_sumario(_html(), "20260202")
    refs = [a.referencia_oficial for a in anuncios]
    assert len(anuncios) == 3
    assert "BOPMA-2026-300" in refs
    assert "BOPMA-2026-305" in refs
    assert all(a.fecha_publicacion.isoformat() == "2026-02-02" for a in anuncios)


def test_sumario_url_titulo_organismo():
    anuncios = {a.referencia_oficial: a for a in ConectorBOPMA().parse_sumario(_html(), "20260202")}
    e = anuncios["BOPMA-2026-300"]
    assert e.url_html.endswith("edicto=20260202-00300-2026-00")
    assert "Técnico" in e.titulo and "oposición" in e.titulo
    assert e.titulo.startswith("Bases")          # sin el municipio ni el [Edicto ...]
    assert "Antequera" in e.organismo


def test_buscar_con_fetch_fn_detecta_sumario():
    # Si fetch_fn devuelve el HTML del sumario, buscar() lo parsea como tal.
    anuncios = ConectorBOPMA().buscar("20260202", fetch_fn=lambda f: _html())
    assert len(anuncios) == 3
