from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_PRODUCT_FIELDS = ("id", "sku", "ean", "name")
OPTIONAL_PRODUCT_DEFAULTS = {
    "producer": "",
    "group": "",
    "product_type": "",
    "warehouse": "",
    "active": True,
    "eol": False,
    "stock": 0,
    "reserved": 0,
    "available": None,
    "inbound_qty": 0,
    "min_qty": 0,
    "moq": 1,
    "order_increment": 1,
    "lead_time_days": 30,
}
REQUIRED_SALES_FIELDS = ("id", "date", "qty", "net_value", "cost")


def peek_columns(path: Path) -> list[str]:
    """Return sorted source column names from an uploaded/sample JSON or CSV."""
    if not path.exists():
        return []
    try:
        df = _read_table(path)
    except Exception:  # noqa: BLE001
        return []
    return sorted(str(c) for c in df.columns if str(c).strip())


def _rename(df: pd.DataFrame, mapping: dict[str, str], *, required: tuple[str, ...]) -> pd.DataFrame:
    rename = {src: dst for dst, src in mapping.items() if src and src in df.columns}
    out = df.rename(columns=rename)
    missing = [dst for dst in required if dst not in out.columns]
    if missing:
        raise ValueError(f"Brak wymaganych pól po mapowaniu: {', '.join(missing)}")
    return out


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            for key in ("items", "data", "records", "products", "sales", "rows"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
            else:
                raise ValueError(
                    "JSON musi być listą obiektów albo obiektem z kluczem "
                    "items/data/records/products/sales/rows."
                )
        if not isinstance(payload, list):
            raise ValueError("JSON musi zawierać listę rekordów.")
        if not payload:
            return pd.DataFrame()
        if not all(isinstance(row, dict) for row in payload):
            raise ValueError("Każdy rekord JSON musi być obiektem {pole: wartość}.")
        return pd.DataFrame(payload)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Nieobsługiwany format pliku: {suffix}. Oczekiwany .json (lub .csv).")


def load_products(path: Path, column_map: dict[str, str]) -> pd.DataFrame:
    df = _read_table(path)
    df = _rename(df, column_map, required=REQUIRED_PRODUCT_FIELDS)
    for field, default in OPTIONAL_PRODUCT_DEFAULTS.items():
        if field not in df.columns:
            df[field] = default
    df["id"] = df["id"].map(_as_id)
    for col in ("stock", "reserved", "available", "inbound_qty", "min_qty", "moq", "order_increment", "lead_time_days"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["stock"] = df["stock"].fillna(0)
    df["reserved"] = df["reserved"].fillna(0)
    df.loc[df["moq"] <= 0, "moq"] = 1
    df.loc[df["order_increment"] <= 0, "order_increment"] = 1
    df.loc[df["lead_time_days"] <= 0, "lead_time_days"] = 30
    df["active"] = df["active"].map(_as_bool)
    df["eol"] = df["eol"].map(_as_bool)
    df["inbound_qty"] = df["inbound_qty"].fillna(0)
    # Nexo: IloscDostepna albo stan − rezerwacja
    if df["available"].notna().any():
        df["free_stock"] = df["available"].fillna(df["stock"] - df["reserved"]).clip(lower=0)
    else:
        df["free_stock"] = (df["stock"] - df["reserved"]).clip(lower=0)
    return df


def load_sales(path: Path, column_map: dict[str, str]) -> pd.DataFrame:
    df = _read_table(path)
    df = _rename(df, column_map, required=REQUIRED_SALES_FIELDS)
    df["id"] = df["id"].map(_as_id)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    df["net_value"] = pd.to_numeric(df["net_value"], errors="coerce").fillna(0)
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(0)
    return df


def _as_id(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if text.endswith(".0"):
        try:
            return str(int(float(text)))
        except ValueError:
            pass
    return text


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"0", "false", "nie", "no", "n", "nieaktywny", "inactive", "wyłączony", "wylaczony", "eol"}:
        return False
    if text in {"1", "true", "tak", "yes", "y", "aktywny", "active"}:
        return True
    return bool(text)


def _normalize_product_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text.replace("ł", "l").replace("ó", "o")


def default_exclude_product_types() -> set[str]:
    return {"usluga", "service", "us"}


def filter_stock_catalog(
    products: pd.DataFrame,
    sales: pd.DataFrame,
    stock_moves: pd.DataFrame | None,
    exclude_types: list[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, int]:
    """Usuń usługi i inne wykluczone typy z produktów, sprzedaży i ruchów."""
    excluded = {_normalize_product_type(x) for x in (exclude_types or []) if str(x).strip()}
    excluded |= default_exclude_product_types()
    before = len(products)
    if "product_type" in products.columns:
        types = products["product_type"].map(_normalize_product_type)
        products = products[~types.isin(excluded)].copy()
    removed = before - len(products)
    allowed = set(products["id"].astype(str))
    if not sales.empty:
        sales = sales[sales["id"].astype(str).isin(allowed)].copy()
    if stock_moves is not None and not stock_moves.empty:
        stock_moves = stock_moves[stock_moves["id"].astype(str).isin(allowed)].copy()
    return products, sales, stock_moves, removed


def aggregate_sales(sales: pd.DataFrame, window_days: int) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "qty_sum",
                "net_sum",
                "cost_sum",
                "tx_days",
                "daily_avg_qty",
                "cv_qty",
            ]
        )
    max_date = sales["date"].max()
    cutoff = max_date - pd.Timedelta(days=window_days)
    s = sales[sales["date"] >= cutoff].copy()
    s["day"] = s["date"].dt.floor("D")
    daily = s.groupby(["id", "day"], as_index=False)["qty"].sum()
    stats = s.groupby("id", as_index=False).agg(
        qty_sum=("qty", "sum"),
        net_sum=("net_value", "sum"),
        cost_sum=("cost", "sum"),
        tx_days=("day", "nunique"),
    )
    cv_rows = []
    for sku_id, g in daily.groupby("id"):
        mean = g["qty"].mean()
        std = g["qty"].std(ddof=0)
        cv = float(std / mean) if mean and mean > 0 else 999.0
        cv_rows.append({"id": sku_id, "cv_qty": cv})
    cv_df = pd.DataFrame(cv_rows) if cv_rows else pd.DataFrame(columns=["id", "cv_qty"])
    out = stats.merge(cv_df, on="id", how="left")
    out["daily_avg_qty"] = out["qty_sum"] / max(window_days, 1)
    return out


def _soft_rename(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    rename = {src: dst for dst, src in mapping.items() if src and src in df.columns}
    return df.rename(columns=rename)


def load_stock_moves(path: Path | None, column_map: dict[str, str]) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame(columns=["id", "date", "qty", "move_type"])
    df = _soft_rename(_read_table(path), column_map)
    for col in ("id", "date", "qty"):
        if col not in df.columns:
            return pd.DataFrame(columns=["id", "date", "qty", "move_type"])
    df["id"] = df["id"].map(_as_id)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    if "move_type" not in df.columns:
        df["move_type"] = "receipt"
    return df.dropna(subset=["date"])


def load_purchase_orders(path: Path | None, column_map: dict[str, str]) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame(columns=["id", "qty", "qty_open", "eta", "status"])
    df = _soft_rename(_read_table(path), column_map)
    if "id" not in df.columns:
        return pd.DataFrame(columns=["id", "qty", "qty_open", "eta", "status"])
    df["id"] = df["id"].map(_as_id)
    df["qty"] = pd.to_numeric(df.get("qty", 0), errors="coerce").fillna(0)
    if "qty_open" in df.columns:
        df["qty_open"] = pd.to_numeric(df["qty_open"], errors="coerce").fillna(df["qty"])
    else:
        df["qty_open"] = df["qty"]
    if "eta" in df.columns:
        df["eta"] = pd.to_datetime(df["eta"], errors="coerce")
    else:
        df["eta"] = pd.NaT
    if "status" not in df.columns:
        df["status"] = "open"
    return df


def load_reservations(path: Path | None, column_map: dict[str, str]) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame(columns=["id", "qty", "start", "end"])
    df = _soft_rename(_read_table(path), column_map)
    if "id" not in df.columns or "qty" not in df.columns:
        return pd.DataFrame(columns=["id", "qty", "start", "end"])
    df["id"] = df["id"].map(_as_id)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    df["start"] = pd.to_datetime(df.get("start"), errors="coerce") if "start" in df.columns else pd.NaT
    df["end"] = pd.to_datetime(df.get("end"), errors="coerce") if "end" in df.columns else pd.NaT
    return df


def resolve_data_path(uploads_dir: Path, stem: str) -> Path | None:
    for ext in (".json", ".csv"):
        path = uploads_dir / f"{stem}{ext}"
        if path.exists():
            return path
    return None
