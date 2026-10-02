"""Diagnóstico del conector BOE.

Muestra QUÉ devuelve la API de datos abiertos del BOE para una fecha, sección
por sección, para localizar por qué la app saca 0 anuncios.

Uso (desde la carpeta del proyecto, con la app parada):
    python diag_boe.py              # la fecha de hoy
    python diag_boe.py 20250115     # una fecha concreta (AAAAMMDD)

Interpretación rápida:
- Si NO hay 'sumario'  -> ese día no tiene boletín (fin de semana, festivo o
  fecha futura). La app debe decir "no hay boletín", no "0 anuncios".
- Si aparece la sección 2B con items > 0 pero parse_sumario devuelve 0 ->
  entonces sí habría un fallo del parser (adjunta esta salida al reportarlo).
- Si la sección 2B no aparece o tiene 0 items -> ese día no hay oposiciones en
  el BOE (aunque haya muchos anuncios en otras secciones).
"""

import sys
from datetime import date

import requests

from opotrack import config
from opotrack.fuentes.boe import ConectorBOE, _as_list


def main():
    fecha = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y%m%d")
    url = config.BOE_API_SUMARIO.format(fecha=fecha)
    print(f"Fecha consultada: {fecha}")
    print(f"GET {url}")
    print(f"Accept: {config.BOE_ACCEPT}\n")

    try:
        r = requests.get(
            url, headers={"Accept": config.BOE_ACCEPT}, timeout=config.HTTP_TIMEOUT
        )
    except Exception as e:  # noqa: BLE001
        print("ERROR de red al llamar a la API:", repr(e))
        return

    print("HTTP:", r.status_code, "| Content-Type:", r.headers.get("Content-Type"))
    if r.status_code != 200:
        print("Cuerpo (recortado):", r.text[:500])
        print("\n>>> La API no devolvió 200: ese día no hay boletín o la fecha es incorrecta.")
        return

    try:
        data = r.json()
    except ValueError:
        print("La respuesta NO es JSON válido. Primeros 500 caracteres:\n", r.text[:500])
        return

    estado = data.get("status") or {}
    print("status.code:", estado.get("code"), "| status.text:", estado.get("text"))

    sumario = (data.get("data") or {}).get("sumario")
    if not sumario:
        print("\n>>> No viene 'sumario': ese día NO tiene boletín (o fecha futura/festivo).")
        return

    import json as _json

    def contar_items(nodo):
        if not isinstance(nodo, dict):
            return 0
        n = sum(1 for it in _as_list(nodo.get("item")) if isinstance(it, dict))
        for clave in ("texto", "epigrafe", "departamento"):
            for sub in _as_list(nodo.get(clave)):
                n += contar_items(sub)
        return n

    diarios = _as_list(sumario.get("diario"))
    print(f"\ndiarios: {len(diarios)}")
    sec_opo = None
    for d in diarios:
        for sec in _as_list(d.get("seccion")):
            cod = str(sec.get("codigo"))
            n = sum(contar_items(dep) for dep in _as_list(sec.get("departamento")))
            marca = "   <-- OPOSICIONES (lo que busca la app)" if cod == config.SECCION_OPOSICIONES else ""
            print(f"  seccion {cod:<4} {(sec.get('nombre') or '')[:55]:<55} items={n}{marca}")
            if cod == config.SECCION_OPOSICIONES:
                sec_opo = sec

    anuncios = ConectorBOE().parse_sumario(data)
    print("\nparse_sumario() de la app devuelve:", len(anuncios), "anuncios")

    if sec_opo is not None and not anuncios:
        print("\n--- Estructura CRUDA de la seccion de oposiciones (recortada a 5000 car.) ---")
        print("claves de la seccion:", list(sec_opo.keys()))
        print(_json.dumps(sec_opo, ensure_ascii=False, indent=1)[:5000])


if __name__ == "__main__":
    main()
