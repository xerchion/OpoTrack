# OpoTrack — Pendiente

_Actualizado: 2026-09-21_

## ✅ Hecho (2026-09-21): bug del aviso «sin novedades»

- **Corregido: el aviso diario mandaba «sin novedades» aunque la búsqueda sí
  encontrara candidatos.** El 21/09 la tarea de las 8:00 registró «11 nuevos ·
  145 sin coincidencia» pero envió el mensaje de «hoy nada nuevo». Causa: en
  `cmd_notificar`, la búsqueda y la lectura de la bandeja / no coincidentes se
  hacían en la misma sesión SQLAlchemy (con `autoflush=False`), así que los
  registros recién insertados por `buscar_fuentes_activas` aún no eran visibles
  en los SELECT posteriores. **Fix:** `s.flush()` tras la búsqueda en `cli.py`.
  Añadido test de regresión (`test_cmd_notificar_ve_su_propia_busqueda`).
  101 tests en verde.

## ✅ Hecho (2026-09-20): avisos por Telegram

- **Notificaciones diarias por Telegram** (`python cli.py notificar`): busca en
  todas las fuentes activas, envía las novedades de la bandeja aún no avisadas y
  las marca (columna `fecha_notificacion`, migración automática). Incluye
  `opotrack/notificaciones.py`, `notificar.bat`, `OpoTrack-Notificar.xml` (tarea
  programada con «despertar el equipo») y la guía `NOTIFICACIONES.md`.
  11 tests nuevos (`tests/test_notificaciones.py`).

## ✅ Hecho (revisión: seguridad, datos y robustez)

- **`.env.example` solo con placeholders** (nada de valores reales).
- **`tests/conftest.py`** fuerza una BBDD temporal → `pytest` ya no puede tocar/borrar la real.
- **BBDD fuera de Drive por defecto** (`%LOCALAPPDATA%\OpoTrack\opotrack.db`), con **copia automática** de la antigua `data/opotrack.db` la primera vez (no se pierde nada; la vieja queda ahí y puedes borrarla). Activados **PRAGMA WAL** y **foreign_keys=ON**.
- **Flask endurecido:** `debug=False` en `run_web.py`; `SECRET_KEY` configurable con `OPOTRACK_SECRET`.
- **BOPG:** el CVE se toma del contenedor del anuncio (no por posición) → emparejamiento referencia↔enlace robusto.

_(38 tests en verde.)_

## Pendiente

### Mantenibilidad
1. **Partir `web/__init__.py` (~1.200 líneas) en Blueprints.** Refactor grande: al mover las rutas cambian los nombres de endpoint (`url_for('bandeja')` → `url_for('bp.bandeja')`), lo que obliga a tocar todas las plantillas. Conviene una sesión dedicada para no dejar la web rota a medias.

### Bugs
2. **Filtros de «No coincidentes» intermitentes** (a veces no filtran en sesión nueva). Reproducir y localizar la causa.

### Mejoras
_✅ Hechas (2026-08-13): el botón «Buscar boletines» se activa al elegir una fecha anterior a hoy (y el límite diario solo aplica a hoy); descartar y detectar-puesto en la bandeja funcionan por AJAX, sin recargar ni mostrar el mensaje verde; el aviso «no hay boletín del X» sale más visible en el resumen._

### Aparcado
6. **Enlace al PDF del edicto del BOPMA.**
