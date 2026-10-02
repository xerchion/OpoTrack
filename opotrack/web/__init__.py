"""Interfaz web de OpoTrack (Flask).

Cubre el flujo principal: panel, búsqueda con límite, bandeja de novedades
(mostrando localidad, puesto y categoría), aceptar / asociar / descartar,
listado y ficha de seguimiento, y papelera reversible.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from datetime import date, datetime, timedelta

import requests
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy import delete, func, select
from werkzeug.utils import secure_filename

from .. import config, db, extraccion, motor, seed
from ..fuentes import get_conector
from ..fuentes.base import SumarioNoDisponible
from ..fuentes.boe import ConectorBOE
from ..models import (
    Ajuste,
    Candidato,
    Convocatoria,
    Descarte,
    Documento,
    EnlaceInfo,
    EstadoPersonal,
    Fase,
    Fuente,
    Ley,
    LogBusqueda,
    PerfilBusqueda,
    Plazo,
    Publicacion,
    ReglaCriterio,
    ResultadoBusqueda,
    Tema,
    TipoPublicacion,
)
from ..motor import LimiteBusquedasExcedido


def _fetch_demo(fecha):
    with open(config.FIXTURE_SUMARIO, encoding="utf-8") as f:
        return json.load(f)


def _int_or_none(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _fecha_or_none(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _sumar_dias_habiles(inicio, n):
    """Suma n días hábiles (lunes-viernes) a `inicio`. No descuenta festivos,
    solo fines de semana."""
    d = inicio
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _dias_habiles_entre(desde, hasta):
    """Días hábiles (lunes-viernes) desde `desde` (excluido) hasta `hasta`
    (incluido). 0 si el plazo ya venció."""
    if not hasta or hasta <= desde:
        return 0
    n, d = 0, desde
    while d < hasta:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _aplicar_form(c, f):
    """Vuelca los campos del formulario de la ficha en la convocatoria."""
    c.organismo = f.get("organismo") or None
    c.provincia = f.get("provincia") or None
    c.localidad = f.get("localidad") or None
    c.cuerpo_escala = f.get("cuerpo_escala") or None
    c.puesto = f.get("puesto") or None
    c.grupo = f.get("grupo") or None
    c.rama = f.get("rama") or None
    c.tipo_personal = f.get("tipo_personal") or None
    c.sistema_acceso = f.get("sistema_acceso") or None
    c.num_plazas = _int_or_none(f.get("num_plazas"))
    c.notas = f.get("notas") or None
    c.fase_id = _int_or_none(f.get("fase_id"))
    c.estado_personal_id = _int_or_none(f.get("estado_personal_id"))
    c.fecha_base_boe = _fecha_or_none(f.get("fecha_base_boe"))
    _dp = _int_or_none(f.get("dias_habiles_plazo"))
    c.dias_habiles_plazo = _dp if (_dp and _dp > 0) else 20


def get_ajuste(s, clave, default=""):
    a = s.scalar(select(Ajuste).where(Ajuste.clave == clave))
    return a.valor if a and a.valor is not None else default


def set_ajuste(s, clave, valor):
    a = s.scalar(select(Ajuste).where(Ajuste.clave == clave))
    if a:
        a.valor = valor
    else:
        s.add(Ajuste(clave=clave, valor=valor))


def get_ajuste_int(s, clave, default):
    """Lee un ajuste entero de la BBDD; si no existe o no es válido, el defecto."""
    try:
        return int(get_ajuste(s, clave, ""))
    except (TypeError, ValueError):
        return default


def _texto_anuncio(conector, referencia, url) -> str:
    """Descarga el texto de un anuncio para detectar el puesto. Usa
    conector.fetch_texto si existe (BOE: txt.php, texto limpio); si no, descarga
    la página del anuncio (url) de cualquier boletín y la limpia. '' si no hay."""
    if conector is not None and hasattr(conector, "fetch_texto"):
        return conector.fetch_texto(referencia)
    if url:
        resp = requests.get(
            url, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return ConectorBOE._limpiar_texto(resp.text)[:8000]
    return ""


# Último resumen de una búsqueda por streaming: la respuesta SSE no puede
# escribir en la sesión Flask, así que se guarda aquí y la bandeja lo recoge en
# el siguiente render (app local de un solo usuario).
_RESUMEN_STREAM = {"v": None}

# Solo una búsqueda a la vez: evita que dos se solapen (y que la reconexión
# automática de EventSource lance una duplicada) provocando «database is locked».
_BUSQUEDA_LOCK = threading.Lock()


def _resumen_modal(resumen, fu_map, fecha_legible):
    """Construye el dict del modal «Resumen de la búsqueda» a partir del
    resultado del motor (enriquece cada detalle con ámbito y es_ayto)."""
    detalle = resumen.get("detalle")
    if not detalle:
        return None
    for d in detalle:
        cod = d.get("codigo") or ""
        prov, nombre = fu_map.get(cod, (None, cod))
        if cod.startswith("AYT"):
            d["es_ayto"] = True
            d["ambito"] = (nombre or cod).replace("Ayuntamiento de ", "")
        else:
            d["es_ayto"] = False
            d["ambito"] = _ambito_boletin(cod, prov)
    return {
        "fecha": fecha_legible,
        "detalle": detalle,
        "nuevos": resumen["nuevos"],
        "ya_vistos": resumen["ya_vistos"],
        "sin_match": resumen["sin_match"],
        "anuncios": resumen.get("anuncios", 0),
        "segundos_total": resumen.get("segundos"),
    }


def _pop_resumen_modal(sess):
    """Resumen para la bandeja: de la sesión (búsqueda normal) o del streaming."""
    rm = sess.get("ultimo_resumen")
    if rm is None and _RESUMEN_STREAM.get("v") is not None:
        rm = _RESUMEN_STREAM["v"]
        sess["ultimo_resumen"] = rm       # se persiste como en la búsqueda normal
        _RESUMEN_STREAM["v"] = None
    return rm


def _seguimiento_sets(s):
    """Anuncios que YA están en seguimiento (tienen Publicacion). Devuelve dos
    conjuntos: por (fuente_id, referencia) y por (fuente_codigo, referencia),
    para excluirlos de la bandeja, de las descartadas y de los resultados."""
    code_by_id = {f.id: f.codigo for f in s.scalars(select(Fuente)).all()}
    ids, cods = set(), set()
    for p in s.scalars(select(Publicacion)).all():
        if not p.referencia_oficial:
            continue
        ids.add((p.fuente_id, p.referencia_oficial))
        cods.add((code_by_id.get(p.fuente_id), p.referencia_oficial))
    return ids, cods


def _quitar_de_listas(s, fuente_id, fuente_codigo, referencia):
    """Al pasar un anuncio a seguimiento, se limpia de las demás listas: borra su
    descarte, marca su candidato como aceptado y elimina sus filas de resultados,
    para que no reaparezca en la bandeja ni en las descartadas."""
    if not referencia:
        return
    for d in s.scalars(select(Descarte).where(
            Descarte.fuente_id == fuente_id,
            Descarte.referencia_oficial == referencia)).all():
        s.delete(d)
    for c in s.scalars(select(Candidato).where(
            Candidato.fuente_id == fuente_id,
            Candidato.referencia_oficial == referencia)).all():
        c.estado = "aceptado"
    for r in s.scalars(select(ResultadoBusqueda).where(
            ResultadoBusqueda.referencia_oficial == referencia)).all():
        if not fuente_codigo or (r.fuente_codigo or "") == fuente_codigo:
            s.delete(r)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY  # configurable con OPOTRACK_SECRET

    # Asegura que exista la base de datos.
    db.init_db()
    # Incorpora fases nuevas (p. ej. «Información») a BBDD ya creadas.
    with db.get_session() as _s:
        seed.asegurar_fases(_s)
        seed.asegurar_fuentes(_s)

    @app.context_processor
    def _inject_globales():
        with db.get_session() as s:
            pendientes = s.scalar(
                select(func.count()).select_from(Candidato).where(Candidato.estado == "pendiente")
            )
            # Excluir lo que ya está en seguimiento (igual que la vista), para que
            # el número del menú cuadre con lo que se ve al entrar.
            _, seg_cods = _seguimiento_sets(s)
            _sin_match = s.execute(
                select(ResultadoBusqueda.fuente_codigo, ResultadoBusqueda.referencia_oficial)
                .where(ResultadoBusqueda.clasificacion == "sin_match")
            ).all()
            no_coincidentes = sum(
                1 for fc, ref in _sin_match if (fc, ref) not in seg_cods
            )
        return {
            "n_pendientes_global": pendientes or 0,
            "n_no_coincidentes_global": no_coincidentes or 0,
            "hoy": date.today(),
        }

    # ---- Panel ---------------------------------------------------------
    @app.route("/panel")
    def panel():
        hoy = date.today()
        with db.get_session() as s:
            n_conv = s.scalar(
                select(func.count()).select_from(Convocatoria).where(
                    Convocatoria.estado_registro == "activa"
                )
            )
            n_papelera = s.scalar(
                select(func.count()).select_from(Convocatoria).where(
                    Convocatoria.estado_registro == "en_papelera"
                )
            )
            plazos = s.scalars(
                select(Plazo)
                .where(Plazo.fecha_fin.is_not(None), Plazo.fecha_fin >= hoy)
                .order_by(Plazo.fecha_fin)
                .limit(10)
            ).all()
            plazos_data = [
                {
                    "convocatoria_id": p.convocatoria_id,
                    "convocatoria": p.convocatoria.puesto or p.convocatoria.organismo or "Convocatoria",
                    "tipo": p.tipo_plazo,
                    "fecha_fin": p.fecha_fin,
                    "dias": (p.fecha_fin - hoy).days,
                }
                for p in plazos
            ]
            return render_template(
                "panel.html", n_conv=n_conv or 0, n_papelera=n_papelera or 0, plazos=plazos_data
            )

    # ---- Búsqueda ------------------------------------------------------
    @app.route("/buscar", methods=["POST"])
    def buscar():
        modo = request.form.get("modo", "real")
        # Fecha elegida (input date, formato YYYY-MM-DD); por defecto hoy.
        hoy = date.today()
        raw = (request.form.get("fecha") or "").strip()
        try:
            dia = date.fromisoformat(raw) if raw else hoy
        except ValueError:
            dia = hoy
        if dia > hoy:
            flash("No se puede buscar en una fecha futura; se usa la de hoy.", "aviso")
            dia = hoy
        fecha = dia.strftime("%Y%m%d")
        fecha_legible = dia.strftime("%d/%m/%Y")
        # Boletines marcados (checkboxes); si no se marca ninguno, se usan todos los activos.
        codigos = request.form.getlist("fuentes") or None
        # El BOJA solo permite consultar el ÚLTIMO boletín (su feed no admite fechas
        # pasadas), así que en búsquedas por una fecha anterior a hoy se omite.
        excluir = None
        if dia != hoy:
            excluir = ["BOJA"]
            if codigos is None or "BOJA" in codigos:
                flash(
                    "El BOJA solo permite consultar el último boletín; se ha omitido "
                    "en la búsqueda por una fecha pasada.",
                    "aviso",
                )
        try:
            with db.get_session() as s:
                if modo == "demo":
                    resumen = motor.buscar(
                        s, ConectorBOE(), fecha, fetch_fn=_fetch_demo, ignorar_limite=True
                    )
                else:
                    resumen = motor.buscar_fuentes_activas(
                        s, fecha, ignorar_limite=(dia != hoy), codigos=codigos, excluir=excluir,
                        limite=get_ajuste_int(s, "max_busquedas_dia", config.MAX_BUSQUEDAS_DIA),
                    )
                _fu = {f.codigo: (f.provincia, f.nombre) for f in s.scalars(select(Fuente)).all()}
            detalle = resumen.get("detalle")
            if detalle:
                for d in detalle:
                    cod = d.get("codigo") or ""
                    prov, nombre = _fu.get(cod, (None, cod))
                    if cod.startswith("AYT"):
                        d["es_ayto"] = True
                        d["ambito"] = (nombre or cod).replace("Ayuntamiento de ", "")
                    else:
                        d["es_ayto"] = False
                        d["ambito"] = _ambito_boletin(cod, prov)
                # Guardar el resumen estructurado para el modal "Resumen de la búsqueda".
                session["ultimo_resumen"] = {
                    "fecha": fecha_legible,
                    "detalle": detalle,
                    "nuevos": resumen["nuevos"],
                    "ya_vistos": resumen["ya_vistos"],
                    "sin_match": resumen["sin_match"],
                    "anuncios": resumen.get("anuncios", 0),
                }
                flash("Búsqueda finalizada con éxito.", "ok")
                for d in detalle:
                    if d["estado"] == "error":
                        flash(f"{d['codigo']}: no se pudo consultar ({d.get('error', '')}).", "aviso")
            else:
                flash("Búsqueda finalizada con éxito.", "ok")
        except LimiteBusquedasExcedido as e:
            flash(str(e), "error")
        except Exception as e:  # noqa: BLE001 (en local, mostrar el error es útil)
            flash(f"No se pudo completar la búsqueda: {e}", "error")
        return redirect(url_for("bandeja"))

    @app.route("/buscar/stream")
    def buscar_stream():
        """Igual que /buscar pero emite el progreso por SSE (para el overlay con
        círculo de progreso). Cada evento indica el sitio en proceso y el %."""
        modo = request.args.get("modo", "real")
        hoy = date.today()
        raw = (request.args.get("fecha") or "").strip()
        try:
            dia = date.fromisoformat(raw) if raw else hoy
        except ValueError:
            dia = hoy
        if dia > hoy:
            dia = hoy
        fecha = dia.strftime("%Y%m%d")
        fecha_legible = dia.strftime("%d/%m/%Y")
        codigos = request.args.getlist("fuentes") or None
        excluir = ["BOJA"] if dia != hoy else None

        if not _BUSQUEDA_LOCK.acquire(blocking=False):
            def _ocupada():
                yield "data: " + json.dumps(
                    {"tipo": "fin", "error": "Ya hay una búsqueda en curso. Espera a que termine.",
                     "resumen": False, "stats": None}, ensure_ascii=False) + "\n\n"
            return Response(_ocupada(), mimetype="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        q: queue.Queue = queue.Queue()
        holder: dict = {}

        def run():
            try:
                with db.get_session() as s:
                    lim = get_ajuste_int(s, "max_busquedas_dia", config.MAX_BUSQUEDAS_DIA)

                    def prog(i, total, cod, nom):
                        q.put({
                            "tipo": "prog", "i": i, "total": total,
                            "actual": (nom or cod),
                            "pct": int(round((i - 1) * 100 / total)) if total else 0,
                        })

                    if modo == "demo":
                        resumen = motor.buscar(s, ConectorBOE(), fecha, fetch_fn=_fetch_demo, ignorar_limite=True)
                    else:
                        resumen = motor.buscar_fuentes_activas(
                            s, fecha, ignorar_limite=(dia != hoy), codigos=codigos,
                            excluir=excluir, limite=lim, on_progress=prog,
                        )
                    fu_map = {f.codigo: (f.provincia, f.nombre) for f in s.scalars(select(Fuente)).all()}
                    holder["resumen_modal"] = _resumen_modal(resumen, fu_map, fecha_legible)
            except LimiteBusquedasExcedido as e:
                holder["error"] = str(e)
            except Exception as e:  # noqa: BLE001
                holder["error"] = "No se pudo completar la búsqueda: " + str(e)
            finally:
                q.put(None)
                _BUSQUEDA_LOCK.release()

        threading.Thread(target=run, daemon=True).start()

        def gen():
            yield "retry: 10000\n\n"
            while True:
                item = q.get()
                if item is None:
                    break
                yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            rm = holder.get("resumen_modal")
            if rm is not None:
                _RESUMEN_STREAM["v"] = rm
            yield "data: " + json.dumps(
                {"tipo": "fin", "error": holder.get("error"), "resumen": rm is not None, "stats": rm},
                ensure_ascii=False,
            ) + "\n\n"

        return Response(
            gen(), mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---- Bandeja de novedades (pantalla principal) --------------------
    @app.route("/")
    @app.route("/bandeja")
    def bandeja():
        hoy = date.today()
        with db.get_session() as s:
            seg_ids, _ = _seguimiento_sets(s)  # anuncios ya en seguimiento: se excluyen
            candidatos = s.scalars(
                select(Candidato)
                .where(Candidato.estado == "pendiente")
                .order_by(Candidato.score.desc(), Candidato.fecha_entrada_bandeja.asc())
            ).all()
            filas = [
                {
                    "id": c.id,
                    "referencia": c.referencia_oficial,
                    "fuente": c.fuente.codigo if c.fuente else "",
                    "titulo": c.titulo,
                    "organismo": c.organismo,
                    "localidad": c.localidad,
                    "puesto": c.puesto,
                    "categoria": c.categoria,
                    "perfil": c.perfil_coincidente,
                    "nivel": c.nivel_confianza,
                    "url": c.url,
                    "entrada": c.fecha_entrada_bandeja.date() if c.fecha_entrada_bandeja else None,
                    "atrasada": bool(c.fecha_entrada_bandeja and c.fecha_entrada_bandeja.date() < hoy),
                }
                for c in candidatos
                if (c.fuente_id, c.referencia_oficial) not in seg_ids
            ]
            boletines = sorted({f["fuente"] for f in filas if f["fuente"]})
            niveles = sorted({f["nivel"] for f in filas if f["nivel"]})
            # Fuentes activas con conector, para las casillas del buscador.
            _fuentes_act = [
                {"codigo": fu.codigo, "nombre": fu.nombre, "provincia": fu.provincia}
                for fu in s.scalars(
                    select(Fuente).where(Fuente.activa.is_(True)).order_by(Fuente.id)
                ).all()
                if get_conector(fu.codigo) is not None
            ]
            # Los ayuntamientos (código AYT*) tienen su propia sección en el buscador.
            fuentes_busqueda = [f for f in _fuentes_act if not f["codigo"].startswith("AYT")]
            ayuntamientos_busqueda = [f for f in _fuentes_act if f["codigo"].startswith("AYT")]
            convocatorias = s.scalars(
                select(Convocatoria).where(Convocatoria.estado_registro == "activa")
                .order_by(Convocatoria.fecha_alta.desc())
            ).all()
            convs = [{"id": c.id, "nombre": _nombre_conv(c)} for c in convocatorias]
            log = s.scalar(
                select(LogBusqueda)
                .where(LogBusqueda.resultado == "ok")
                .order_by(LogBusqueda.momento.desc())
                .limit(1)
            )
            resumen = None
            if log:
                resumen = {
                    "momento": log.momento,
                    "nuevas": log.num_candidatos,
                    "ya_vistos": log.num_ya_vistos,
                    "sin_match": log.num_sin_match,
                }
            _max_bus = get_ajuste_int(s, "max_busquedas_dia", config.MAX_BUSQUEDAS_DIA)
            busqueda_bloqueada = _max_bus > 0 and motor.busquedas_hoy(s) >= _max_bus
            return render_template(
                "bandeja.html",
                filas=filas,
                convocatorias=convs,
                resumen=resumen,
                boletines=boletines,
                niveles=niveles,
                fuentes_busqueda=fuentes_busqueda,
                ayuntamientos_busqueda=ayuntamientos_busqueda,
                hoy_iso=hoy.isoformat(),
                busqueda_bloqueada=busqueda_bloqueada,
                resumen_modal=_pop_resumen_modal(session),
            )

    # ---- Acciones sobre un candidato ----------------------------------
    @app.route("/candidato/<int:cid>/aceptar", methods=["POST"])
    def aceptar(cid):
        with db.get_session() as s:
            c = s.get(Candidato, cid)
            if not c or c.estado != "pendiente":
                abort(404)
            fase = s.scalar(select(Fase).where(Fase.codigo == "convocada"))
            tipo = s.scalar(select(TipoPublicacion).where(TipoPublicacion.codigo == "bases"))
            d = extraccion.extraer(c)
            conv = Convocatoria(
                organismo=c.organismo,
                localidad=c.localidad,
                provincia=c.localidad,
                puesto=c.puesto,
                grupo=c.categoria,
                num_plazas=d["num_plazas"],
                tipo_personal=d["tipo_personal"],
                sistema_acceso=d["sistema_acceso"],
                fase=fase,
                estado_registro="activa",
                fecha_base_boe=c.fecha_publicacion,
            )
            pub = Publicacion(
                convocatoria=conv,
                fuente_id=c.fuente_id,
                referencia_oficial=c.referencia_oficial,
                tipo_publicacion=tipo,
                fecha_publicacion=c.fecha_publicacion,
                titulo=c.titulo,
                url=c.url,
            )
            s.add(conv)
            s.add(pub)
            c.estado = "aceptado"
            _quitar_de_listas(s, c.fuente_id, c.fuente.codigo if c.fuente else None, c.referencia_oficial)
            s.flush()
            nuevo_id = conv.id
        flash("Convocatoria añadida al seguimiento.", "ok")
        return redirect(url_for("ficha", cid=nuevo_id))

    @app.route("/candidato/<int:cid>/detectar-puesto", methods=["POST"])
    def detectar_puesto(cid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        with db.get_session() as s:
            c = s.get(Candidato, cid)
            if not c or c.estado != "pendiente":
                abort(404)
            conector = get_conector(c.fuente.codigo if c.fuente else "")
            try:
                texto = _texto_anuncio(conector, c.referencia_oficial, c.url)
            except Exception as e:  # noqa: BLE001
                flash(f"No se pudo leer el texto del anuncio: {e}", "error")
                return redirect(url_for("bandeja"))
            if not texto:
                flash("No hay texto disponible para este anuncio.", "aviso")
                return redirect(url_for("bandeja"))
            puesto = extraccion.puesto_desde_texto(texto)
            if puesto:
                c.puesto = puesto
            if ajax:
                return jsonify(ok=True, puesto=(puesto or ""))
            if puesto:
                flash(f"Puesto detectado: {puesto}.", "ok")
            else:
                flash("No se detectó el puesto en el cuerpo del anuncio.", "aviso")
        return redirect(url_for("bandeja"))

    @app.route("/candidato/<int:cid>/asociar", methods=["GET", "POST"])
    def asociar(cid):
        with db.get_session() as s:
            c = s.get(Candidato, cid)
            if not c or c.estado != "pendiente":
                abort(404)
            if request.method == "POST":
                conv_id = _int_or_none(request.form.get("convocatoria_id"))
                conv = s.get(Convocatoria, conv_id) if conv_id else None
                if not conv:
                    flash("Selecciona una convocatoria válida.", "error")
                    return redirect(url_for("asociar", cid=cid))
                tipo_cod = request.form.get("tipo_publicacion") or "otros"
                tipo = s.scalar(select(TipoPublicacion).where(TipoPublicacion.codigo == tipo_cod))
                s.add(
                    Publicacion(
                        convocatoria=conv,
                        fuente_id=c.fuente_id,
                        referencia_oficial=c.referencia_oficial,
                        tipo_publicacion=tipo,
                        fecha_publicacion=c.fecha_publicacion,
                        titulo=c.titulo,
                        url=c.url,
                    )
                )
                c.estado = "aceptado"
                _quitar_de_listas(s, c.fuente_id, c.fuente.codigo if c.fuente else None, c.referencia_oficial)
                conv_id_final = conv.id
                flash("Publicación asociada a la convocatoria.", "ok")
                s.flush()
                return redirect(url_for("ficha", cid=conv_id_final))

            # GET
            candidato = {
                "id": c.id, "titulo": c.titulo, "localidad": c.localidad,
                "puesto": c.puesto, "categoria": c.categoria,
            }
            convocatorias = s.scalars(
                select(Convocatoria).where(Convocatoria.estado_registro == "activa")
                .order_by(Convocatoria.fecha_alta.desc())
            ).all()
            convs = [{"id": cv.id, "nombre": _nombre_conv(cv)} for cv in convocatorias]
            tipos = _tipos_publicacion(s)
            return render_template("asociar.html", candidato=candidato, convocatorias=convs, tipos=tipos)

    @app.route("/candidato/<int:cid>/descartar", methods=["POST"])
    def descartar(cid):
        with db.get_session() as s:
            c = s.get(Candidato, cid)
            if not c or c.estado != "pendiente":
                abort(404)
            existe = s.scalar(
                select(Descarte.id).where(
                    Descarte.fuente_id == c.fuente_id,
                    Descarte.referencia_oficial == c.referencia_oficial,
                )
            )
            if not existe:
                s.add(
                    Descarte(
                        fuente_id=c.fuente_id,
                        referencia_oficial=c.referencia_oficial,
                        motivo=request.form.get("motivo"),
                    )
                )
            c.estado = "descartado"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=True)
        flash("Novedad descartada. No volverá a aparecer.", "ok")
        return redirect(url_for("bandeja"))

    # ---- Seguimiento: listado -----------------------------------------
    @app.route("/convocatorias")
    def convocatorias():
        with db.get_session() as s:
            items = s.scalars(
                select(Convocatoria)
                .where(Convocatoria.estado_registro == "activa")
                .order_by(Convocatoria.fecha_alta.desc())
            ).all()
            filas = []
            for c in items:
                bols = sorted({p.fuente.codigo for p in c.publicaciones if p.fuente})
                _tope = _sumar_dias_habiles(c.fecha_base_boe, c.dias_habiles_plazo or 20) if c.fecha_base_boe else None
                _en_plazo = bool(_tope and c.fecha_base_boe <= date.today() <= _tope)
                filas.append(
                    {
                        "id": c.id,
                        "nombre": _nombre_conv(c),
                        "localidad": c.localidad,
                        "grupo": c.grupo,
                        "fase": c.fase.nombre if c.fase else None,
                        "estado_personal": c.estado_personal.nombre if c.estado_personal else None,
                        "n_pub": len(c.publicaciones),
                        "boletines": bols,
                        "favorito": c.favorito,
                        "estado_orden": c.estado_personal_id or 9999,
                        "en_plazo": _en_plazo,
                        "dias_rest": _dias_habiles_entre(date.today(), _tope) if _en_plazo else None,
                    }
                )
            # Favoritos primero; dentro, orden por estado personal y nombre.
            filas.sort(key=lambda f: (not f["favorito"], f["estado_orden"], (f["nombre"] or "").lower()))
            grupos = sorted({f["grupo"] for f in filas if f["grupo"]})
            fases = sorted({f["fase"] for f in filas if f["fase"]})
            estados = sorted({f["estado_personal"] for f in filas if f["estado_personal"]})
            boletines = sorted({b for f in filas for b in f["boletines"]})
            return render_template(
                "convocatorias.html",
                filas=filas,
                grupos=grupos,
                fases=fases,
                estados=estados,
                boletines=boletines,
            )

    @app.route("/convocatoria/<int:cid>/favorito", methods=["POST"])
    def favorito_toggle(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            c.favorito = not c.favorito
            fav = c.favorito
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=True, favorito=fav)
        return redirect(request.referrer or url_for("convocatorias"))

    # ---- Seguimiento: alta manual -------------------------------------
    @app.route("/convocatoria/nueva", methods=["GET", "POST"])
    def convocatoria_nueva():
        with db.get_session() as s:
            if request.method == "POST":
                f = request.form
                conv = Convocatoria(
                    organismo=f.get("organismo") or None,
                    provincia=f.get("provincia") or None,
                    localidad=f.get("localidad") or None,
                    cuerpo_escala=f.get("cuerpo_escala") or None,
                    puesto=f.get("puesto") or None,
                    grupo=f.get("grupo") or None,
                    rama=f.get("rama") or None,
                    tipo_personal=f.get("tipo_personal") or None,
                    sistema_acceso=f.get("sistema_acceso") or None,
                    num_plazas=_int_or_none(f.get("num_plazas")),
                    notas=f.get("notas") or None,
                    fase_id=_int_or_none(f.get("fase_id")),
                    estado_personal_id=_int_or_none(f.get("estado_personal_id")),
                    fecha_base_boe=_fecha_or_none(f.get("fecha_base_boe")),
                    estado_registro="activa",
                )
                s.add(conv)
                s.flush()
                nuevo_id = conv.id
                flash("Convocatoria creada manualmente.", "ok")
                return redirect(url_for("ficha", cid=nuevo_id))
            fases = s.scalars(select(Fase).order_by(Fase.orden)).all()
            estados = s.scalars(select(EstadoPersonal).order_by(EstadoPersonal.id)).all()
            return render_template("convocatoria_nueva.html", fases=fases, estados=estados)

    # ---- Seguimiento: ficha -------------------------------------------
    @app.route("/convocatoria/<int:cid>")
    def ficha(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            datos = _ficha_data(s, c)
            return render_template("ficha.html", **datos)

    @app.route("/convocatoria/<int:cid>/editar", methods=["POST"])
    def editar(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            _aplicar_form(c, request.form)
        flash("Datos actualizados.", "ok")
        return redirect(url_for("ficha", cid=cid))

    @app.route("/convocatoria/<int:cid>/tema", methods=["POST"])
    def add_tema(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            titulo = request.form.get("titulo")
            if titulo:
                s.add(
                    Tema(
                        convocatoria_id=cid,
                        bloque=request.form.get("bloque") or None,
                        numero=_int_or_none(request.form.get("numero")),
                        titulo=titulo,
                    )
                )
                flash("Tema añadido.", "ok")
        return redirect(url_for("ficha", cid=cid))

    @app.route("/convocatoria/<int:cid>/plazo", methods=["POST"])
    def add_plazo(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            s.add(
                Plazo(
                    convocatoria_id=cid,
                    tipo_plazo=request.form.get("tipo_plazo") or None,
                    fecha_inicio=_fecha_or_none(request.form.get("fecha_inicio")),
                    fecha_fin=_fecha_or_none(request.form.get("fecha_fin")),
                )
            )
            flash("Plazo añadido.", "ok")
        return redirect(url_for("ficha", cid=cid))

    @app.route("/convocatoria/<int:cid>/plazo-tope", methods=["POST"])
    def plazo_desde_tope(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            _aplicar_form(c, request.form)  # guarda lo que haya en el formulario
            if not c.fecha_base_boe:
                flash("Rellena la fecha base del BOE para calcular el plazo.", "aviso")
                return redirect(url_for("ficha", cid=cid))
            fin = _sumar_dias_habiles(c.fecha_base_boe, c.dias_habiles_plazo or 20)
            s.add(
                Plazo(
                    convocatoria_id=c.id,
                    tipo_plazo="Plazo abierto",
                    fecha_inicio=c.fecha_base_boe,
                    fecha_fin=fin,
                )
            )
            flash("Plazo abierto añadido a Plazos.", "ok")
        return redirect(url_for("ficha", cid=cid))

    @app.route("/plazo/<int:pid>/editar", methods=["POST"])
    def editar_plazo(pid):
        with db.get_session() as s:
            p = s.get(Plazo, pid)
            if not p:
                abort(404)
            cid = p.convocatoria_id
            f = request.form
            p.tipo_plazo = f.get("tipo_plazo") or None
            p.fecha_inicio = _fecha_or_none(f.get("fecha_inicio"))
            p.fecha_fin = _fecha_or_none(f.get("fecha_fin"))
        flash("Plazo actualizado.", "ok")
        return redirect(url_for("ficha", cid=cid) + "#plazos")

    @app.route("/plazo/<int:pid>/eliminar", methods=["POST"])
    def eliminar_plazo(pid):
        with db.get_session() as s:
            p = s.get(Plazo, pid)
            if not p:
                abort(404)
            cid = p.convocatoria_id
            s.delete(p)
        flash("Plazo eliminado.", "ok")
        return redirect(url_for("ficha", cid=cid) + "#plazos")

    @app.route("/convocatoria/<int:cid>/documento/<categoria>", methods=["POST"])
    def subir_documento(cid, categoria):
        if categoria not in ("temario", "requisitos"):
            abort(404)
        destino = url_for("ficha", cid=cid) + "#" + categoria
        f = request.files.get("archivo")
        if not f or not f.filename:
            flash("Selecciona un archivo.", "aviso")
            return redirect(destino)
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in config.EXTENSIONES_DOCUMENTO:
            flash("Solo se permiten archivos PDF o DOCX.", "aviso")
            return redirect(destino)
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            carpeta = config.ARCHIVOS_DIR / str(cid)
            carpeta.mkdir(parents=True, exist_ok=True)
            nombre_disco = f"{uuid.uuid4().hex}{ext}"
            f.save(carpeta / nombre_disco)
            s.add(Documento(
                convocatoria_id=cid,
                categoria=categoria,
                archivo=nombre_disco,
                nombre=secure_filename(f.filename) or ("documento" + ext),
            ))
        flash("Archivo añadido.", "ok")
        return redirect(destino)

    @app.route("/documento/<int:did>")
    def descargar_documento(did):
        with db.get_session() as s:
            d = s.get(Documento, did)
            if not d:
                abort(404)
            ruta = config.ARCHIVOS_DIR / str(d.convocatoria_id) / d.archivo
            nombre = d.nombre
        if not ruta.exists():
            abort(404)
        return send_file(ruta, as_attachment=True, download_name=nombre)

    @app.route("/documento/<int:did>/eliminar", methods=["POST"])
    def eliminar_documento(did):
        with db.get_session() as s:
            d = s.get(Documento, did)
            if not d:
                abort(404)
            cid, categoria = d.convocatoria_id, d.categoria
            ruta = config.ARCHIVOS_DIR / str(cid) / d.archivo
            s.delete(d)
        try:
            if ruta.exists():
                ruta.unlink()
        except OSError:
            pass
        flash("Archivo eliminado.", "ok")
        return redirect(url_for("ficha", cid=cid) + "#" + categoria)

    @app.route("/convocatoria/<int:cid>/enlace", methods=["POST"])
    def enlace_add(cid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        url = (request.form.get("url") or "").strip()
        titulo = (request.form.get("titulo") or "").strip() or None
        if url and not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        datos = None
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            if url:
                e = EnlaceInfo(convocatoria_id=cid, url=url[:500], titulo=titulo)
                s.add(e)
                s.flush()
                datos = {"id": e.id, "url": e.url, "titulo": e.titulo}
        if ajax:
            return jsonify(ok=bool(datos), **(datos or {}))
        flash("Enlace añadido." if datos else "Indica una URL.", "ok" if datos else "aviso")
        return redirect(url_for("ficha", cid=cid) + "#datos")

    @app.route("/enlace/<int:eid>/eliminar", methods=["POST"])
    def enlace_eliminar(eid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        with db.get_session() as s:
            e = s.get(EnlaceInfo, eid)
            if not e:
                abort(404)
            cid = e.convocatoria_id
            s.delete(e)
        if ajax:
            return jsonify(ok=True)
        return redirect(url_for("ficha", cid=cid) + "#datos")

    @app.route("/enlace/<int:eid>/editar", methods=["POST"])
    def editar_enlace(eid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        url = (request.form.get("url") or "").strip()
        titulo = (request.form.get("titulo") or "").strip() or None
        if url and not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        with db.get_session() as s:
            e = s.get(EnlaceInfo, eid)
            if not e:
                abort(404)
            cid = e.convocatoria_id
            if url:
                e.url = url[:500]
            e.titulo = titulo
            datos = {"url": e.url, "titulo": e.titulo}
        if ajax:
            return jsonify(ok=True, **datos)
        return redirect(url_for("ficha", cid=cid) + "#datos")

    @app.route("/convocatoria/<int:cid>/publicacion", methods=["POST"])
    def add_publicacion(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            boe = s.scalar(select(func.min(Publicacion.fuente_id)).where(Publicacion.convocatoria_id == cid))
            tipo_cod = request.form.get("tipo_publicacion") or "otros"
            tipo = s.scalar(select(TipoPublicacion).where(TipoPublicacion.codigo == tipo_cod))
            s.add(
                Publicacion(
                    convocatoria_id=cid,
                    fuente_id=boe or 1,
                    referencia_oficial=request.form.get("referencia_oficial") or "(manual)",
                    tipo_publicacion=tipo,
                    fecha_publicacion=_fecha_or_none(request.form.get("fecha_publicacion")),
                    titulo=request.form.get("titulo") or None,
                    url=request.form.get("url") or None,
                    notas=request.form.get("notas") or None,
                )
            )
            flash("Publicación añadida.", "ok")
        return redirect(url_for("ficha", cid=cid))

    @app.route("/publicacion/<int:pid>/desasociar", methods=["POST"])
    def desasociar_publicacion(pid):
        with db.get_session() as s:
            p = s.get(Publicacion, pid)
            if not p:
                abort(404)
            cid = p.convocatoria_id
            s.delete(p)   # quita la asociación (borra el vínculo con la convocatoria)
        flash("Publicación desasociada de la convocatoria.", "ok")
        return redirect(url_for("ficha", cid=cid))

    @app.route("/publicacion/<int:pid>/editar", methods=["POST"])
    def editar_publicacion(pid):
        with db.get_session() as s:
            p = s.get(Publicacion, pid)
            if not p:
                abort(404)
            cid = p.convocatoria_id
            f = request.form
            tipo_cod = f.get("tipo_publicacion") or "otros"
            p.tipo_publicacion = s.scalar(
                select(TipoPublicacion).where(TipoPublicacion.codigo == tipo_cod)
            )
            p.referencia_oficial = f.get("referencia_oficial") or p.referencia_oficial
            p.fecha_publicacion = _fecha_or_none(f.get("fecha_publicacion"))
            p.titulo = f.get("titulo") or None
            p.url = f.get("url") or None
            p.notas = f.get("notas") or None
        flash("Publicación actualizada.", "ok")
        return redirect(url_for("ficha", cid=cid) + "#publicaciones")

    @app.route("/convocatoria/<int:cid>/ley", methods=["POST"])
    def add_ley(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            denominacion = request.form.get("denominacion")
            if denominacion:
                ley = Ley(
                    denominacion=denominacion,
                    identificador_boe=request.form.get("identificador_boe") or None,
                    url_consolidada=request.form.get("url_consolidada") or None,
                )
                c.leyes.append(ley)
                tema_id = _int_or_none(request.form.get("tema_id"))
                if tema_id:
                    tema = s.get(Tema, tema_id)
                    if tema:
                        tema.leyes.append(ley)
                s.add(ley)
                flash("Ley añadida y enlazada.", "ok")
        return redirect(url_for("ficha", cid=cid))

    # ---- Papelera ------------------------------------------------------
    @app.route("/convocatoria/<int:cid>/eliminar", methods=["POST"])
    def eliminar(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            c.estado_registro = "en_papelera"
            c.fecha_eliminacion = date.today()
            c.motivo_eliminacion = request.form.get("motivo") or None
        flash("Convocatoria movida a la papelera.", "ok")
        return redirect(url_for("convocatorias"))

    @app.route("/papelera")
    def papelera():
        with db.get_session() as s:
            items = s.scalars(
                select(Convocatoria)
                .where(Convocatoria.estado_registro == "en_papelera")
                .order_by(Convocatoria.fecha_eliminacion.desc())
            ).all()
            filas = [
                {
                    "id": c.id,
                    "nombre": _nombre_conv(c),
                    "eliminada": c.fecha_eliminacion,
                    "motivo": c.motivo_eliminacion,
                }
                for c in items
            ]
            fecha_por_ref = {
                (d.fuente_id, d.referencia_oficial): d.fecha_descarte
                for d in s.scalars(select(Descarte)).all()
            }
            seg_ids, _ = _seguimiento_sets(s)  # lo que ya se sigue no es «descartada»
            descartados = [
                {
                    "id": c.id,
                    "referencia": c.referencia_oficial,
                    "puesto": c.puesto,
                    "localidad": c.localidad,
                    "categoria": c.categoria,
                    "url": c.url,
                    "fecha": fecha_por_ref.get((c.fuente_id, c.referencia_oficial)),
                }
                for c in s.scalars(
                    select(Candidato)
                    .where(Candidato.estado == "descartado")
                    .order_by(Candidato.id.desc())
                ).all()
                if (c.fuente_id, c.referencia_oficial) not in seg_ids
            ]
            return render_template("papelera.html", filas=filas, descartados=descartados)

    @app.route("/convocatoria/<int:cid>/restaurar", methods=["POST"])
    def restaurar(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            c.estado_registro = "activa"
            c.fecha_eliminacion = None
            c.motivo_eliminacion = None
        flash("Convocatoria restaurada.", "ok")
        return redirect(url_for("convocatorias"))

    @app.route("/convocatoria/<int:cid>/borrar", methods=["POST"])
    def borrar(cid):
        with db.get_session() as s:
            c = s.get(Convocatoria, cid)
            if not c:
                abort(404)
            s.delete(c)
        flash("Convocatoria borrada definitivamente.", "ok")
        return redirect(url_for("papelera"))

    @app.route("/candidato/<int:cid>/recuperar", methods=["POST"])
    def recuperar_descarte(cid):
        with db.get_session() as s:
            c = s.get(Candidato, cid)
            if not c or c.estado != "descartado":
                abort(404)
            c.estado = "pendiente"
            d = s.scalar(
                select(Descarte).where(
                    Descarte.fuente_id == c.fuente_id,
                    Descarte.referencia_oficial == c.referencia_oficial,
                )
            )
            if d:
                s.delete(d)
        flash("Novedad devuelta a la bandeja.", "ok")
        return redirect(url_for("papelera"))

    @app.route("/candidato/<int:cid>/borrar-descarte", methods=["POST"])
    def borrar_descarte(cid):
        with db.get_session() as s:
            c = s.get(Candidato, cid)
            if not c or c.estado != "descartado":
                abort(404)
            # Se elimina la entrada visible de la papelera, pero se conserva el
            # registro en Descarte (memoria) para que la novedad no reaparezca.
            s.delete(c)
        flash("Novedad eliminada definitivamente de la papelera.", "ok")
        return redirect(url_for("papelera"))

    @app.route("/descartadas/vaciar", methods=["POST"])
    def vaciar_descartadas():
        with db.get_session() as s:
            n = s.scalar(
                select(func.count()).select_from(Candidato).where(Candidato.estado == "descartado")
            ) or 0
            # Se vacía la LISTA visible; se conserva la memoria de descartes (tabla
            # Descarte) para que esas novedades no reaparezcan en las búsquedas.
            s.execute(delete(Candidato).where(Candidato.estado == "descartado"))
        flash(
            f"Vaciadas {n} novedades descartadas." if n else "No había novedades descartadas.",
            "ok",
        )
        return redirect(url_for("papelera"))

    # ---- Resultados de la última búsqueda -----------------------------
    @app.route("/resultados/<clase>")
    def resultados(clase):
        mapa = {
            "ya-conocidas": (
                "ya_conocido",
                "Novedades ya conocidas",
                "Anuncios que encajaban con tus criterios pero que ya estaban en la "
                "bandeja, en seguimiento o descartados, por lo que no se han vuelto a añadir.",
            ),
            "sin-coincidencia": (
                "sin_match",
                "Anuncios sin coincidencia",
                "Anuncios de la sección de oposiciones del BOE que no encajaron con "
                "ningún perfil de búsqueda. Si ves alguno que te interesa, ajusta tus "
                "criterios en Configuración.",
            ),
        }
        if clase not in mapa:
            abort(404)
        clasif, titulo, descripcion = mapa[clase]
        with db.get_session() as s:
            fuentes_prov = {f.codigo: f.provincia for f in s.scalars(select(Fuente)).all()}
            items = s.scalars(
                select(ResultadoBusqueda)
                .where(ResultadoBusqueda.clasificacion == clasif)
                .order_by(ResultadoBusqueda.id)
            ).all()
            _, seg_cods = _seguimiento_sets(s)
            filas = []
            for r in items:
                if (r.fuente_codigo, r.referencia_oficial) in seg_cods:
                    continue  # ya en seguimiento: no reaparece en estas listas
                d = extraccion.extraer(r)
                ambito = d["localidad"] or fuentes_prov.get(r.fuente_codigo) or ""
                filas.append({
                    "id": r.id,
                    "referencia": r.referencia_oficial,
                    "titulo": r.titulo,
                    "organismo": r.organismo,
                    "url": r.url,
                    "fecha": r.fecha_publicacion,
                    "puesto": r.puesto or d["puesto"],
                    "num_plazas": d["num_plazas"],
                    "tipo_personal": d["tipo_personal"],
                    "sistema_acceso": d["sistema_acceso"],
                    "turno": d["turno"],
                    "ambito": ambito,
                    "fuente": r.fuente_codigo or "",
                })
            ambitos = sorted({f["ambito"] for f in filas if f["ambito"]})
            # Todos los boletines activos (no solo los presentes en estos
            # resultados), para que el filtro sea consistente (p. ej. el BOJA).
            fuentes = [
                fu.codigo for fu in s.scalars(
                    select(Fuente).where(Fuente.activa.is_(True)).order_by(Fuente.id)
                ).all()
            ]
            tipos = sorted({f["tipo_personal"] for f in filas if f["tipo_personal"]})
            sistemas = sorted({f["sistema_acceso"] for f in filas if f["sistema_acceso"]})
            return render_template(
                "resultados.html", titulo=titulo, descripcion=descripcion,
                filas=filas, ambitos=ambitos, fuentes=fuentes,
                tipos=tipos, sistemas=sistemas,
            )

    @app.route("/resultado/<int:rid>/seguimiento", methods=["POST"])
    def resultado_a_seguimiento(rid):
        with db.get_session() as s:
            r = s.get(ResultadoBusqueda, rid)
            if not r:
                abort(404)
            fuente = s.scalar(select(Fuente).where(Fuente.codigo == (r.fuente_codigo or "BOE")))
            fase = s.scalar(select(Fase).where(Fase.codigo == "convocada"))
            tipo = s.scalar(select(TipoPublicacion).where(TipoPublicacion.codigo == "bases"))
            datos = extraccion.extraer(r)
            conv = Convocatoria(
                organismo=r.organismo,
                localidad=datos["localidad"],
                provincia=datos["localidad"],
                puesto=datos["puesto"],
                grupo=datos["categoria"],
                num_plazas=datos["num_plazas"],
                tipo_personal=datos["tipo_personal"],
                sistema_acceso=datos["sistema_acceso"],
                fase=fase,
                estado_registro="activa",
                fecha_base_boe=r.fecha_publicacion,
            )
            s.add(Publicacion(
                convocatoria=conv,
                fuente_id=fuente.id if fuente else 1,
                referencia_oficial=r.referencia_oficial,
                tipo_publicacion=tipo,
                fecha_publicacion=r.fecha_publicacion,
                titulo=r.titulo,
                url=r.url,
            ))
            s.add(conv)
            _quitar_de_listas(s, fuente.id if fuente else None, r.fuente_codigo, r.referencia_oficial)
            s.flush()
            nuevo_id = conv.id
        flash("Añadida al seguimiento.", "ok")
        return redirect(url_for("ficha", cid=nuevo_id))

    @app.route("/resultado/<int:rid>/bandeja", methods=["POST"])
    def resultado_a_bandeja(rid):
        with db.get_session() as s:
            r = s.get(ResultadoBusqueda, rid)
            if not r:
                abort(404)
            fuente = s.scalar(select(Fuente).where(Fuente.codigo == (r.fuente_codigo or "BOE")))
            fid = fuente.id if fuente else 1
            # Revertir un posible descarte previo.
            d = s.scalar(select(Descarte).where(
                Descarte.fuente_id == fid, Descarte.referencia_oficial == r.referencia_oficial))
            if d:
                s.delete(d)
            cand = s.scalar(select(Candidato).where(
                Candidato.fuente_id == fid, Candidato.referencia_oficial == r.referencia_oficial))
            if cand:
                cand.estado = "pendiente"
            else:
                datos = extraccion.extraer(r)
                s.add(Candidato(
                    fuente_id=fid,
                    referencia_oficial=r.referencia_oficial,
                    fecha_publicacion=r.fecha_publicacion,
                    titulo=r.titulo,
                    url=r.url,
                    organismo=r.organismo,
                    localidad=datos["localidad"],
                    puesto=datos["puesto"],
                    categoria=datos["categoria"],
                    perfil_coincidente="(añadido manualmente)",
                    nivel_confianza="media",
                    score=0,
                ))
        flash("Enviada a la bandeja.", "ok")
        return redirect(url_for("bandeja"))

    @app.route("/resultado/<int:rid>/descartar", methods=["POST"])
    def resultado_descartar(rid):
        with db.get_session() as s:
            r = s.get(ResultadoBusqueda, rid)
            if not r:
                abort(404)
            fuente = s.scalar(select(Fuente).where(Fuente.codigo == (r.fuente_codigo or "BOE")))
            fid = fuente.id if fuente else 1
            existe = s.scalar(select(Descarte.id).where(
                Descarte.fuente_id == fid, Descarte.referencia_oficial == r.referencia_oficial))
            if not existe:
                s.add(Descarte(
                    fuente_id=fid,
                    referencia_oficial=r.referencia_oficial,
                    motivo="ruido (sin coincidencia)",
                ))
            s.delete(r)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=True)
        flash("Anuncio descartado; no volverá a aparecer en las búsquedas.", "ok")
        return redirect(request.referrer or url_for("bandeja"))

    @app.route("/resultado/<int:rid>/detectar-puesto", methods=["POST"])
    def resultado_detectar_puesto(rid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        with db.get_session() as s:
            r = s.get(ResultadoBusqueda, rid)
            if not r:
                abort(404)
            conector = get_conector(r.fuente_codigo or "")
            try:
                texto = _texto_anuncio(conector, r.referencia_oficial, r.url)
            except Exception as e:  # noqa: BLE001
                if ajax:
                    return jsonify(ok=False)
                flash(f"No se pudo leer el texto del anuncio: {e}", "error")
                return redirect(request.referrer or url_for("bandeja"))
            p = extraccion.puesto_desde_texto(texto)
            if p:
                r.puesto = p
            if ajax:
                return jsonify(ok=True, puesto=(p or ""))
            if p:
                flash(f"Puesto detectado: {p}.", "ok")
            else:
                flash("No se detectó el puesto en el cuerpo del anuncio.", "aviso")
        return redirect(request.referrer or url_for("bandeja"))

    @app.route("/resultado/<int:rid>/info", methods=["GET", "POST"])
    def resultado_info(rid):
        with db.get_session() as s:
            r = s.get(ResultadoBusqueda, rid)
            if not r:
                abort(404)
            fuente = s.scalar(select(Fuente).where(Fuente.codigo == (r.fuente_codigo or "BOE")))
            fid = fuente.id if fuente else 1
            if request.method == "POST":
                f = request.form
                accion = f.get("accion")
                if accion == "detectar":
                    # Rellena el puesto desde el cuerpo del anuncio (BOE) sin perder
                    # lo que el usuario ya haya escrito en el formulario.
                    datos = {
                        "id": r.id, "referencia": r.referencia_oficial,
                        "fuente": r.fuente_codigo or "", "titulo": f.get("titulo", ""),
                        "organismo": f.get("organismo", ""), "url": f.get("url", ""),
                        "puesto": f.get("puesto", ""), "localidad": f.get("localidad", ""),
                        "grupo": f.get("grupo", ""), "num_plazas": f.get("num_plazas", ""),
                        "tipo_personal": f.get("tipo_personal", ""),
                        "sistema_acceso": f.get("sistema_acceso", ""),
                    }
                    conector = get_conector(r.fuente_codigo or "")
                    try:
                        p = extraccion.puesto_desde_texto(
                            _texto_anuncio(conector, r.referencia_oficial, r.url)
                        )
                        if p:
                            datos["puesto"] = p
                            flash(f"Puesto detectado: {p}.", "ok")
                        else:
                            flash("No se detectó el puesto en el cuerpo del anuncio.", "aviso")
                    except Exception as e:  # noqa: BLE001
                        flash(f"No se pudo leer el texto del anuncio: {e}", "error")
                    return render_template("resultado_info.html", r=datos)
                if accion == "seguir":
                    fase = s.scalar(select(Fase).where(Fase.codigo == "convocada"))
                    tipo = s.scalar(select(TipoPublicacion).where(TipoPublicacion.codigo == "bases"))
                    conv = Convocatoria(
                        organismo=f.get("organismo") or None,
                        localidad=f.get("localidad") or None,
                        provincia=f.get("localidad") or None,
                        puesto=f.get("puesto") or None,
                        grupo=f.get("grupo") or None,
                        num_plazas=_int_or_none(f.get("num_plazas")),
                        tipo_personal=f.get("tipo_personal") or None,
                        sistema_acceso=f.get("sistema_acceso") or None,
                        fase=fase,
                        estado_registro="activa",
                        fecha_base_boe=r.fecha_publicacion,
                    )
                    s.add(Publicacion(
                        convocatoria=conv, fuente_id=fid,
                        referencia_oficial=r.referencia_oficial, tipo_publicacion=tipo,
                        fecha_publicacion=r.fecha_publicacion,
                        titulo=f.get("titulo") or r.titulo, url=f.get("url") or r.url,
                    ))
                    s.add(conv)
                    s.delete(r)
                    s.flush()
                    nuevo_id = conv.id
                    flash("Añadida al seguimiento con la información indicada.", "ok")
                    return redirect(url_for("ficha", cid=nuevo_id))
                # accion == "review" -> a la bandeja
                d = s.scalar(select(Descarte).where(
                    Descarte.fuente_id == fid, Descarte.referencia_oficial == r.referencia_oficial))
                if d:
                    s.delete(d)
                cand = s.scalar(select(Candidato).where(
                    Candidato.fuente_id == fid, Candidato.referencia_oficial == r.referencia_oficial))
                if cand:
                    cand.estado = "pendiente"
                    cand.organismo = f.get("organismo") or None
                    cand.localidad = f.get("localidad") or None
                    cand.puesto = f.get("puesto") or None
                    cand.categoria = f.get("grupo") or None
                else:
                    s.add(Candidato(
                        fuente_id=fid, referencia_oficial=r.referencia_oficial,
                        fecha_publicacion=r.fecha_publicacion,
                        titulo=f.get("titulo") or r.titulo, url=f.get("url") or r.url,
                        organismo=f.get("organismo") or None,
                        localidad=f.get("localidad") or None,
                        puesto=f.get("puesto") or None,
                        categoria=f.get("grupo") or None,
                        perfil_coincidente="(añadido manualmente)",
                        nivel_confianza="media", score=0,
                    ))
                s.delete(r)
                flash("Enviada a la bandeja con la información indicada.", "ok")
                return redirect(url_for("bandeja"))
            # GET: formulario pre-relleno con lo extraído por las heurísticas.
            d = extraccion.extraer(r)
            datos = {
                "id": r.id, "referencia": r.referencia_oficial, "fuente": r.fuente_codigo or "",
                "titulo": r.titulo or "", "organismo": r.organismo or "", "url": r.url or "",
                "puesto": d["puesto"] or "", "localidad": d["localidad"] or "",
                "grupo": d["categoria"] or "", "num_plazas": d["num_plazas"] or "",
                "tipo_personal": d["tipo_personal"] or "", "sistema_acceso": d["sistema_acceso"] or "",
            }
            return render_template("resultado_info.html", r=datos)

    # ---- Configuración de búsqueda ------------------------------------
    @app.route("/configuracion")
    def configuracion():
        with db.get_session() as s:
            perfiles = s.scalars(select(PerfilBusqueda).order_by(PerfilBusqueda.nombre)).all()
            perfiles_data = [_perfil_dto(p) for p in perfiles]
            fuentes = [
                {"id": f.id, "codigo": f.codigo, "nombre": f.nombre, "activa": f.activa}
                for f in s.scalars(select(Fuente).order_by(Fuente.id)).all()
            ]
            ajustes_app = {
                "max_busquedas_dia": get_ajuste_int(s, "max_busquedas_dia", config.MAX_BUSQUEDAS_DIA),
            }
            return render_template(
                "configuracion.html", perfiles=perfiles_data, fuentes=fuentes,
                ajustes_app=ajustes_app,
            )

    @app.route("/configuracion/ajustes", methods=["POST"])
    def config_ajustes():
        with db.get_session() as s:
            for clave, minimo in (("max_busquedas_dia", 0),):
                try:
                    val = max(minimo, int(request.form.get(clave, "")))
                    set_ajuste(s, clave, str(val))
                except (TypeError, ValueError):
                    pass
        flash("Opciones guardadas.", "ok")
        return redirect(url_for("configuracion"))

    @app.route("/configuracion/perfil/nuevo", methods=["POST"])
    def perfil_nuevo():
        nombre = (request.form.get("nombre") or "").strip()
        if nombre:
            with db.get_session() as s:
                if s.scalar(select(PerfilBusqueda).where(PerfilBusqueda.nombre == nombre)):
                    flash("Ya existe un perfil con ese nombre.", "error")
                else:
                    s.add(PerfilBusqueda(
                        nombre=nombre,
                        rama=request.form.get("rama") or None,
                        ambito=request.form.get("ambito") or None,
                        activo=True,
                    ))
                    flash("Perfil creado.", "ok")
        return redirect(url_for("configuracion"))

    @app.route("/configuracion/perfil/<int:pid>/toggle", methods=["POST"])
    def perfil_toggle(pid):
        with db.get_session() as s:
            p = s.get(PerfilBusqueda, pid)
            if not p:
                abort(404)
            p.activo = not p.activo
        return redirect(request.referrer or url_for("configuracion"))

    @app.route("/configuracion/perfil/<int:pid>/eliminar", methods=["POST"])
    def perfil_eliminar(pid):
        with db.get_session() as s:
            p = s.get(PerfilBusqueda, pid)
            if not p:
                abort(404)
            s.delete(p)
        flash("Perfil eliminado.", "ok")
        return redirect(url_for("configuracion"))

    @app.route("/configuracion/perfil/<int:pid>")
    def perfil_editar(pid):
        with db.get_session() as s:
            p = s.get(PerfilBusqueda, pid)
            if not p:
                abort(404)
            datos = _perfil_dto(p)
        return render_template("perfil_editar.html", p=datos)

    @app.route("/configuracion/perfil/<int:pid>/datos", methods=["POST"])
    def perfil_datos(pid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        nombre = (request.form.get("nombre") or "").strip()
        with db.get_session() as s:
            p = s.get(PerfilBusqueda, pid)
            if not p:
                abort(404)
            if nombre:
                dup = s.scalar(
                    select(PerfilBusqueda).where(
                        PerfilBusqueda.nombre == nombre, PerfilBusqueda.id != pid
                    )
                )
                if dup:
                    if ajax:
                        return jsonify(ok=False, error="Ya existe un perfil con ese nombre."), 400
                    flash("Ya existe un perfil con ese nombre.", "error")
                    return redirect(url_for("perfil_editar", pid=pid))
                p.nombre = nombre
            p.rama = request.form.get("rama") or None
            p.ambito = request.form.get("ambito") or None
            datos = {"nombre": p.nombre, "rama": p.rama, "ambito": p.ambito}
        if ajax:
            return jsonify(ok=True, **datos)
        flash("Perfil actualizado.", "ok")
        return redirect(url_for("perfil_editar", pid=pid))

    @app.route("/configuracion/perfil/<int:pid>/regla", methods=["POST"])
    def regla_add(pid):
        termino = (request.form.get("termino") or "").strip()
        tipo = request.form.get("tipo")
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if termino and tipo in ("tematica", "geografica", "exclusion"):
            with db.get_session() as s:
                if not s.get(PerfilBusqueda, pid):
                    abort(404)
                r = ReglaCriterio(perfil_id=pid, tipo=tipo, termino=termino)
                s.add(r)
                s.flush()
                datos = {"id": r.id, "termino": r.termino, "tipo": r.tipo}
            if ajax:
                return jsonify(ok=True, **datos)
            return redirect(request.referrer or url_for("configuracion"))
        if ajax:
            return jsonify(ok=False, error="Término o tipo no válido"), 400
        return redirect(request.referrer or url_for("configuracion"))

    @app.route("/configuracion/regla/<int:rid>/eliminar", methods=["POST"])
    def regla_eliminar(rid):
        ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        with db.get_session() as s:
            r = s.get(ReglaCriterio, rid)
            if not r:
                abort(404)
            s.delete(r)
        if ajax:
            return jsonify(ok=True)
        return redirect(request.referrer or url_for("configuracion"))

    @app.route("/configuracion/fuente/<int:fid>/toggle", methods=["POST"])
    def fuente_toggle(fid):
        with db.get_session() as s:
            f = s.get(Fuente, fid)
            if not f:
                abort(404)
            f.activa = not f.activa
        return redirect(url_for("configuracion"))

    @app.route("/configuracion/modo-panico", methods=["POST"])
    def modo_panico():
        with db.get_session() as s:
            n_desc = s.scalar(select(func.count()).select_from(Descarte)) or 0
            n_cand = s.scalar(
                select(func.count()).select_from(Candidato).where(Candidato.estado == "descartado")
            ) or 0
            s.execute(delete(Descarte))
            s.execute(delete(Candidato).where(Candidato.estado == "descartado"))
        flash(
            f"Modo pánico activado: eliminados {n_desc} descartes y {n_cand} novedades "
            "descartadas. Esos anuncios podrán volver a aparecer en próximas búsquedas.",
            "ok",
        )
        return redirect(url_for("configuracion"))

    return app


# --- Helpers -------------------------------------------------------------
def _nombre_conv(c: Convocatoria) -> str:
    return c.puesto or c.organismo or f"Convocatoria {c.id}"


def _tipos_publicacion(s):
    tipos = s.scalars(select(TipoPublicacion).order_by(TipoPublicacion.orden)).all()
    return [{"codigo": t.codigo, "nombre": t.nombre} for t in tipos]


def _ambito_boletin(codigo, provincia):
    """Etiqueta de localidad/ámbito de un boletín para el resumen de búsqueda."""
    if provincia:
        return provincia
    return {"BOE": "Estatal", "BOJA": "Andalucía"}.get(codigo, "")


def _perfil_dto(p) -> dict:
    """Serializa un perfil y sus reglas (por tipo) para las plantillas."""
    return {
        "id": p.id, "nombre": p.nombre, "activo": p.activo,
        "rama": p.rama, "ambito": p.ambito,
        "tematicas": [(r.id, r.termino) for r in p.reglas if r.tipo == "tematica"],
        "geograficas": [(r.id, r.termino) for r in p.reglas if r.tipo == "geografica"],
        "exclusiones": [(r.id, r.termino) for r in p.reglas if r.tipo == "exclusion"],
    }


def _ficha_data(s, c: Convocatoria) -> dict:
    # Migración suave: el antiguo url_info único pasa a la lista de enlaces.
    if c.url_info and not c.enlaces_info:
        c.enlaces_info.append(EnlaceInfo(url=c.url_info))
        c.url_info = None
        s.flush()
    enlaces = [{"id": e.id, "url": e.url, "titulo": e.titulo} for e in c.enlaces_info]
    publicaciones = sorted(
        c.publicaciones, key=lambda p: (p.fecha_publicacion or date.min)
    )
    # Fecha tope = N días hábiles desde la fecha base del BOE (N configurable).
    dias_plazo = c.dias_habiles_plazo or 20
    fecha_tope = _sumar_dias_habiles(c.fecha_base_boe, dias_plazo) if c.fecha_base_boe else None
    dias_restantes = _dias_habiles_entre(date.today(), fecha_tope) if fecha_tope else None
    tope_vencido = bool(fecha_tope and fecha_tope < date.today())
    plazos = []
    for _p in sorted(c.plazos, key=lambda p: (p.fecha_fin or date.max)):
        _abierto = bool(_p.fecha_inicio and _p.fecha_fin and _p.fecha_inicio <= date.today() <= _p.fecha_fin)
        plazos.append({
            "id": _p.id,
            "tipo_plazo": _p.tipo_plazo,
            "fecha_inicio": _p.fecha_inicio,
            "fecha_fin": _p.fecha_fin,
            "abierto": _abierto,
            "dias_rest": _dias_habiles_entre(date.today(), _p.fecha_fin) if _abierto else None,
        })
    _pares_tope = {(p.fecha_inicio, p.fecha_fin) for p in c.plazos if p.tipo_plazo == "Plazo abierto"}
    plazo_tope_existe = bool(fecha_tope and (c.fecha_base_boe, fecha_tope) in _pares_tope)
    plazos_abiertos = [
        f"{p.fecha_inicio.isoformat()}|{p.fecha_fin.isoformat()}"
        for p in c.plazos
        if p.tipo_plazo == "Plazo abierto" and p.fecha_inicio and p.fecha_fin
    ]
    return {
        "c": c,
        "enlaces": enlaces,
        "dias_plazo": dias_plazo,
        "fecha_tope": fecha_tope,
        "dias_restantes": dias_restantes,
        "tope_vencido": tope_vencido,
        "plazo_tope_existe": plazo_tope_existe,
        "plazos_abiertos": plazos_abiertos,
        "publicaciones": publicaciones,
        "temas": sorted(c.temas, key=lambda t: (t.bloque or "", t.numero or 0)),
        "plazos": plazos,
        "requisitos": c.requisitos,
        "leyes": c.leyes,
        "documentos_temario": sorted(
            [d for d in c.documentos if d.categoria == "temario"],
            key=lambda d: d.fecha or datetime.min,
        ),
        "documentos_requisitos": sorted(
            [d for d in c.documentos if d.categoria == "requisitos"],
            key=lambda d: d.fecha or datetime.min,
        ),
        "fases": s.scalars(select(Fase).order_by(Fase.orden)).all(),
        "estados": s.scalars(select(EstadoPersonal).order_by(EstadoPersonal.id)).all(),
        "tipos": _tipos_publicacion(s),
    }
