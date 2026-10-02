"""Conector del Ayuntamiento de Nerja (tablón de empleo), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_nerja import ConectorNerja
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTNER, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTNER")).__name__ == "ConectorNerja"


def test_parse_nerja():
    anuncios = ConectorNerja().parse_html(_html())
    # 3 filas; la sesión de junta de gobierno se excluye -> 2 convocatorias.
    assert len(anuncios) == 2
    refs = {a.referencia_oficial for a in anuncios}
    assert refs == {"NER-158502", "NER-153192"}
    assert "NER-158662" not in refs  # sesión JGL excluida
    for a in anuncios:
        assert a.referencia_oficial.startswith("NER-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Nerja"
        # href real relativo -> el conector lo resuelve a absoluto.
        assert a.url_html.startswith("https://sedeelectronica.nerja.es/") and "expId=" in a.url_html

    # Casa perfiles (Málaga: administrativa e informática).
    textos = " ".join(a.titulo.lower() for a in anuncios)
    assert "auxiliar administrativo" in textos and ("informático" in textos or "informatico" in textos)

    # Fecha = inicio de exposición (primera fecha de la fila).
    aux = next(a for a in anuncios if a.referencia_oficial == "NER-158502")
    assert aux.fecha_publicacion and aux.fecha_publicacion.isoformat() == "2026-06-15"


def test_referencia_estable():
    r1 = {a.referencia_oficial for a in ConectorNerja().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorNerja().parse_html(_html())}
    assert r1 == r2 and len(r1) == 2


def test_buscar_sin_resultados_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorNerja().buscar("20260825", fetch_fn=lambda f: "<html><body>nada</body></html>")
