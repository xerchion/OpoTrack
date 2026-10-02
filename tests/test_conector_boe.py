"""Pruebas del conector BOE y de la regla de filtrado (ámbito × rama).

Usan el sumario de ejemplo (fixtures/sumario_ejemplo.json), sin acceso a la red.
Ejecutar con:  python3 -m pytest tests/ -v
"""

import json

import pytest

from opotrack import config
from opotrack.fuentes.base import SumarioNoDisponible
from opotrack.fuentes.boe import ConectorBOE
from opotrack.motor import evaluar, normaliza
from opotrack.seed import PERFILES


def cargar_fixture() -> dict:
    with open(config.FIXTURE_SUMARIO, encoding="utf-8") as f:
        return json.load(f)


def perfiles_normalizados() -> list[dict]:
    """Reproduce lo que hace el motor al cargar los perfiles de la BBDD."""
    salida = []
    for p in PERFILES:
        salida.append(
            {
                "nombre": p["nombre"],
                "tematicas": [normaliza(t) for t in p["tematicas"]],
                "geograficas": [normaliza(g) for g in p["geograficas"]],
                "exclusiones": [normaliza(e) for e in p["exclusiones"]],
            }
        )
    return salida


def anuncios_por_ref() -> dict:
    conector = ConectorBOE()
    return {a.referencia_oficial: a for a in conector.parse_sumario(cargar_fixture())}


def test_parser_extrae_solo_la_seccion_de_oposiciones():
    anuncios = anuncios_por_ref()
    # 6 items en la sección 2B; el de la sección I queda fuera.
    assert len(anuncios) == 6
    assert "BOE-A-2026-19000" not in anuncios       # sección I. Disposiciones generales
    assert "BOE-A-2026-20002" in anuncios


def test_parser_lee_los_campos_del_item():
    a = anuncios_por_ref()["BOE-A-2026-20002"]
    assert a.organismo == "DIPUTACIÓN PROVINCIAL DE GRANADA"
    assert a.url_pdf.endswith("BOE-A-2026-20002.pdf")
    assert a.url_html.endswith("id=BOE-A-2026-20002")
    assert a.fecha_publicacion is not None and a.fecha_publicacion.year == 2026


def test_regla_ambito_rama():
    anuncios = anuncios_por_ref()
    perfiles = perfiles_normalizados()

    def casa(ref):
        return evaluar(anuncios[ref], perfiles) is not None

    # Administrativo SOLO cuenta en Granada/Málaga.
    assert casa("BOE-A-2026-20002")        # Administrativo, Granada -> entra
    assert not casa("BOE-A-2026-20001")    # Administrativo, estatal -> fuera
    assert not casa("BOE-A-2026-20003")    # Administrativo, Sevilla -> fuera
    # Informática entra en cualquier ámbito.
    assert casa("BOE-A-2026-20004")        # Sistemas informáticos, Valencia -> entra
    assert casa("BOE-A-2026-20006")        # Informática, Málaga -> entra
    # Exclusiones.
    assert not casa("BOE-A-2026-20005")    # Limpieza -> fuera


def test_nivel_de_confianza():
    anuncios = anuncios_por_ref()
    perfiles = perfiles_normalizados()
    # Con coincidencia geográfica explícita -> alta.
    assert evaluar(anuncios["BOE-A-2026-20006"], perfiles)["nivel"] == "alta"
    # Informática sin ámbito geográfico en el perfil -> media.
    assert evaluar(anuncios["BOE-A-2026-20004"], perfiles)["nivel"] == "media"


def test_boe_no_disponible_por_envoltorio():
    """Fechas sin boletín: la API responde 200 pero con status!=200 o sin
    'sumario'; debe tratarse como no disponible, no como 0 anuncios."""
    c = ConectorBOE()
    with pytest.raises(SumarioNoDisponible):
        c._verificar_disponible({"status": {"code": "404"}, "data": {}}, "20260819")
    with pytest.raises(SumarioNoDisponible):
        c._verificar_disponible({"status": {"code": "200"}, "data": {}}, "20260819")


def test_boe_disponible_ok_no_lanza():
    ConectorBOE()._verificar_disponible(cargar_fixture(), "20260804")  # no lanza


def test_parser_2b_con_envoltorio_texto():
    """En el BOE real la sección 2B mete los epígrafes dentro de un nodo
    'texto' (departamento -> texto -> epigrafe -> item). El parser debe
    recogerlos igualmente, con item único o lista."""
    data = {
        "status": {"code": "200", "text": "ok"},
        "data": {"sumario": {
            "metadatos": {"fecha_publicacion": "20260819"},
            "diario": {  # objeto único, no lista
                "seccion": [
                    {"codigo": "2A", "nombre": "II.A",
                     "departamento": {"nombre": "OTRO",
                                      "item": {"identificador": "BOE-A-2026-0001", "titulo": "nombramiento"}}},
                    {"codigo": "2B", "nombre": "II.B Oposiciones",
                     "departamento": {"codigo": "9525", "nombre": "ADMINISTRACIÓN LOCAL",
                                      "texto": {"epigrafe": [
                                          {"nombre": "Personal funcionario",
                                           "item": {"identificador": "BOE-A-2026-17917", "titulo": "Las Palmas"}},
                                          {"nombre": "Personal funcionario y laboral",
                                           "item": [
                                               {"identificador": "BOE-A-2026-17918", "titulo": "Logrosán"},
                                               {"identificador": "BOE-A-2026-17919", "titulo": "La Mojonera"},
                                           ]},
                                      ]}}},
                ]}}}}
    anuncios = {a.referencia_oficial: a for a in ConectorBOE().parse_sumario(data)}
    assert set(anuncios) == {"BOE-A-2026-17917", "BOE-A-2026-17918", "BOE-A-2026-17919"}
    assert anuncios["BOE-A-2026-17917"].organismo == "ADMINISTRACIÓN LOCAL"
    assert anuncios["BOE-A-2026-17917"].epigrafe == "Personal funcionario"
    assert anuncios["BOE-A-2026-17918"].epigrafe == "Personal funcionario y laboral"
