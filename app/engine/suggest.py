from __future__ import annotations

import math

import pandas as pd


def _ceil_to_increment(qty: float, increment: float, moq: float) -> int:
    if qty <= 0:
        return 0
    inc = max(float(increment or 1), 1.0)
    moq = max(float(moq or 0), 0.0)
    target = max(qty, moq) if moq > 0 else qty
    return int(math.ceil(target / inc) * inc)


def suggest_orders(df: pd.DataFrame, algo: dict) -> pd.DataFrame:
    out = df.copy()
    buffer_days = float(algo.get("buffer_days", 30))
    cover_days = out["lead_time_days"].fillna(0) + buffer_days
    demand = out["daily_avg_qty"].fillna(0) * cover_days
    need = demand - out["free_stock"].fillna(0)
    # dogonić min stock jeśli poniżej
    below_min = out["min_qty"].fillna(0) - out["free_stock"].fillna(0)
    need = need.combine(below_min, max)

    suggested = [
        _ceil_to_increment(n, inc, moq)
        for n, inc, moq in zip(
            need.tolist(),
            out["order_increment"].fillna(1).tolist(),
            out["moq"].fillna(0).tolist(),
        )
    ]
    out["cover_days"] = cover_days
    out["demand_cover"] = demand.round(2)
    out["suggested_qty"] = suggested
    out["suggested_value"] = 0.0
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
        if float(row.get("moq", 0) or 0) < 0:
            missing.append("MOQ")
        if float(row.get("order_increment", 0) or 0) <= 0:
            missing.append("OI")
        if float(row.get("lead_time_days", 0) or 0) <= 0:
            missing.append("LT")
        if missing:
            modes.append("do weryfikacji")
            notes.append("Braki: " + ", ".join(missing))
            continue
        abc = str(row.get("ABC", "C"))
        xyz = str(row.get("XYZ", "Z"))
        tx = int(row.get("tx_days", 0) or 0)
        if abc in auto_abc and xyz in auto_xyz and tx >= min_tx and int(row.get("suggested_qty", 0) or 0) > 0:
            modes.append("auto-ready")
            notes.append("Stabilny ruch, komplet danych")
        elif int(row.get("suggested_qty", 0) or 0) == 0 and tx < min_tx:
            modes.append("skip")
            notes.append("Brak potrzeby / słaby ruch")
        else:
            modes.append("do weryfikacji")
            notes.append("Wymaga decyzji")
    out["mode"] = modes
    out["note"] = notes
    return out
