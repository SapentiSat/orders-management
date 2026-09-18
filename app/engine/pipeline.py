from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.engine.abc_xyz import assign_abc_xyz
from app.engine.demand_engine import enrich_demand
from app.engine.excel_export import export_excel
from app.engine.io_data import (
    aggregate_sales,
    filter_stock_catalog,
    load_products,
    load_purchase_orders,
    load_sales,
    load_stock_moves,
    resolve_data_path,
)
from app.engine.suggest import suggest_orders
from app.licensing import LicenseStatus, effective_max_skus


@dataclass
class PipelineResult:
    ok: bool
    message: str
    excel_path: Path | None
    summary: dict[str, Any]
    preview: list[dict[str, Any]]
    analytics: dict[str, Any]


def build_period_analytics(
    sales: pd.DataFrame,
    products: pd.DataFrame,
    *,
    current_start: pd.Timestamp | None = None,
    current_end: pd.Timestamp | None = None,
) -> dict[str, Any]:
    if sales.empty:
        return {
            "current": {},
            "previous": {},
            "changes": {},
            "top_products": [],
            "daily_sales": [],
        }

    last_date = current_end or sales["date"].max()
    current_start = current_start or (last_date - pd.Timedelta(days=7))
    period_length = max(last_date - current_start, pd.Timedelta(hours=1))
    previous_start = current_start - period_length
    current = sales[(sales["date"] >= current_start) & (sales["date"] <= last_date)]
    previous = sales[(sales["date"] >= previous_start) & (sales["date"] < current_start)]

    def period_stats(frame: pd.DataFrame) -> dict[str, float]:
        return {
            "qty": float(frame["qty"].sum()),
            "net": float(frame["net_value"].sum()),
            "cost": float(frame["cost"].sum()),
            "margin": float((frame["net_value"] - frame["cost"]).sum()),
            "products": int(frame["id"].nunique()),
        }

    current_stats = period_stats(current)
    previous_stats = period_stats(previous)

    def change(key: str) -> float | None:
        old = previous_stats[key]
        return round((current_stats[key] - old) / old * 100, 1) if old else None

    names = products[["id", "sku", "name"]].drop_duplicates("id")
    top = (
        current.groupby("id", as_index=False)
        .agg(qty=("qty", "sum"), net=("net_value", "sum"))
        .merge(names, on="id", how="left")
        .sort_values("qty", ascending=False)
        .head(10)
    )

    chart_start = current_start
    selected = sales[(sales["date"] >= chart_start) & (sales["date"] <= last_date)].copy()
    long_period = (last_date - current_start).days > 62
    selected["bucket"] = (
        selected["date"].dt.to_period("M").dt.to_timestamp()
        if long_period
        else selected["date"].dt.floor("D")
    )
    daily = (
        selected.groupby("bucket", as_index=False)
        .agg(qty=("qty", "sum"), net=("net_value", "sum"))
    )
    return {
        "period": {
            "current": f"{current_start:%Y-%m-%d %H:%M} — {last_date:%Y-%m-%d %H:%M}",
            "previous": f"{previous_start:%Y-%m-%d %H:%M} — {current_start:%Y-%m-%d %H:%M}",
        },
        "current": current_stats,
        "previous": previous_stats,
        "changes": {key: change(key) for key in ("qty", "net", "margin", "products")},
        "top_products": top.fillna("").to_dict(orient="records"),
        "daily_sales": [
            {
                "date": row.bucket.strftime("%m.%Y" if long_period else "%d.%m"),
                "qty": float(row.qty),
                "net": float(row.net),
            }
            for row in daily.itertuples()
        ],
    }


def _anchor_date(sales: pd.DataFrame) -> pd.Timestamp:
    """Dzisiaj; jeśli sample kończy się wcześniej — kotwica = ostatni dzień sprzedaży."""
    today = pd.Timestamp.now().normalize()
    if sales.empty:
        return today
    last = sales["date"].max().normalize()
    return min(today, last)


def build_sales_analytics(sales: pd.DataFrame, products: pd.DataFrame, classified: pd.DataFrame) -> dict[str, Any]:
    anchor = _anchor_date(sales)
    week = build_period_analytics(
        sales,
        products,
        current_start=anchor - pd.Timedelta(days=7),
        current_end=anchor + pd.Timedelta(hours=23, minutes=59),
    )
    month = build_period_analytics(
        sales,
        products,
        current_start=anchor - pd.Timedelta(days=30),
        current_end=anchor + pd.Timedelta(hours=23, minutes=59),
    )
    result = {
        **week,
        "week": week,
        "month": month,
        "anchor_date": str(anchor.date()),
    }
    abc = classified.groupby("ABC", as_index=False).agg(products=("id", "count"), net=("net_sum", "sum"))
    xyz = classified.groupby("XYZ", as_index=False).agg(products=("id", "count"), qty=("qty_sum", "sum"))
    result["abc_distribution"] = abc.to_dict(orient="records")
    result["xyz_distribution"] = xyz.to_dict(orient="records")
    result["order_snapshot"] = {
        "auto_ready": int((classified["mode"] == "auto-ready").sum()) if "mode" in classified.columns else 0,
        "review": int((classified["mode"] == "do weryfikacji").sum()) if "mode" in classified.columns else 0,
        "skip": int((classified["mode"] == "skip").sum()) if "mode" in classified.columns else 0,
        "suggested_value": float(classified["suggested_value"].sum()) if "suggested_value" in classified.columns else 0,
        "suggested_qty": int(classified["suggested_qty"].sum()) if "suggested_qty" in classified.columns else 0,
        "top_order": (
            classified[classified["suggested_qty"] > 0]
            .sort_values("suggested_value", ascending=False)[
                ["sku", "name", "ABC_XYZ", "suggested_qty", "suggested_value"]
            ]
            .head(5)
            .fillna("")
            .to_dict(orient="records")
            if "suggested_qty" in classified.columns
            else []
        ),
    }
    return result


