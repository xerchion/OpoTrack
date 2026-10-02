"""Capa de acceso a la base de datos (SQLite + SQLAlchemy)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import Base

# Un único engine para toda la aplicación.
engine = create_engine(config.DB_URL, future=True, connect_args={"timeout": 30})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """En cada conexión SQLite: WAL (menos bloqueos, más robusto ante sync) y
    claves foráneas activadas (integridad referencial)."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    # Espera hasta 30 s si la BBDD está bloqueada por otra escritura (el servidor
    # de desarrollo es multihilo) en lugar de fallar al instante con
    # «database is locked».
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def _default_literal(col) -> Optional[str]:
    """Literal SQL del valor por defecto de una columna, si es escalar."""
    d = col.default
    if d is None or not getattr(d, "is_scalar", False):
        return None
    val = d.arg
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return None


def _aplicar_migraciones() -> None:
    """Migración ligera: añade a las tablas ya existentes las columnas nuevas
    del modelo que aún no estén (ALTER TABLE ADD COLUMN). Evita tener que borrar
    la base de datos al ampliar el esquema. No borra ni modifica datos.

    Las tablas totalmente nuevas las crea `create_all`; aquí solo se rellenan
    las columnas que falten en tablas preexistentes.
    """
    insp = inspect(engine)
    tablas = set(insp.get_table_names())
    for tabla in Base.metadata.sorted_tables:
        if tabla.name not in tablas:
            continue
        columnas = {c["name"] for c in insp.get_columns(tabla.name)}
        for col in tabla.columns:
            if col.name in columnas:
                continue
            tipo = col.type.compile(dialect=engine.dialect)
            ddl = f"ALTER TABLE {tabla.name} ADD COLUMN {col.name} {tipo}"
            default = _default_literal(col)
            if default is not None:
                ddl += f" DEFAULT {default}"
                if not col.nullable:
                    ddl += " NOT NULL"
            with engine.begin() as conn:
                conn.execute(text(ddl))


def _migrar_ubicacion_bbdd() -> None:
    """Si la BBDD usa la ubicación por defecto (nueva, fuera de Drive) y no
    existe todavía pero había una antigua en data/opotrack.db, la copia una vez
    para no perder datos al mover la ubicación. Con OPOTRACK_DB fijado no hace
    nada (tests o ruta forzada por el usuario)."""
    import os
    import shutil

    if os.environ.get("OPOTRACK_DB"):
        return
    antigua = config.DATA_DIR / "opotrack.db"
    if (
        antigua.exists()
        and not config.DB_PATH.exists()
        and antigua.resolve() != config.DB_PATH.resolve()
    ):
        shutil.copy2(antigua, config.DB_PATH)


def _reparar_urls_antequera() -> None:
    """Repara URLs relativas de Antequera guardadas antes de resolverlas a
    absolutas: el href real de antequera.es es relativo a la raíz
    (``/ayuntamiento/…``) y, guardado tal cual, el enlace apuntaba a localhost
    (404 de Flask). Antepone el dominio. Idempotente y acotado a esa ruta."""
    insp = inspect(engine)
    tablas = set(insp.get_table_names())
    patron = "/ayuntamiento/tablon-de-anuncios/Empleo-Publico/%"
    site = "https://www.antequera.es"
    with engine.begin() as conn:
        for tabla in ("convocatoria", "candidato", "publicacion", "resultado_busqueda"):
            if tabla not in tablas:
                continue
            if "url" not in {c["name"] for c in insp.get_columns(tabla)}:
                continue
            conn.execute(
                text(f"UPDATE {tabla} SET url = :site || url WHERE url LIKE :patron"),
                {"site": site, "patron": patron},
            )


def init_db() -> None:
    """Crea la base de datos y las tablas que falten, y aplica la migración
    ligera para las columnas nuevas de tablas ya existentes."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _migrar_ubicacion_bbdd()
    Base.metadata.create_all(engine)
    _aplicar_migraciones()
    _reparar_urls_antequera()


@contextmanager
def get_session() -> Iterator[Session]:
    """Sesión con commit/rollback automáticos."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
