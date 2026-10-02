#!/usr/bin/env python3
"""Lanza la interfaz web de OpoTrack en local.

Uso:
    python run_web.py
Luego abre http://127.0.0.1:5000 en el navegador.
"""

from opotrack.web import create_app

app = create_app()

if __name__ == "__main__":
    # debug=False: en local no hace falta el depurador de Werkzeug (que además
    # expondría una consola si algo falla). Cámbialo a True solo para depurar.
    app.run(host="127.0.0.1", port=5000, debug=False)
