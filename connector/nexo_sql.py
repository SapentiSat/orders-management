"""Nexo Pro SQL read-only export (4 JSON files)."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import pyodbc
except ImportError:  # pragma: no cover
    pyodbc = None  # type: ignore[assignment]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def connection_string(cfg: dict[str, Any]) -> str:
    if cfg.get("sql_trusted"):
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={cfg['sql_server']};"
            f"DATABASE={cfg['sql_database']};"
            "Trusted_Connection=yes;"
        )
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={cfg['sql_server']};"
        f"DATABASE={cfg['sql_database']};"
        f"UID={cfg['sql_user']};"
        f"PWD={cfg['sql_password']};"
    )


def connect(cfg: dict[str, Any]):
    if pyodbc is None:
        raise RuntimeError("Brak pyodbc — zainstaluj: pip install pyodbc")
    conn = pyodbc.connect(connection_string(cfg), timeout=30)
    conn.timeout = 120
    return conn


def _wh_filter(cfg: dict[str, Any], alias: str = "m") -> tuple[str, list[Any]]:
    wh = [w.strip() for w in (cfg.get("warehouses") or []) if str(w).strip()]
    if not wh:
        return "", []
    placeholders = ",".join("?" for _ in wh)
    return f" AND {alias}.Symbol IN ({placeholders})", wh


def _type_filter(cfg: dict[str, Any], alias: str = "r") -> tuple[str, list[Any]]:
    excl = [t.strip() for t in (cfg.get("exclude_types") or []) if str(t).strip()]
    if not excl:
        return "", []
    placeholders = ",".join("?" for _ in excl)
    return f" AND ({alias}.Symbol IS NULL OR {alias}.Symbol NOT IN ({placeholders}))", excl


def fetch_catalog(cfg: dict[str, Any]) -> dict[str, Any]:
    schema = cfg.get("schema") or "ModelDanychContainer"
    with connect(cfg) as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT Symbol, Nazwa FROM {schema}.Magazyny ORDER BY Symbol")
        warehouses = [{"symbol": r[0], "name": r[1]} for r in cur.fetchall()]
        cur.execute(
            f"SELECT Symbol, Nazwa, StanyMagazynowe FROM {schema}.RodzajeAsortymentu ORDER BY Symbol"
        )
        types = [{"symbol": r[0], "name": r[1], "has_stock": bool(r[2])} for r in cur.fetchall()]
        cur.execute(f"SELECT Symbol, Nazwa FROM {schema}.DzialySprzedazy ORDER BY Symbol")
        departments = [{"symbol": r[0], "name": r[1]} for r in cur.fetchall()]
    return {
        "database": cfg.get("sql_database"),
        "server": cfg.get("sql_server"),
        "warehouses": warehouses,
        "product_types": types,
        "departments": departments,
    }


def _rows(cur) -> list[dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def export_products(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    schema = cfg.get("schema") or "ModelDanychContainer"
    wh_sql, wh_params = _wh_filter(cfg)
    type_sql, type_params = _type_filter(cfg)
    aggregate = bool(cfg.get("aggregate_warehouses", True))
    if aggregate:
        sql = f"""
        SELECT
          CAST(a.Id AS varchar(32)) AS id,
          a.Symbol AS sku,
          MAX(k.Kod) AS ean,
          a.Nazwa AS name,
          MAX(ra.Symbol) AS product_type,
          MAX(g.Nazwa) AS [group],
          SUM(sm.IloscDostepna) AS available,
          SUM(sm.IloscZarezerwowanaIlosciowo + ISNULL(sm.IloscZarezerwowanaDostawowo, 0)) AS reserved,
          SUM(sm.IloscDostepna + sm.IloscZarezerwowanaIlosciowo
              + ISNULL(sm.IloscZarezerwowanaDostawowo, 0)) AS stock
        FROM {schema}.Asortymenty a
        JOIN {schema}.StanyMagazynowe sm ON sm.Asortyment_Id = a.Id
        JOIN {schema}.Magazyny m ON m.Id = sm.Magazyn_Id
        LEFT JOIN {schema}.KodyKreskowe k ON k.Asortyment_Id = a.Id AND k.Domyslny = 1
        LEFT JOIN {schema}.RodzajeAsortymentu ra ON ra.Id = a.Rodzaj_Id
        LEFT JOIN {schema}.GrupyAsortymentu g ON g.Id = a.GrupaAsortymentu_Id
        WHERE 1=1 {wh_sql} {type_sql}
        GROUP BY a.Id, a.Symbol, a.Nazwa
        ORDER BY a.Symbol
        """
    else:
        sql = f"""
        SELECT
          CAST(a.Id AS varchar(32)) AS id,
          a.Symbol AS sku,
          k.Kod AS ean,
          a.Nazwa AS name,
          ra.Symbol AS product_type,
          g.Nazwa AS [group],
          m.Symbol AS warehouse,
          sm.IloscDostepna AS available,
          sm.IloscZarezerwowanaIlosciowo + ISNULL(sm.IloscZarezerwowanaDostawowo, 0) AS reserved,
          sm.IloscDostepna + sm.IloscZarezerwowanaIlosciowo
            + ISNULL(sm.IloscZarezerwowanaDostawowo, 0) AS stock
        FROM {schema}.Asortymenty a
        JOIN {schema}.StanyMagazynowe sm ON sm.Asortyment_Id = a.Id
        JOIN {schema}.Magazyny m ON m.Id = sm.Magazyn_Id
        LEFT JOIN {schema}.KodyKreskowe k ON k.Asortyment_Id = a.Id AND k.Domyslny = 1
        LEFT JOIN {schema}.RodzajeAsortymentu ra ON ra.Id = a.Rodzaj_Id
        LEFT JOIN {schema}.GrupyAsortymentu g ON g.Id = a.GrupaAsortymentu_Id
        WHERE 1=1 {wh_sql} {type_sql}
        ORDER BY a.Symbol, m.Symbol
        """
    params = wh_params + type_params
    with connect(cfg) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return _rows(cur)


def export_sales(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    schema = cfg.get("schema") or "ModelDanychContainer"
    days = int(cfg.get("sales_days") or 365)
    wh_sql, wh_params = _wh_filter(cfg, "mg")
    type_sql, type_params = _type_filter(cfg)
    sql = f"""
    SELECT
      CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
      d.DataWprowadzenia AS [date],
      pd.IloscWJednostceBazowej AS qty,
      pd.WartoscNetto AS net_value,
      pd.KosztEwidencyjny AS cost
    FROM {schema}.PozycjeDokumentu pd
    JOIN {schema}.Dokumenty d ON d.Id = pd.Dokument_Id
    LEFT JOIN {schema}.Magazyny mg ON mg.Id = d.MagazynId
    LEFT JOIN {schema}.RodzajeAsortymentu r ON r.Id = pd.RodzajAsortymentuId
    WHERE d.DataWprowadzenia >= DATEADD(day, -?, GETDATE())
      AND d.Symbol IN ('FS', 'PA', 'FV', 'PAR')
      {wh_sql} {type_sql}
    ORDER BY d.DataWprowadzenia
    """
    params = [days] + wh_params + type_params
    with connect(cfg) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return _rows(cur)


def export_purchase_orders(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    schema = cfg.get("schema") or "ModelDanychContainer"
    wh_sql, wh_params = _wh_filter(cfg, "mg")
    sql = f"""
    SELECT
      CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
      pd.IloscWJednostceBazowej AS qty,
      idr.PozostalaIlosc AS qty_open,
      d.TerminRealizacji AS eta,
      'open' AS status,
      d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
      p.NazwaSkrocona AS supplier,
      mg.Symbol AS warehouse
    FROM {schema}.PozycjeDokumentu pd
    JOIN {schema}.Dokumenty d ON d.Id = pd.Dokument_Id
    LEFT JOIN {schema}.IlosciDoRealizacji idr ON idr.PozycjaDokumentuRealizowanego_Id = pd.Id
    LEFT JOIN {schema}.Podmioty p ON p.Id = d.PodmiotId
    LEFT JOIN {schema}.Magazyny mg ON mg.Id = pd.MagazynId
    WHERE d.Symbol LIKE 'ZD%'
      AND ISNULL(idr.PozostalaIlosc, pd.IloscWJednostceBazowej) > 0
      {wh_sql}
    ORDER BY d.TerminRealizacji
    """
    with connect(cfg) as conn:
        cur = conn.cursor()
        cur.execute(sql, wh_params)
        return _rows(cur)


def export_stock_moves(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    schema = cfg.get("schema") or "ModelDanychContainer"
    days = int(cfg.get("sales_days") or 365)
    wh_sql, wh_params = _wh_filter(cfg, "mg")
    sql = f"""
    SELECT id, [date], qty, move_type, document_symbol, warehouse FROM (
      SELECT
        CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
        d.DataWprowadzenia AS [date],
        ABS(pd.IloscWJednostceBazowej) AS qty,
        'receipt' AS move_type,
        d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
        mg.Symbol AS warehouse
      FROM {schema}.PozycjeDokumentu pd
      JOIN {schema}.Dokumenty d ON d.Id = pd.Dokument_Id
      LEFT JOIN {schema}.Magazyny mg ON mg.Id = d.MagazynId
      WHERE d.Symbol IN ('PZ', 'PW')
        AND d.DataWprowadzenia >= DATEADD(day, -?, GETDATE())
        {wh_sql}
      UNION ALL
      SELECT
        CAST(pd.AsortymentAktualnyId AS varchar(32)) AS id,
        d.DataWprowadzenia AS [date],
        -ABS(pd.IloscWJednostceBazowej) AS qty,
        'issue' AS move_type,
        d.NumerWewnetrzny_PelnaSygnatura AS document_symbol,
        mg.Symbol AS warehouse
      FROM {schema}.PozycjeDokumentu pd
      JOIN {schema}.Dokumenty d ON d.Id = pd.Dokument_Id
      LEFT JOIN {schema}.Magazyny mg ON mg.Id = d.MagazynId
      WHERE d.Symbol IN ('WZ', 'RW')
        AND d.DataWprowadzenia >= DATEADD(day, -?, GETDATE())
        {wh_sql}
    ) moves
    ORDER BY [date]
    """
    params = [days] + wh_params + [days] + wh_params
    with connect(cfg) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return _rows(cur)


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=_json_default)


def export_all(cfg: dict[str, Any], export_dir: Path) -> dict[str, Any]:
    export_dir.mkdir(parents=True, exist_ok=True)
    products = export_products(cfg)
    sales = export_sales(cfg)
    pos = export_purchase_orders(cfg)
    moves = export_stock_moves(cfg)
    write_json(export_dir / "products.json", products)
    write_json(export_dir / "sales.json", sales)
    write_json(export_dir / "purchase_orders.json", pos)
    write_json(export_dir / "stock_moves.json", moves)
    return {
        "products": len(products),
        "sales": len(sales),
        "purchase_orders": len(pos),
        "stock_moves": len(moves),
        "export_dir": str(export_dir),
    }


def export_demo(export_dir: Path, sample_root: Path) -> dict[str, Any]:
    export_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name in ("products", "sales", "purchase_orders", "stock_moves"):
        src = sample_root / f"{name}.json"
        dst = export_dir / f"{name}.json"
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            data = json.loads(dst.read_text(encoding="utf-8"))
            counts[name.replace(".json", "")] = len(data) if isinstance(data, list) else 0
        else:
            dst.write_text("[]", encoding="utf-8")
            counts[name.replace(".json", "")] = 0
    return {"demo": True, "export_dir": str(export_dir), **counts}
