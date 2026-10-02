# OpoTrack

Aplicación web **local** para buscar y hacer seguimiento de convocatorias de
oposiciones en boletines oficiales españoles. Cada día recorre el BOE, el BOJA,
los boletines provinciales andaluces y las webs de varios ayuntamientos, filtra
los anuncios con tus perfiles de búsqueda y deja lo que encaja en una bandeja
para que decidas qué seguir.

Está pensada para un solo usuario, en su propio equipo: Python + Flask + SQLite,
sin servicios externos obligatorios.

## Qué hace

- **Búsqueda multi-fuente** por fecha, eligiendo qué boletines y ayuntamientos
  entran, con un resumen por fuente (anuncios leídos, novedades, «sin boletín
  hoy», errores).
- **Perfiles de búsqueda configurables** (reglas temáticas, geográficas y de
  exclusión) editables desde la web, sin tocar código.
- **Bandeja de novedades** con localidad, puesto, grupo y nivel de confianza
  extraídos del anuncio. Cada entrada se puede **seguir**, **asociar** a una
  convocatoria ya seguida o **descartar** (el descarte se recuerda).
- **No coincidentes**: lo que el filtro deja fuera se acumula para repasarlo,
  con filtros por texto, ámbito, boletín, tipo de personal, sistema de acceso y
  nº de plazas.
- **Seguimiento** de cada convocatoria: ficha editable, publicaciones en línea
  temporal, temario con estado de estudio, plazos, requisitos, leyes, enlaces y
  documentos adjuntos (PDF/DOCX).
- **Papelera reversible**, panel con contadores y plazos próximos, y tema
  claro/oscuro.
- **Avisos diarios por Telegram** (opcional) con las novedades del día.

## Fuentes

| Código | Fuente | Cómo se lee |
|--------|--------|-------------|
| `BOE` | Boletín Oficial del Estado | API de datos abiertos (sumario, sección II.B) |
| `BOJA` | Boletín Oficial de la Junta de Andalucía | Feed Atom de la sección de oposiciones |
| `BOPG` | BOP de Granada | HTML del boletín del día |
| `BOPMA` | BOP de Málaga | Sumario diario; respaldo en datos abiertos (CKAN) o CSV local |
| `BOPS` | BOP de Sevilla | HTML del boletín del día |
| `BOPCO` | BOP de Córdoba | HTML del boletín del día |
| `BOPJ` | BOP de Jaén | HTML del boletín del día |
| `AYT…` | Ayuntamientos de Antequera, Benalmádena, Córdoba, Huétor Tájar, Loja, Málaga, Motril y Nerja | HTML de su página de empleo público |

El estado de cada ayuntamiento (y los que no se pueden leer sin navegador) está
en [`municipios.md`](municipios.md). Cada fuente se activa o desactiva desde
**Configuración**.

## Instalación

Requiere **Python 3.10 o superior**.

```
git clone <url-del-repositorio>
cd OpoTrack
pip install -r requirements.txt
python cli.py seed        # crea la base de datos y carga fuentes y perfiles
python run_web.py         # http://127.0.0.1:5000
```

En **Windows** basta con hacer doble clic en `OpoTrack.bat`: instala las
dependencias la primera vez, prepara la base de datos, arranca el servidor y
abre el navegador.

## Configuración

Todo lo configurable por entorno se lee de un archivo `.env` en la raíz del
proyecto. Copia la plantilla y rellena solo lo que vayas a usar:

```
cp .env.example .env      # en Windows: copy .env.example .env
```

| Variable | Para qué |
|----------|----------|
| `OPOTRACK_DB` | Ruta de la base de datos (ver más abajo) |
| `OPOTRACK_SECRET` | Clave de sesión de Flask. Si falta, se genera una aleatoria en cada arranque |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Avisos por Telegram |
| `OPOTRACK_NOTIFICAR_SIN_NOVEDADES`, `OPOTRACK_ENVIAR_NO_COINCIDENTES`, `OPOTRACK_MAX_NO_COINCIDENTES` | Ajustes del aviso diario |

El `.env` está en `.gitignore`: **no subas nunca tus credenciales al repositorio**.

### Base de datos

Por defecto la base de datos se crea **fuera** de la carpeta del proyecto, en la
carpeta de datos del usuario (`%LOCALAPPDATA%\OpoTrack\opotrack.db` en Windows,
`$XDG_DATA_HOME/OpoTrack/opotrack.db` en Linux), y si no existe ninguna de esas
variables, en `data/opotrack.db`. El motivo: SQLite da errores de bloqueo en
carpetas sincronizadas (OneDrive, Google Drive…) o en unidades de red.

Para ponerla en otro sitio:

```
# Windows (PowerShell)
$env:OPOTRACK_DB = "C:\opotrack\opotrack.db"
# Linux / macOS
export OPOTRACK_DB=/ruta/local/opotrack.db
```

El esquema se amplía solo al arrancar (se añaden las columnas y tablas nuevas),
así que no hay que borrar la base de datos al actualizar.

## Uso

