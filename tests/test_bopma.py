"""Pruebas del conector del BOP de Málaga (parseo de CSV y de registros de la API)."""

from opotrack import config, extraccion
from opotrack.fuentes.bop_malaga import ConectorBOPMA


def _csv():
    with open(config.FIXTURE_BOPMA, encoding="utf-8") as f:
        return f.read()


def test_csv_filtra_por_fecha():
    anuncios = ConectorBOPMA().parse_csv(_csv(), "20251201")   # solo 01/12/2025
    refs = [a.referencia_oficial for a in anuncios]
    assert len(anuncios) == 3
    assert "BOPMA-2025-229-6001" in refs
    assert all(a.fecha_publicacion.isoformat() == "2025-12-01" for a in anuncios)


def test_csv_sin_fecha_devuelve_todo():
    assert len(ConectorBOPMA().parse_csv(_csv())) == 5


def test_extraccion_sobre_edicto_de_oposicion():
    anuncios = {a.referencia_oficial: a for a in ConectorBOPMA().parse_csv(_csv(), "20251201")}
    d = extraccion.extraer(anuncios["BOPMA-2025-229-6001"])
    assert d["puesto"] and "PROGRAMADOR" in d["puesto"].upper()
    assert d["tipo_personal"] == "funcionario"
    assert d["sistema_acceso"] == "oposición"


def test_parse_registros_de_api():
    # Simula la respuesta de la API CKAN (lista de dicts con los mismos campos).
    records = [
        {"edicto": "700", "ejercicio": "2025", "boletin": "230", "procedencia": "Ayuntamiento",
         "municipio": "Málaga", "resumen": "Bases de una plaza de Técnico Auxiliar de Informática, "
                                            "oposición libre", "fecha_publicacion": "02/12/2025"},
    ]
    anuncios = ConectorBOPMA().parse_rows(records, "20251202")
    assert len(anuncios) == 1
    assert anuncios[0].referencia_oficial == "BOPMA-2025-230-700"
    assert "Informática" in anuncios[0].titulo
