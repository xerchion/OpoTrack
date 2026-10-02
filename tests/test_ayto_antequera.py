"""Conector del Ayuntamiento de Antequera (empleo público), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_antequera import ConectorAntequera
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTANT, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTANT")).__name__ == "ConectorAntequera"


def test_parse_antequera():
    anuncios = ConectorAntequera().parse_html(_html())
    # 3 tarjetas de detalle -> 3 anuncios. Los enlaces de menú (sin slug) no cuentan.
    assert len(anuncios) == 3
    for a in anuncios:
        assert a.referencia_oficial.startswith("ANT-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Antequera"
        # El href real es relativo a la raíz; el conector lo resuelve a absoluto.
        assert a.url_html.startswith("https://www.antequera.es/")
        assert "/Empleo-Publico/oposiciones/" in a.url_html

    # Un perfil administrativo (Málaga) debe poder casar.
    assert any("auxiliar administrativo" in a.titulo.lower() for a in anuncios)

    # Conserje: fecha de publicación = start-time de la tarjeta.
    conserje = next(a for a in anuncios if "CONSERJE" in a.titulo)
    assert conserje.fecha_publicacion and conserje.fecha_publicacion.isoformat() == "2026-02-26"

    # La tarjeta sin fechas se incluye igualmente (fecha None).
    tecnico = next(a for a in anuncios if "TÉCNICO/A MEDIO" in a.titulo)
    assert tecnico.fecha_publicacion is None


def test_referencia_estable():
    r1 = {a.referencia_oficial for a in ConectorAntequera().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorAntequera().parse_html(_html())}
    assert r1 == r2 and len(r1) == 3


def test_buscar_combina_urls_y_dedup():
    # buscar() recorre las 3 URLs; con la misma fixture en todas, dedup por ref -> 3.
    anuncios = ConectorAntequera().buscar("20260825", fetch_fn=lambda u: _html())
    assert len(anuncios) == 3


def test_buscar_sin_resultados_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorAntequera().buscar("20260825", fetch_fn=lambda u: "<html><body>nada</body></html>")
