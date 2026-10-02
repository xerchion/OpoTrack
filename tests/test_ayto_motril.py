"""Conector del Ayuntamiento de Motril (empleo público), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_motril import ConectorMotril
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTMOT, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTMOT")).__name__ == "ConectorMotril"


def test_parse_motril():
    anuncios = ConectorMotril().parse_html(_html())
    # 3 enlaces de detalle (/oferta-empleo/<slug>/). El índice de menú se ignora.
    assert len(anuncios) == 3
    for a in anuncios:
        assert a.referencia_oficial.startswith("MOT-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Motril"
        # href real puede ser relativo -> el conector lo resuelve a absoluto.
        assert a.url_html.startswith("https://motril.es/") and "/oferta-empleo/" in a.url_html
    assert len({a.referencia_oficial for a in anuncios}) == 3
    # Casa un perfil administrativo (Granada).
    assert any("auxiliar administrativo" in a.titulo.lower() for a in anuncios)


def test_referencia_estable():
    r1 = {a.referencia_oficial for a in ConectorMotril().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorMotril().parse_html(_html())}
    assert r1 == r2 and len(r1) == 3


def test_buscar_sin_resultados_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorMotril().buscar("20260825", fetch_fn=lambda f: "<html><body>nada</body></html>")
