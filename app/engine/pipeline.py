from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.engine.abc_xyz import assign_abc_xyz
from app.engine.excel_export import export_excel
from app.engine.io_data import aggregate_sales, load_products, load_sales
from app.engine.suggest import suggest_orders
from app.licensing import LicenseStatus, effective_max_skus


@dataclass
class PipelineResult:
    ok: bool
    message: str
    excel_path: Path | None
    summary: dict[str, Any]
    preview: list[dict[str, Any]]


def run_pipeline(
    *,
    products_path: Path,
    sales_path: Path,
    settings: dict[str, Any],
    exports_dir: Path,
    license_status: LicenseStatus,
) -> PipelineResult:
    products = load_products(products_path, settings["column_map"]["products"])
    sales = load_sales(sales_path, settings["column_map"]["sales"])

    max_skus = effective_max_skus(license_status)
    if len(products) > max_skus:
        products = products.head(max_skus).copy()
        truncated = True
    else:
        truncated = False

    window = int(settings.get("algorithm", {}).get("sales_window_days", 365))
    sales_agg = aggregate_sales(sales, window)
    merged = products.merge(sales_agg, on="id", how="left")
    for col in ("qty_sum", "net_sum", "cost_sum", "tx_days", "daily_avg_qty", "cv_qty"):
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = merged[col].fillna(0)

    merged = assign_abc_xyz(merged, settings.get("abc_xyz", {}))
    merged = suggest_orders(merged, settings.get("algorithm", {}))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    excel_path = exports_dir / f"zamowienia_{stamp}.xlsx"
    export_excel(merged, excel_path)

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
    }

    preview_cols = [
        "sku",
        "name",
        "ABC_XYZ",
        "mode",
        "suggested_qty",
        "free_stock",
        "lead_time_days",
        "note",
    ]
    preview = (
        merged[preview_cols]
        .head(30)
        .fillna("")
        .to_dict(orient="records")
    )

    msg = "Raport wygenerowany."
    if truncated:
        msg += f" Przycięto do limitu licencji ({max_skus} SKU)."
    return PipelineResult(ok=True, message=msg, excel_path=excel_path, summary=summary, preview=preview)


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
