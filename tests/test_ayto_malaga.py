"""Conector del Ayuntamiento de Málaga (empleo público), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_malaga import ConectorMalaga
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTMLG, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTMLG")).__name__ == "ConectorMalaga"


def test_parse_omite_cerrados():
    anuncios = ConectorMalaga().parse_html(_html())
    # 3 convocatorias; la que tiene «Cerrado…» en Trámite se omite -> 2.
    assert len(anuncios) == 2
    refs = {a.referencia_oficial for a in anuncios}
    assert refs == {"MLG-260", "MLG-397"}
    assert "MLG-217" not in refs  # la cerrada
    for a in anuncios:
        assert a.referencia_oficial.startswith("MLG-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Málaga"
        # href real relativo -> el conector lo resuelve a absoluto.
        assert a.url_html.startswith("https://www.malaga.eu/")
        assert "detalle-de-la-convocatoria" in a.url_html and "id=" in a.url_html
        assert "cerrado" not in (a.epigrafe or "").lower()
    # Casa un perfil administrativo (Málaga).
    assert any("auxiliar administrativo" in a.titulo.lower() for a in anuncios)


def test_referencia_estable():
    r1 = {a.referencia_oficial for a in ConectorMalaga().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorMalaga().parse_html(_html())}
    assert r1 == r2 and len(r1) == 2


def test_buscar_sin_resultados_lanza():
    # Todo cerrado -> sin resultados -> SumarioNoDisponible.
    cerrado = (
        '<ul><li class="articulo"><h3>X</h3>'
        '<dl><dt>Trámite:</dt><dd>Cerrado plazo de presentación de solicitudes</dd></dl>'
        '<div class="actions"><a href="/x/detalle-de-la-convocatoria/index.html?id=9">Detalle</a></div>'
        '</li></ul>'
    )
    with pytest.raises(SumarioNoDisponible):
        ConectorMalaga().buscar("20260825", fetch_fn=lambda f: cerrado)
