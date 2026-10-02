"""Conectores de boletines oficiales.

Cada boletín se implementa como un adaptador que cumple la interfaz
``ConectorBase`` (ver ``base.py``). Registro central de conectores por código.
"""

from __future__ import annotations

from typing import Optional

from .base import AnuncioNormalizado, ConectorBase, SumarioNoDisponible
from .boe import ConectorBOE
from .ayto_benalmadena import ConectorBenalmadena
from .ayto_loja import ConectorLoja
from .ayto_huetortajar import ConectorHuetorTajar
from .ayto_antequera import ConectorAntequera
from .ayto_malaga import ConectorMalaga
from .ayto_motril import ConectorMotril
from .ayto_cordoba import ConectorCordoba
from .ayto_nerja import ConectorNerja
from .boja import ConectorBOJA
from .bop_cordoba import ConectorBOPCO, ConectorBOPJA
from .bop_granada import ConectorBOPG, ConectorBOPS
from .bop_malaga import ConectorBOPMA

CONECTORES = {
    ConectorBOE.codigo: ConectorBOE,        # "BOE"
    ConectorBOPG.codigo: ConectorBOPG,      # "BOPG"
    ConectorBOPS.codigo: ConectorBOPS,      # "BOPS" (Sevilla)
    ConectorBOPCO.codigo: ConectorBOPCO,    # "BOPCO" (Córdoba)
    ConectorBOPJA.codigo: ConectorBOPJA,    # "BOPJ" (Jaén)
    ConectorBOPMA.codigo: ConectorBOPMA,    # "BOPMA"
    ConectorBOJA.codigo: ConectorBOJA,      # "BOJA"
    ConectorBenalmadena.codigo: ConectorBenalmadena,  # "AYTBEN" (Ayto. Benalmádena)
    ConectorLoja.codigo: ConectorLoja,      # "AYTLOJA" (Ayto. Loja)
    ConectorHuetorTajar.codigo: ConectorHuetorTajar,  # "AYTHT" (Ayto. Huétor Tájar)
    ConectorAntequera.codigo: ConectorAntequera,      # "AYTANT" (Ayto. Antequera)
    ConectorMalaga.codigo: ConectorMalaga,            # "AYTMLG" (Ayto. Málaga capital)
    ConectorMotril.codigo: ConectorMotril,            # "AYTMOT" (Ayto. Motril)
    ConectorCordoba.codigo: ConectorCordoba,          # "AYTCOR" (Ayto. Córdoba capital)
    ConectorNerja.codigo: ConectorNerja,              # "AYTNER" (Ayto. Nerja)
}


def get_conector(codigo: str) -> Optional[ConectorBase]:
    """Devuelve una instancia del conector de esa fuente, o None si no existe."""
    cls = CONECTORES.get(codigo)
    return cls() if cls else None


__all__ = [
    "AnuncioNormalizado",
    "ConectorBase",
    "SumarioNoDisponible",
    "ConectorBOE",
    "ConectorBOJA",
    "ConectorBOPG",
    "ConectorBOPMA",
    "CONECTORES",
    "get_conector",
]
