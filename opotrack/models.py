"""Modelo de datos de OpoTrack (SQLAlchemy 2.0).

Entidades núcleo: Convocatoria y Publicacion. Alrededor: temas, plazos,
requisitos, titulación, leyes (con enlaces N:M), perfiles de búsqueda,
bandeja de candidatos, memoria de descartes y catálogos.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- Tablas de asociación N:M -------------------------------------------
tema_ley = Table(
    "tema_ley",
    Base.metadata,
    Column("tema_id", ForeignKey("tema.id", ondelete="CASCADE"), primary_key=True),
    Column("ley_id", ForeignKey("ley.id", ondelete="CASCADE"), primary_key=True),
)

convocatoria_ley = Table(
    "convocatoria_ley",
    Base.metadata,
    Column("convocatoria_id", ForeignKey("convocatoria.id", ondelete="CASCADE"), primary_key=True),
    Column("ley_id", ForeignKey("ley.id", ondelete="CASCADE"), primary_key=True),
)


# --- Catálogos -----------------------------------------------------------
class Fuente(Base):
    __tablename__ = "fuente"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)   # BOE, BOPG, BOPMA...
    nombre: Mapped[str] = mapped_column(String(120))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    # Provincia implícita de la fuente (BOP provinciales): se inyecta en el
    # filtrado para que los perfiles geográficos casen aunque el título no la cite.
    provincia: Mapped[str | None] = mapped_column(String(80))


class TipoPublicacion(Base):
    __tablename__ = "tipo_publicacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Fase(Base):
    __tablename__ = "fase"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)


class EstadoPersonal(Base):
    __tablename__ = "estado_personal"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))


# --- Entidades núcleo ----------------------------------------------------
class Convocatoria(Base):
    __tablename__ = "convocatoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    organismo: Mapped[str | None] = mapped_column(String(255))
    ambito: Mapped[str | None] = mapped_column(String(40))        # estatal/autonomico/provincial/local
    provincia: Mapped[str | None] = mapped_column(String(80))
    localidad: Mapped[str | None] = mapped_column(String(120))
    cuerpo_escala: Mapped[str | None] = mapped_column(String(255))
    puesto: Mapped[str | None] = mapped_column(String(255))
    grupo: Mapped[str | None] = mapped_column(String(20))          # C1, C2, B, M1, M2, E2...
    rama: Mapped[str | None] = mapped_column(String(40))           # administrativa / informatica
    tipo_personal: Mapped[str | None] = mapped_column(String(20))  # funcionario / laboral
    sistema_acceso: Mapped[str | None] = mapped_column(String(60))
    num_plazas: Mapped[int | None] = mapped_column(Integer)

    fase_id: Mapped[int | None] = mapped_column(ForeignKey("fase.id"))
    estado_personal_id: Mapped[int | None] = mapped_column(ForeignKey("estado_personal.id"))

    # Borrado a papelera (reversible).
    estado_registro: Mapped[str] = mapped_column(String(20), default="activa")  # activa / en_papelera
    fecha_eliminacion: Mapped[date | None] = mapped_column(Date)
    motivo_eliminacion: Mapped[str | None] = mapped_column(String(255))

    fecha_base_boe: Mapped[date | None] = mapped_column(Date)
    dias_habiles_plazo: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    url_info: Mapped[str | None] = mapped_column(String(255))   # enlace a más información
    favorito: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_alta: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    fase: Mapped[Fase | None] = relationship()
    estado_personal: Mapped[EstadoPersonal | None] = relationship()
    publicaciones: Mapped[list["Publicacion"]] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan"
    )
    temas: Mapped[list["Tema"]] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan"
    )
    plazos: Mapped[list["Plazo"]] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan"
    )
    requisitos: Mapped[list["RequisitoEspecifico"]] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan"
    )
    titulacion: Mapped["Titulacion | None"] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan", uselist=False
    )
    leyes: Mapped[list["Ley"]] = relationship(
        secondary=convocatoria_ley, back_populates="convocatorias"
    )
    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan"
    )
    enlaces_info: Mapped[list["EnlaceInfo"]] = relationship(
        back_populates="convocatoria", cascade="all, delete-orphan"
    )


class Publicacion(Base):
    __tablename__ = "publicacion"
    __table_args__ = (
        UniqueConstraint("fuente_id", "referencia_oficial", name="uq_pub_fuente_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE")
    )
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuente.id"))
    referencia_oficial: Mapped[str] = mapped_column(String(40))   # BOE-A-2026-14786
    tipo_publicacion_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_publicacion.id"))
    fecha_publicacion: Mapped[date | None] = mapped_column(Date)
    titulo: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(255))
    ruta_pdf: Mapped[str | None] = mapped_column(String(255))
    resumen: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)   # info añadida a mano
    fecha_deteccion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="publicaciones")
    fuente: Mapped[Fuente] = relationship()
    tipo_publicacion: Mapped[TipoPublicacion | None] = relationship()


class Tema(Base):
    __tablename__ = "tema"
    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE")
    )
    bloque: Mapped[str | None] = mapped_column(String(120))        # general / especifica / ...
    numero: Mapped[int | None] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(Text)
    estado_estudio: Mapped[str] = mapped_column(String(20), default="pendiente")
    notas: Mapped[str | None] = mapped_column(Text)

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="temas")
    leyes: Mapped[list["Ley"]] = relationship(secondary=tema_ley, back_populates="temas")


class Plazo(Base):
    __tablename__ = "plazo"
    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE")
    )
    tipo_plazo: Mapped[str | None] = mapped_column(String(60))     # solicitud / subsanacion / ...
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    publicacion_origen_id: Mapped[int | None] = mapped_column(ForeignKey("publicacion.id"))
    notas: Mapped[str | None] = mapped_column(Text)

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="plazos")


class Documento(Base):
    """Archivo (PDF/DOCX) adjunto a una convocatoria, agrupado por categoría
    ('temario' o 'requisitos'). Se guarda en disco; en la BBDD el nombre real
    (en disco) y el nombre original para descargar."""
    __tablename__ = "documento"
    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE")
    )
    categoria: Mapped[str] = mapped_column(String(20))   # temario / requisitos
    archivo: Mapped[str] = mapped_column(String(255))    # nombre en disco
    nombre: Mapped[str] = mapped_column(String(255))     # nombre original
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="documentos")


class EnlaceInfo(Base):
    """Enlace de información (URL) asociado a una convocatoria; puede haber varios."""
    __tablename__ = "enlace_info"
    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(String(500))
    titulo: Mapped[str | None] = mapped_column(String(255))   # etiqueta opcional

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="enlaces_info")


class Titulacion(Base):
    __tablename__ = "titulacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE"), unique=True
    )
    nivel_academico: Mapped[str | None] = mapped_column(String(120))
    titulos_admitidos: Mapped[str | None] = mapped_column(Text)
    admite_equivalentes: Mapped[bool | None] = mapped_column(Boolean)
    texto_literal: Mapped[str | None] = mapped_column(Text)        # requisito tal cual lo publica el BOE
    cumple_usuario: Mapped[bool | None] = mapped_column(Boolean)   # previsto, sin uso en el MVP

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="titulacion")


class RequisitoEspecifico(Base):
    __tablename__ = "requisito_especifico"
    id: Mapped[int] = mapped_column(primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="CASCADE")
    )
    descripcion: Mapped[str] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="requisitos")


class Ley(Base):
    __tablename__ = "ley"
    id: Mapped[int] = mapped_column(primary_key=True)
    denominacion: Mapped[str] = mapped_column(Text)               # "Ley 39/2015, de 1 de octubre, ..."
    tipo_rango: Mapped[str | None] = mapped_column(String(80))    # ley, ley orgánica, real decreto...
    numero: Mapped[str | None] = mapped_column(String(40))
    anio: Mapped[int | None] = mapped_column(Integer)
    fecha: Mapped[date | None] = mapped_column(Date)
    identificador_boe: Mapped[str | None] = mapped_column(String(40))   # BOE-A-2015-10565
    url_consolidada: Mapped[str | None] = mapped_column(String(255))
    ambito: Mapped[str | None] = mapped_column(String(40))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_actualizacion_consolidada: Mapped[date | None] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text)

    temas: Mapped[list[Tema]] = relationship(secondary=tema_ley, back_populates="leyes")
    convocatorias: Mapped[list[Convocatoria]] = relationship(
        secondary=convocatoria_ley, back_populates="leyes"
    )


# --- Configuración de búsqueda (persistente) ----------------------------
class PerfilBusqueda(Base):
    __tablename__ = "perfil_busqueda"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    rama: Mapped[str | None] = mapped_column(String(40))          # administrativa / informatica
    ambito: Mapped[str | None] = mapped_column(String(120))       # etiqueta descriptiva del ámbito

    reglas: Mapped[list["ReglaCriterio"]] = relationship(
        back_populates="perfil", cascade="all, delete-orphan"
    )


class ReglaCriterio(Base):
    __tablename__ = "regla_criterio"
    id: Mapped[int] = mapped_column(primary_key=True)
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfil_busqueda.id", ondelete="CASCADE"))
    # 'tematica' (rama), 'geografica' (ámbito) o 'exclusion'.
    tipo: Mapped[str] = mapped_column(String(20))
    termino: Mapped[str] = mapped_column(String(120))

    perfil: Mapped[PerfilBusqueda] = relationship(back_populates="reglas")


# --- Bandeja de novedades y memoria de descartes ------------------------
class Candidato(Base):
    __tablename__ = "candidato"
    __table_args__ = (
        UniqueConstraint("fuente_id", "referencia_oficial", name="uq_cand_fuente_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuente.id"))
    referencia_oficial: Mapped[str] = mapped_column(String(40))
    fecha_publicacion: Mapped[date | None] = mapped_column(Date)
    titulo: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(255))
    organismo: Mapped[str | None] = mapped_column(String(255))
    localidad: Mapped[str | None] = mapped_column(String(120))
    puesto: Mapped[str | None] = mapped_column(String(255))
    categoria: Mapped[str | None] = mapped_column(String(60))
    perfil_coincidente: Mapped[str | None] = mapped_column(String(255))
    nivel_confianza: Mapped[str | None] = mapped_column(String(20))   # alta / media / baja
    score: Mapped[int] = mapped_column(Integer, default=0)
    fecha_entrada_bandeja: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Momento en que este candidato se avisó por Telegram (NULL = aún no avisado).
    # Lo usa el comando `notificar` para no repetir avisos ya enviados.
    fecha_notificacion: Mapped[datetime | None] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente/aceptado/descartado
    convocatoria_sugerida_id: Mapped[int | None] = mapped_column(ForeignKey("convocatoria.id"))

    fuente: Mapped[Fuente] = relationship()


class Descarte(Base):
    __tablename__ = "descarte"
    __table_args__ = (
        UniqueConstraint("fuente_id", "referencia_oficial", name="uq_desc_fuente_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuente.id"))
    referencia_oficial: Mapped[str] = mapped_column(String(40))
    fecha_descarte: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    motivo: Mapped[str | None] = mapped_column(String(255))

    fuente: Mapped[Fuente] = relationship()


class LogBusqueda(Base):
    """Registro de cada búsqueda, para aplicar el límite diario del botón."""
    __tablename__ = "log_busqueda"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    momento: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fuente_codigo: Mapped[str | None] = mapped_column(String(10))
    resultado: Mapped[str | None] = mapped_column(String(20))     # ok / no_publicado / error
    num_candidatos: Mapped[int] = mapped_column(Integer, default=0)
    num_ya_vistos: Mapped[int] = mapped_column(Integer, default=0)
    num_sin_match: Mapped[int] = mapped_column(Integer, default=0)


class ResultadoBusqueda(Base):
    """Anuncios clasificados como 'ya conocidos' o 'sin coincidencia', para
    revisarlos desde la web. 'ya_conocido' refleja solo la última búsqueda;
    'sin_match' se acumula hasta que el usuario lo borre."""
    __tablename__ = "resultado_busqueda"
    id: Mapped[int] = mapped_column(primary_key=True)
    clasificacion: Mapped[str] = mapped_column(String(20))        # ya_conocido / sin_match
    fuente_codigo: Mapped[str | None] = mapped_column(String(10))
    referencia_oficial: Mapped[str | None] = mapped_column(String(40))
    titulo: Mapped[str | None] = mapped_column(Text)
    organismo: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(255))
    puesto: Mapped[str | None] = mapped_column(String(255))   # detectado del cuerpo (bajo demanda)
    fecha_publicacion: Mapped[date | None] = mapped_column(Date)
    momento: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Ajuste(Base):
    """Ajustes clave-valor de la app (p. ej. el límite diario de búsquedas)."""
    __tablename__ = "ajuste"
    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(60), unique=True)
    valor: Mapped[str | None] = mapped_column(Text)

