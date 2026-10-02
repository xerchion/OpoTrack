"""Conector del Ayuntamiento de Córdoba (empleo público), sin red."""

import pytest

from opotrack import config
from opotrack.fuentes import get_conector
from opotrack.fuentes.ayto_cordoba import ConectorCordoba
from opotrack.fuentes.base import SumarioNoDisponible


def _html():
    with open(config.FIXTURE_AYTCOR, encoding="utf-8") as f:
        return f.read()


def test_registrado():
    assert type(get_conector("AYTCOR")).__name__ == "ConectorCordoba"


def test_parse_cordoba():
    anuncios = ConectorCordoba().parse_html(_html())
    # 2 convocatorias abiertas en el acordeón. La sección vacía no cuenta.
    assert len(anuncios) == 2
    refs = {a.referencia_oficial for a in anuncios}
    assert refs == {"COR-RHU03-2026-01", "COR-RHU10-2026-02"}
    for a in anuncios:
        assert a.referencia_oficial.startswith("COR-") and len(a.referencia_oficial) <= 40
        assert a.organismo == "Ayuntamiento de Córdoba"
        assert a.url_html == "https://www.cordoba.es/sede/tramites/empleo/convocatorias"

    # Fecha = inicio del plazo de presentación.
    rhu03 = next(a for a in anuncios if a.referencia_oficial == "COR-RHU03-2026-01")
    assert rhu03.fecha_publicacion and rhu03.fecha_publicacion.isoformat() == "2026-08-12"

    # Casa el perfil de informática (resto de España).
    assert any("informática" in a.titulo.lower() or "informatica" in a.titulo.lower() for a in anuncios)


def test_referencia_estable():
    r1 = {a.referencia_oficial for a in ConectorCordoba().parse_html(_html())}
    r2 = {a.referencia_oficial for a in ConectorCordoba().parse_html(_html())}
    assert r1 == r2 and len(r1) == 2


def test_buscar_sin_abiertas_devuelve_lista_vacia():
    # 0 convocatorias abiertas es un estado válido: devuelve [], no lanza
    # SumarioNoDisponible (el resumen mostrará «0/0», no «no hay publicación»).
    out = ConectorCordoba().buscar(
        "20260825", fetch_fn=lambda f: "<html><body>Sin convocatorias</body></html>"
    )
    assert out == []
