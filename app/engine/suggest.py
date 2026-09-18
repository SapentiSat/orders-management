from __future__ import annotations

import math
import re

import pandas as pd


_SAFE_FORMULA = re.compile(
    r"^[\d\s\.\+\-\*/\(\)"
    r"abcdefghijklmnopqrstuvwxyz_]+$"
)


def _ceil_to_increment(qty: float, increment: float, moq: float) -> int:
    if qty <= 0:
        return 0
    inc = max(float(increment or 1), 1.0)
    moq = max(float(moq or 0), 0.0)
    target = max(qty, moq) if moq > 0 else qty
    return int(math.ceil(target / inc) * inc)


DEFAULT_FORMULA = (
    "daily_demand_adj * (lead_time_days + buffer_days * volatility_factor) "
    "- free_stock - inbound_qty + backlog_qty - reserved_horizon"
)


def _eval_need(row: pd.Series, formula: str, buffer_days: float) -> float:
    env = {
        "daily_demand_adj": float(row.get("daily_demand_adj", row.get("daily_avg_qty", 0)) or 0),
        "daily_avg_qty": float(row.get("daily_avg_qty", 0) or 0),
        "lead_time_days": float(row.get("lead_time_days", 0) or 0),
        "buffer_days": float(buffer_days),
        "volatility_factor": float(row.get("volatility_factor", 1) or 1),
        "free_stock": float(row.get("free_stock", 0) or 0),
        "inbound_qty": float(row.get("inbound_qty", 0) or 0),
        "backlog_qty": float(row.get("backlog_qty", 0) or 0),
        "reserved_horizon": float(row.get("reserved_horizon", row.get("reserved", 0)) or 0),
        "min_qty": float(row.get("min_qty", 0) or 0),
        "stock": float(row.get("stock", 0) or 0),
        "reserved": float(row.get("reserved", 0) or 0),
        "availability_factor": float(row.get("availability_factor", 1) or 1),
        "demand_decay_factor": float(row.get("demand_decay_factor", 1) or 1),
        "seasonality_factor": float(row.get("seasonality_factor", 1) or 1),
        "max": max,
        "min": min,
        "abs": abs,
    }
    expr = (formula or DEFAULT_FORMULA).strip().lower()
    expr = expr.replace("×", "*").replace("−", "-")
    if not _SAFE_FORMULA.match(expr.replace("max", "").replace("min", "").replace("abs", "")):
        # fallback classic
        return (
            env["daily_demand_adj"] * (env["lead_time_days"] + env["buffer_days"] * env["volatility_factor"])
            - env["free_stock"]
            - env["inbound_qty"]
            + env["backlog_qty"]
            - env["reserved_horizon"]
        )
    try:
        return float(eval(expr, {"__builtins__": {}}, env))  # noqa: S307 — guarded vars only
    except Exception:  # noqa: BLE001
        return (
            env["daily_demand_adj"] * (env["lead_time_days"] + env["buffer_days"] * env["volatility_factor"])
            - env["free_stock"]
            - env["inbound_qty"]
            + env["backlog_qty"]
            - env["reserved_horizon"]
        )


def suggest_orders(df: pd.DataFrame, algo: dict) -> pd.DataFrame:
    out = df.copy()
    buffer_days = float(algo.get("buffer_days", 30))
    formula = algo.get("order_formula") or DEFAULT_FORMULA

    # Ensure coefficient columns exist
    for col, default in (
        ("daily_demand_adj", None),
        ("inbound_qty", 0),
        ("backlog_qty", 0),
        ("reserved_horizon", None),
        ("volatility_factor", 1),
        ("availability_factor", 1),
        ("demand_decay_factor", 1),
        ("seasonality_factor", 1),
    ):
        if col not in out.columns:
            if col == "daily_demand_adj":
                out[col] = out.get("daily_avg_qty", 0).fillna(0)
            elif col == "reserved_horizon":
                out[col] = out.get("reserved", 0).fillna(0)
            else:
                out[col] = default

    cover_days = out["lead_time_days"].fillna(0) + buffer_days * out["volatility_factor"].fillna(1)
    demand = out["daily_demand_adj"].fillna(0) * cover_days

    needs = []
    for _, row in out.iterrows():
        need = _eval_need(row, formula, buffer_days)
        below_min = float(row.get("min_qty", 0) or 0) - float(row.get("free_stock", 0) or 0)
        needs.append(max(need, below_min, 0.0))

    suggested = [
        _ceil_to_increment(n, inc, moq)
        for n, inc, moq in zip(
            needs,
            out["order_increment"].fillna(1).tolist(),
            out["moq"].fillna(0).tolist(),
        )
    ]
    out["cover_days"] = cover_days
    out["demand_cover"] = pd.Series(demand).round(2).values
    out["raw_need"] = [round(n, 2) for n in needs]
    out["suggested_qty"] = suggested
    unit = out["net_sum"] / out["qty_sum"].replace(0, float("nan"))
    unit = unit.fillna(0)
    out["suggested_value"] = (out["suggested_qty"] * unit).round(2)

    auto_abc = set(algo.get("auto_min_abc", ["A", "B"]))
    auto_xyz = set(algo.get("auto_min_xyz", ["X"]))
    min_tx = int(algo.get("auto_min_tx_days", 5))

    modes = []
    notes = []
    for _, row in out.iterrows():
        if (not bool(row.get("active", True))) or bool(row.get("eol", False)):
            modes.append("skip")
            notes.append("Nieaktywny lub EOL")
            continue
        missing = []
        if float(row.get("order_increment", 0) or 0) <= 0:
            missing.append("OI")
        if float(row.get("lead_time_days", 0) or 0) <= 0:
            missing.append("LT")
        if missing:
            modes.append("do weryfikacji")
            notes.append("Braki: " + ", ".join(missing))
            continue

        explain = []
        decay = float(row.get("demand_decay_factor", 1) or 1)
        avail = float(row.get("availability_factor", 1) or 1)
        season = float(row.get("seasonality_factor", 1) or 1)
        inbound = float(row.get("inbound_qty", 0) or 0)
        if decay < 0.95:
            explain.append(f"spadek popytu×{decay:.2f}")
        if avail > 1.05:
            explain.append(f"korekta stockout×{avail:.2f}")
        if abs(season - 1.0) > 0.08:
            explain.append(f"sezon×{season:.2f}")
        if inbound > 0:
            explain.append(f"w drodze {inbound:.0f}")

        abc = str(row.get("ABC", "C"))
        xyz = str(row.get("XYZ", "Z"))
        tx = int(row.get("tx_days", 0) or 0)
        qty = int(row.get("suggested_qty", 0) or 0)
        suffix = ("; " + ", ".join(explain)) if explain else ""

        if abc in auto_abc and xyz in auto_xyz and tx >= min_tx and qty > 0 and decay >= 0.7:
            modes.append("auto-ready")
            notes.append("Stabilny ruch, komplet danych" + suffix)
        elif qty == 0 and (tx < min_tx or decay < 0.55):
            modes.append("skip")
            notes.append(("Rynek stygnie — bez zamówienia" if decay < 0.55 else "Brak potrzeby / słaby ruch") + suffix)
        else:
            modes.append("do weryfikacji")
            notes.append("Wymaga decyzji" + suffix)

    out["mode"] = modes
    out["note"] = notes
    return out
