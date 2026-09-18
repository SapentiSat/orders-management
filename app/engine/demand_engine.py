"""Demand features + coefficients from sales history and optional ZD (purchase orders)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _clamp(series: pd.Series, lo: float, hi: float) -> pd.Series:
    return series.clip(lower=lo, upper=hi)


def enrich_demand(
    products: pd.DataFrame,
    sales: pd.DataFrame,
    *,
    purchase_orders: pd.DataFrame | None = None,
    algo: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Attach demand coefficients and supply signals onto product rows.

    Stany/rezerwacje biorą się z pliku produktów (available lub stock−reserved).
    Opcjonalny plik ZD uzupełnia inbound_qty (suma z otwartych pozycji).
    """
    algo = algo or {}
    out = products.copy()
    ids = out["id"].astype(str)

    out["inbound_qty"] = pd.to_numeric(out.get("inbound_qty", 0), errors="coerce").fillna(0.0)
    # Rezerwacja jest już w free_stock (available lub stan − rezerwacja) — nie odejmuj drugi raz
    out["reserved_horizon"] = 0.0
    out["backlog_qty"] = 0.0
    out["avg_qty_30"] = 0.0
    out["avg_qty_90"] = 0.0
    out["trend_ratio"] = 1.0
    out["stockout_share"] = 0.0
    out["availability_factor"] = 1.0
    out["demand_decay_factor"] = 1.0
    out["seasonality_factor"] = 1.0
    out["volatility_factor"] = 1.0
    out["daily_demand_adj"] = out.get("daily_avg_qty", 0).fillna(0).astype(float)

    if sales is not None and not sales.empty:
        s = sales.copy()
        s["id"] = s["id"].astype(str)
        max_date = s["date"].max()
        w30 = s[s["date"] >= max_date - pd.Timedelta(days=30)]
        w90 = s[s["date"] >= max_date - pd.Timedelta(days=90)]
        a30 = w30.groupby("id")["qty"].sum() / 30.0
        a90 = w90.groupby("id")["qty"].sum() / 90.0
        out["avg_qty_30"] = ids.map(a30).fillna(0.0)
        out["avg_qty_90"] = ids.map(a90).fillna(0.0)
        # prefer longer window as base when short is noisy
        base = out["daily_avg_qty"].fillna(0).astype(float)
        base = np.where(out["avg_qty_90"] > 0, out["avg_qty_90"], base)
        out["daily_demand_base"] = base
        ratio = np.where(out["avg_qty_90"] > 1e-9, out["avg_qty_30"] / out["avg_qty_90"], 1.0)
        out["trend_ratio"] = ratio

        # Seasonality: current calendar month vs average month (same SKU)
        s["month"] = s["date"].dt.month
        cur_month = int(max_date.month)
        by_m = s.groupby(["id", "month"])["qty"].sum().reset_index()
        month_avg = by_m.groupby("id")["qty"].mean()
        cur = by_m[by_m["month"] == cur_month].set_index("id")["qty"]
        season = (ids.map(cur) / ids.map(month_avg).replace(0, np.nan)).fillna(1.0)
        if bool(algo.get("seasonality_enabled", True)):
            out["seasonality_factor"] = _clamp(season, 0.6, 1.6)
        else:
            out["seasonality_factor"] = 1.0
    else:
        out["daily_demand_base"] = out.get("daily_avg_qty", 0).fillna(0).astype(float)

    # Availability: bez osobnego pliku ruchów — domyślnie 1.0 (stockout korekta na później / Przychody)
    out["stockout_share"] = 0.0
    out["availability_factor"] = 1.0

    # Demand decay: krótki okno << długi przy dostępnym stanie
    free = out.get("free_stock", 0).fillna(0).astype(float)
    decay_thr = float(algo.get("decay_threshold", 0.75))
    decay = np.ones(len(out))
    mask = (free > 0) & (out["trend_ratio"] < decay_thr) & (out["avg_qty_90"] > 0)
    decay_vals = np.clip(out.loc[mask, "trend_ratio"] / max(decay_thr, 1e-6), 0.35, 1.0)
    decay[mask.to_numpy()] = decay_vals.to_numpy()
    out["demand_decay_factor"] = decay

    # Volatility z XYZ / CV
    cv = out.get("cv_qty", 0).fillna(0).astype(float)
    xyz = out.get("XYZ", "Y").astype(str)
    vol = np.ones(len(out))
    vol = np.where(xyz == "Z", 1.25, vol)
    vol = np.where(xyz == "Y", 1.1, vol)
    vol = np.where(xyz == "X", 1.0, vol)
    vol = np.where(cv > 1.5, np.maximum(vol, 1.2), vol)
    out["volatility_factor"] = vol

    # W drodze z pliku ZD (nadpisuje/agreguje inbound z produktów)
    if purchase_orders is not None and not purchase_orders.empty:
        po = purchase_orders.copy()
        po["id"] = po["id"].astype(str)
        if "status" in po.columns:
            open_mask = ~po["status"].astype(str).str.lower().isin(
                {"closed", "done", "received", "cancelled", "canceled", "zamknięte", "zrealizowane", "anulowane"}
            )
            po = po[open_mask]
        remaining = po.get("qty_open")
        if remaining is None:
            remaining = po.get("qty", 0)
        po["qty_open"] = pd.to_numeric(remaining, errors="coerce").fillna(0)
        inbound = po.groupby("id")["qty_open"].sum()
        out["inbound_qty"] = ids.map(inbound).fillna(out["inbound_qty"]).astype(float)

    # Rezerwacje: snapshot z produktów (reserved / available z Nexo)
    # Rezerwacja jest już w free_stock (available lub stan − rezerwacja) — nie odejmuj drugi raz
    out["reserved_horizon"] = 0.0

    # Combined adjusted daily demand
    out["daily_demand_adj"] = (
        out["daily_demand_base"].astype(float)
        * out["availability_factor"]
        * out["demand_decay_factor"]
        * out["seasonality_factor"]
    )
    out["daily_demand_adj"] = _clamp(out["daily_demand_adj"], 0.0, 1e9)

    return out
