# engine/symbols.py
from __future__ import annotations

import re

# Codes mois (futures) -> numéro de mois
_MONTH_CODE = {
    "F": 1,  # Jan
    "G": 2,  # Feb
    "H": 3,  # Mar
    "J": 4,  # Apr
    "K": 5,  # May
    "M": 6,  # Jun
    "N": 7,  # Jul
    "Q": 8,  # Aug
    "U": 9,  # Sep
    "V": 10, # Oct
    "X": 11, # Nov
    "Z": 12, # Dec
}

_SYMBOL_RE = re.compile(r"^ZQ([FGHJKMNQUVXZ])(\d{2})$")

def fed_funds_symbol_to_month(symbol: str) -> str | None:
    """
    Convertit un symbol CME 30-Day Fed Funds type ZQX25 en 'YYYY-MM'.
    Retourne None si le format n'est pas reconnu.
    """
    s = (symbol or "").strip().upper()
    m = _SYMBOL_RE.match(s)
    if not m:
        return None

    month_code = m.group(1)
    yy = int(m.group(2))
    year = 2000 + yy
    month = _MONTH_CODE[month_code]
    return f"{year:04d}-{month:02d}"
