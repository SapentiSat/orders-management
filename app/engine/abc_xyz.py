from __future__ import annotations

import pandas as pd


def assign_abc_xyz(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    metric = cfg.get("abc_metric", "net_value")
    col = "net_sum" if metric == "net_value" else "qty_sum"
    if col not in out.columns:
        out["ABC"] = "C"
        out["XYZ"] = "Z"
        return out

    vals = out[col].fillna(0).clip(lower=0)
    total = vals.sum()
    if total <= 0:
        out["ABC"] = "C"
    else:
        ranked = out.assign(_v=vals).sort_values("_v", ascending=False)
        ranked["_cum_pct"] = ranked["_v"].cumsum() / total * 100
        a_pct = float(cfg.get("a_pct", 80))
        b_pct = float(cfg.get("b_pct", 95))

        def abc_label(cum: float) -> str:
            if cum <= a_pct:
                return "A"
            if cum <= b_pct:
                return "B"
            return "C"

        ranked["ABC"] = ranked["_cum_pct"].map(abc_label)
        out = out.drop(columns=["ABC"], errors="ignore").merge(
            ranked[["id", "ABC"]], on="id", how="left"
        )

    x_cv = float(cfg.get("x_cv", 0.5))
    y_cv = float(cfg.get("y_cv", 1.0))
    cv = out.get("cv_qty", pd.Series([999.0] * len(out))).fillna(999.0)

    def xyz_label(v: float) -> str:
        if v <= x_cv:
            return "X"
        if v <= y_cv:
            return "Y"
        return "Z"

    out["XYZ"] = cv.map(xyz_label)
    out["ABC_XYZ"] = out["ABC"].astype(str) + out["XYZ"].astype(str)
    return out
