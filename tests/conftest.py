"""Configuración de pytest.

Fuerza que los tests usen SIEMPRE una base de datos temporal, para que
`pytest` no pueda tocar (ni borrar con drop_all) la BBDD real del usuario.
Se ejecuta antes de importar cualquier módulo de `opotrack`, así que el
engine se crea ya apuntando a la BBDD temporal.
"""

import os
import pathlib
import tempfile

if not os.environ.get("OPOTRACK_DB"):
    _tmp = pathlib.Path(tempfile.gettempdir()) / "opotrack_tests.db"
    os.environ["OPOTRACK_DB"] = str(_tmp)
