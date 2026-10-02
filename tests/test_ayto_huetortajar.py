"""Conector del Ayuntamiento de Huétor Tájar (empleo público), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_huetortajar import ConectorHuetorTajar
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTHT, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTHT")).__name__ == "ConectorHuetorTajar"


def test_parse_huetortajar():
    anuncios = ConectorHuetorTajar().parse_html(_html())
    # 4 encabezados con PDFs -> 4 anuncios. El separador «CONSOLIDACIÓN…» (sin
    # PDFs) y el PDF del menú de navegación (fuera de la <section>) se ignoran.
    assert len(anuncios) == 4
    assert all("protocolo-de-acoso" not in (a.url_pdf or "").lower() for a in anuncios)
    for a in anuncios:
        assert a.referencia_oficial.startswith("HT-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Huétor Tájar"
        assert a.url_pdf and a.url_pdf.endswith(".pdf")  # nunca el .doc del anexo

    por_titulo = {a.titulo: a for a in anuncios}
    # Un perfil administrativo (Granada) debe poder casar.
    assert any("administrativo" in t.lower() for t in por_titulo)

    # TAG: fecha = la más antigua del bloque (origen) y enlace = el de las bases.
    tag = next(a for a in anuncios if "Técnico de Administración General" in a.titulo)
    assert tag.fecha_publicacion and tag.fecha_publicacion.isoformat() == "2026-06-30"
    assert "Bases-y-convocatoria" in tag.url_pdf

    # Policía: ningún PDF dice «bases», así que se toma el más antiguo (la
    # convocatoria), NO el de «convocatoria cuarta prueba» más reciente.
    pol = next(a for a in anuncios if "policía local" in a.titulo.lower())
    assert pol.url_pdf.endswith("Convocatoria-de-cuatro-plazas-de-policia-local-en-turno-libre.pdf")
    assert pol.fecha_publicacion.isoformat() == "2025-10-30"


def test_referencia_estable():
    r1 = {a.referencia_oficial for a in ConectorHuetorTajar().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorHuetorTajar().parse_html(_html())}
    assert r1 == r2 and len(r1) == 4


def test_buscar_sin_resultados_lanza():
    with pytest.raises(SumarioNoDisponible):
        ConectorHuetorTajar().buscar("20260820", fetch_fn=lambda f: "<html><body>nada</body></html>")
