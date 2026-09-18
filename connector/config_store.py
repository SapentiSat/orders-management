"""Local connector configuration (Windows ProgramData or beside executable)."""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "api_token": "",
    "listen_host": "0.0.0.0",
    "listen_port": 8765,
    "export_dir": "",
    "sql_server": "",
    "sql_database": "",
    "sql_user": "",
    "sql_password": "",
    "sql_trusted": False,
    "schema": "ModelDanychContainer",
    "warehouses": [],
    "exclude_types": ["US"],
    "sales_days": 365,
    "aggregate_warehouses": True,
    "demo_mode": False,
}


def config_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "OrdersManagement"
    else:
        base = Path(__file__).resolve().parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return config_dir() / "connector.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        if not cfg["export_dir"]:
            cfg["export_dir"] = str(config_dir() / "export")
        save_config(cfg)
        return cfg
    with path.open("r", encoding="utf-8") as f:
        stored = json.load(f)
    merged = deepcopy(DEFAULT_CONFIG)
    for key, value in stored.items():
        merged[key] = value
    if not merged.get("export_dir"):
        merged["export_dir"] = str(config_dir() / "export")
    return merged


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def public_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in cfg.items() if k != "sql_password"}
    out["sql_password_set"] = bool(cfg.get("sql_password"))
    return out
