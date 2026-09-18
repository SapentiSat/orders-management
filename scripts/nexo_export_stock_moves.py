#!/usr/bin/env python3
"""
Eksport ruchów magazynowych Nexo → stock_moves.json

Tylko plus/minus (PZ, PW, WZ, RW) dla magazynu Symbol = '001'.
Bez ZD, bez rezerwacji — resztę dodajesz osobno.

Użycie:
  python scripts/nexo_export_stock_moves.py
  python scripts/nexo_export_stock_moves.py -o C:\\export\\stock_moves.json

Wymaga: pip install pyodbc
ODBC: Microsoft ODBC Driver 17 for SQL Server
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

try:
    import pyodbc
except ImportError:
    print("Brak pyodbc: pip install pyodbc", file=sys.stderr)
    sys.exit(1)

# --- KONFIGURACJA (edytuj albo ustaw zmienne środowiskowe) ---
SQL_SERVER = os.environ.get("NEXO_SQL_SERVER", r"localhost\NEXO")
SQL_DATABASE = os.environ.get("NEXO_SQL_DATABASE", "Nexo_Baza")
SQL_USER = os.environ.get("NEXO_SQL_USER", "")
SQL_PASSWORD = os.environ.get("NEXO_SQL_PASSWORD", "")
SQL_TRUSTED = os.environ.get("NEXO_SQL_TRUSTED", "0") == "1"

SCHEMA = "ModelDanychContainer"
WAREHOUSE_SYMBOL = os.environ.get("NEXO_MAGAZYN", "MAG")  # Symbol magazynu w Nexo
DAYS_BACK = int(os.environ.get("NEXO_DNI", "365"))

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "sample_data" / "stock_moves.json"

SQL = f"""
SELECT id, [date], qty, move_type, document_symbol, warehouse
FROM (
  SELECT
    CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
    CAST(d.DataWprowadzenia AS date) AS [date],
    ABS(pd.IloscWJednostceBazowej) AS qty,
    'receipt' AS move_type,
    d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
    mg.Symbol AS warehouse
  FROM {SCHEMA}.PozycjeDokumentu pd
  INNER JOIN {SCHEMA}.Dokumenty d ON d.Id = pd.Dokument_Id
  INNER JOIN {SCHEMA}.Magazyny mg ON mg.Id = COALESCE(pd.MagazynId, d.MagazynId)
  WHERE mg.Symbol = ?
    AND d.DataWprowadzenia >= DATEADD(day, -?, CAST(GETDATE() AS date))
    AND (
      d.KlasaDokumentu IN ('DokumentPZ', 'DokumentPW')
      OR d.Symbol IN ('PZ', 'PW')
    )
    AND pd.AsortymentAktualnyId IS NOT NULL
    AND pd.IloscWJednostceBazowej <> 0

  UNION ALL

  SELECT
    CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
    CAST(d.DataWprowadzenia AS date) AS [date],
    -ABS(pd.IloscWJednostceBazowej) AS qty,
    'issue' AS move_type,
    d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
    mg.Symbol AS warehouse
  FROM {SCHEMA}.PozycjeDokumentu pd
  INNER JOIN {SCHEMA}.Dokumenty d ON d.Id = pd.Dokument_Id
  INNER JOIN {SCHEMA}.Magazyny mg ON mg.Id = COALESCE(pd.MagazynId, d.MagazynId)
  WHERE mg.Symbol = ?
    AND d.DataWprowadzenia >= DATEADD(day, -?, CAST(GETDATE() AS date))
    AND (
      d.KlasaDokumentu IN ('DokumentWZ', 'DokumentRW')
      OR d.Symbol IN ('WZ', 'RW')
    )
    AND pd.AsortymentAktualnyId IS NOT NULL
    AND pd.IloscWJednostceBazowej <> 0
) moves
ORDER BY [date], document_symbol
"""


def _conn_str() -> str:
    if SQL_TRUSTED:
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};Trusted_Connection=yes;"
        )
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};"
        f"UID={SQL_USER};PWD={SQL_PASSWORD};"
    )


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def export_stock_moves() -> list[dict]:
    params = (WAREHOUSE_SYMBOL, DAYS_BACK, WAREHOUSE_SYMBOL, DAYS_BACK)
    with pyodbc.connect(_conn_str(), timeout=60) as conn:
        conn.timeout = 300
        cur = conn.cursor()
        cur.execute(SQL, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Nexo → stock_moves.json")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT, help="Plik wyjściowy JSON")
    parser.add_argument("--magazyn", default=WAREHOUSE_SYMBOL, help="Symbol magazynu (domyślnie 001)")
    parser.add_argument("--dni", type=int, default=DAYS_BACK, help="Ile dni wstecz")
    args = parser.parse_args()

    global WAREHOUSE_SYMBOL, DAYS_BACK
    WAREHOUSE_SYMBOL = args.magazyn
    DAYS_BACK = args.dni

    print(f"Eksport: magazyn={WAREHOUSE_SYMBOL}, dni={DAYS_BACK}, baza={SQL_DATABASE}")
    rows = export_stock_moves()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"Zapisano {len(rows)} wierszy → {args.output}")


if __name__ == "__main__":
    main()