### Interfaz web

```
python run_web.py
```

- **Bandeja** (pantalla principal): lanza la búsqueda y revisa las novedades.
- **No coincidentes**: anuncios que no casan con ningún perfil, por si el filtro
  se ha dejado algo.
- **Seguimiento**: listado y ficha de las convocatorias que sigues.
- **Panel**: contadores y plazos próximos.
- **Configuración**: perfiles, fuentes, ajustes y *Modo Pánico* (borra todos los
  descartes para que nada quede oculto de forma permanente).
- **Papelera**: convocatorias eliminadas y novedades descartadas, recuperables.

### Línea de comandos

```
python cli.py init-db                  # crea la base de datos
python cli.py seed                     # carga fuentes, catálogos y perfiles
python cli.py buscar --demo            # BOE sobre el sumario de ejemplo (sin internet)
python cli.py buscar --fecha 20260804  # búsqueda real en el BOE de esa fecha
python cli.py bandeja                  # muestra la bandeja de novedades
python cli.py notificar                # busca en todas las fuentes y avisa por Telegram
```

## Avisos por Telegram

OpoTrack puede enviarte cada día un resumen de las convocatorias nuevas que
encajan con tus perfiles. Se configura con un bot de Telegram y una tarea
programada (plantilla para Windows en `OpoTrack-Notificar.xml`). Guía paso a
paso en [`NOTIFICACIONES.md`](NOTIFICACIONES.md).

```
python cli.py notificar --test    # prueba la conexión
python cli.py notificar           # busca y avisa de las novedades
```

## Perfiles de búsqueda

Un anuncio entra en la bandeja si contiene algún término **temático** del
perfil, cumple el ámbito **geográfico** (si el perfil lo exige) y no contiene
ninguna **exclusión**.

`python cli.py seed` carga tres perfiles **de ejemplo**, definidos en
`opotrack/seed.py`:

- **Granada/Málaga – Administrativo**: términos administrativos, solo en Granada y Málaga.
- **Granada/Málaga – Informática**: términos de informática, en Granada y Málaga.
- **Informática – resto de España**: términos de informática, sin restricción geográfica.

Cámbialos, desactívalos o crea los tuyos desde **Configuración → Perfiles**.

## Tests

```
python -m pytest tests/
```

Los tests no usan la red ni tu base de datos: trabajan sobre las muestras de
`fixtures/` y sobre una base de datos temporal.

## Estructura

```
OpoTrack/
├── cli.py                    # línea de comandos (búsqueda, bandeja, avisos)
├── run_web.py                # lanza la interfaz web
├── OpoTrack.bat              # lanzador para Windows
├── notificar.bat             # aviso diario (lo llama la tarea programada)
├── OpoTrack-Notificar.xml    # plantilla de la tarea programada de Windows
├── opotrack/
│   ├── config.py             # rutas, URLs de las fuentes, límites, entorno
│   ├── db.py                 # motor SQLAlchemy y migración ligera
│   ├── models.py             # modelo de datos
│   ├── motor.py              # búsqueda, filtrado por perfiles y deduplicación
│   ├── extraccion.py         # puesto, nº de plazas, tipo, sistema, localidad…
│   ├── notificaciones.py     # mensajes y envío por Telegram
│   ├── seed.py               # fuentes, catálogos y perfiles iniciales
│   ├── fuentes/              # un conector por boletín o ayuntamiento
│   └── web/                  # rutas Flask, plantillas y estilos
├── fixtures/                 # muestras reales de cada fuente para los tests
├── tests/
├── NOTIFICACIONES.md         # guía de los avisos por Telegram
├── municipios.md             # estado de los ayuntamientos
├── OpoTrack_Especificacion.md  # documento de diseño original
└── TODO.md                   # pendientes
```

### Añadir una fuente

1. Guarda una muestra de la página en `fixtures/`.
2. Crea el conector en `opotrack/fuentes/` implementando `ConectorBase`
   (`base.py`): debe devolver una lista de `AnuncioNormalizado`.
3. Regístralo en `opotrack/fuentes/__init__.py` y añade la fuente a `FUENTES`
   en `opotrack/seed.py`.
4. Añade un test que parsee la muestra.

## A tener en cuenta

- **Es una aplicación local y no tiene login.** El servidor escucha solo en
  `127.0.0.1`. No la expongas a internet tal cual: cualquiera que llegue a ella
  podría ver y modificar tus datos. Si la despliegas en un servidor, ponla
  detrás de una VPN o de autenticación.
- **Uso responsable de las fuentes.** Varias se leen del HTML público de cada
  sitio. Con una búsqueda al día es suficiente; el límite diario de búsquedas se
  ajusta en Configuración. Si una web cambia su estructura, su conector puede
  dejar de funcionar hasta que se adapte.
- OpoTrack **no es un servicio oficial** ni sustituye a la consulta de los
  boletines: es una ayuda para no perderse publicaciones. Comprueba siempre los
  plazos y las bases en la fuente original.

## Licencia

[MIT](LICENSE).