def run_pipeline(
    *,
    products_path: Path,
    sales_path: Path,
    settings: dict[str, Any],
    exports_dir: Path,
    license_status: LicenseStatus,
    uploads_dir: Path | None = None,
) -> PipelineResult:
    cmap = settings.get("column_map", {})
    products = load_products(products_path, cmap.get("products", {}))
    sales = load_sales(sales_path, cmap.get("sales", {}))

    sm_path = resolve_data_path(uploads_dir, "stock_moves") if uploads_dir else None
    stock_moves = load_stock_moves(sm_path, cmap.get("stock_moves", {}))

    exclude_types = settings.get("exclude_product_types") or ["Usługa", "Usluga", "US"]
    products, sales, stock_moves, excluded_products = filter_stock_catalog(
        products, sales, stock_moves if sm_path else None, exclude_types
    )

    po_path = resolve_data_path(uploads_dir, "purchase_orders") if uploads_dir else None
    purchase_orders = load_purchase_orders(po_path, cmap.get("purchase_orders", {}))

    from app.config import get_settings as _get_app_settings

    # sku_limit: 0 = bez limitu, >0 = twardy limit, None = z licencji
    override = _get_app_settings().sku_limit
    if override is None:
        max_skus = effective_max_skus(license_status)
    elif int(override) <= 0:
        max_skus = 10**9
    else:
        max_skus = int(override)
    window = int(settings.get("algorithm", {}).get("sales_window_days", 365))
    sales_agg = aggregate_sales(sales, window)

    truncated = False
    if len(products) > max_skus:
        ranked = products.merge(
            sales_agg[["id", "net_sum", "qty_sum"]],
            on="id",
            how="left",
        )
        ranked["net_sum"] = ranked["net_sum"].fillna(0)
        ranked["qty_sum"] = ranked["qty_sum"].fillna(0)
        ranked = ranked.sort_values(["net_sum", "qty_sum"], ascending=[False, False])
        products = ranked.drop(columns=["net_sum", "qty_sum"]).head(max_skus).copy()
        truncated = True

    merged = products.merge(sales_agg, on="id", how="left")
    for col in ("qty_sum", "net_sum", "cost_sum", "tx_days", "daily_avg_qty", "cv_qty"):
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = merged[col].fillna(0)

    merged = assign_abc_xyz(merged, settings.get("abc_xyz", {}))
    merged = enrich_demand(
        merged,
        sales,
        purchase_orders=purchase_orders,
        algo=settings.get("algorithm", {}),
    )
    merged = suggest_orders(merged, settings.get("algorithm", {}))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    excel_path = exports_dir / f"zamowienia_{stamp}.xlsx"
    analytics = build_sales_analytics(sales, products, merged)
    export_excel(
        merged,
        excel_path,
        analytics,
        sales=sales,
        window_days=window,
    )

    mode_counts = merged["mode"].value_counts().to_dict()
    summary = {
        "rows": int(len(merged)),
        "truncated_to_license": truncated,
        "max_skus": max_skus,
        "modes": {k: int(v) for k, v in mode_counts.items()},
        "suggested_value_sum": float(merged["suggested_value"].sum()),
        "suggested_qty_sum": int(merged["suggested_qty"].sum()),
        "excel": str(excel_path.name),
        "license_mode": license_status.mode,
        "optional_files": {
            "purchase_orders": bool(po_path),
            "stock_moves": bool(sm_path and sm_path.exists()),
        },
        "excluded_product_types": exclude_types,
        "excluded_products_count": excluded_products,
    }

    preview_cols = [
        "sku",
        "name",
        "ABC_XYZ",
        "mode",
        "suggested_qty",
        "free_stock",
        "lead_time_days",
        "availability_factor",
        "demand_decay_factor",
        "seasonality_factor",
        "volatility_factor",
        "note",
    ]
    preview = (
        merged[[c for c in preview_cols if c in merged.columns]]
        .head(30)
        .fillna("")
        .to_dict(orient="records")
    )

    msg = "Raport wygenerowany."
    if truncated:
        msg += f" Przycięto do limitu licencji ({max_skus} SKU)."
    extras = [k for k, v in summary["optional_files"].items() if v]
    if extras:
        msg += " Pliki dodatkowe: " + ", ".join(extras) + "."

    return PipelineResult(
        ok=True,
        message=msg,
        excel_path=excel_path,
        summary=summary,
        preview=preview,
        analytics=analytics,
    )


def week_stats(sales: pd.DataFrame, from_date: str | None = None) -> dict[str, Any]:
    if sales.empty:
        return {"week_qty": 0, "week_net": 0, "prev_month_qty": 0, "prev_month_net": 0}
    max_d = sales["date"].max()
    if from_date:
        start = pd.to_datetime(from_date)
    else:
        start = max_d - pd.Timedelta(days=7)
    week = sales[sales["date"] >= start]
    prev = sales[(sales["date"] < start) & (sales["date"] >= start - pd.Timedelta(days=30))]
    return {
        "from": str(pd.to_datetime(start).date()),
        "to": str(pd.to_datetime(max_d).date()),
        "week_qty": float(week["qty"].sum()),
        "week_net": float(week["net_value"].sum()),
        "prev_month_qty": float(prev["qty"].sum()),
        "prev_month_net": float(prev["net_value"].sum()),
    }
