from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _rename(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    rename = {src: dst for dst, src in mapping.items() if src in df.columns}
    out = df.rename(columns=rename)
    missing = [dst for dst in mapping if dst not in out.columns]
    if missing:
        raise ValueError(f"Brak wymaganych kolumn po mapowaniu: {', '.join(missing)}")
    return out


def load_products(path: Path, column_map: dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = _rename(df, column_map)
    df["id"] = df["id"].astype(str)
    for col in ("stock", "reserved", "min_qty", "moq", "order_increment", "lead_time_days"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["active"] = df["active"].astype(str).str.lower().isin(["1", "true", "tak", "yes", "y"])
    df["eol"] = df["eol"].astype(str).str.lower().isin(["1", "true", "tak", "yes", "y"])
    df["free_stock"] = (df["stock"] - df["reserved"]).clip(lower=0)
    return df


def load_sales(path: Path, column_map: dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = _rename(df, column_map)
    df["id"] = df["id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    df["net_value"] = pd.to_numeric(df["net_value"], errors="coerce").fillna(0)
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(0)
    return df


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
