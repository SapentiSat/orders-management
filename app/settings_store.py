from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "schedule": {"weekday": "monday", "hour": 7, "minute": 0, "enabled": False},
    "ftp": {
        "protocol": "sftp",
        "host": "",
        "port": 22,
        "username": "",
        "password": "",
        "products_path": "/export/products.csv",
        "sales_path": "/export/sales.csv",
    },
    "cloud": {"provider": "none", "folder": "OrdersManagement", "retention_weeks": 26},
    "mail": {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "from_addr": "",
        "report_recipients": [],
        "alert_recipients": [],
    },
    "panel_users": ["admin"],
    "column_map": {
        "products": {
            "id": "id",
            "sku": "sku",
            "ean": "ean",
            "name": "nazwa",
            "producer": "producent",
            "group": "grupa",
            "active": "aktywny",
            "eol": "koniec_zycia",
            "stock": "stan",
            "reserved": "rezerwacje",
            "min_qty": "ilosc_min",
            "moq": "moq",
            "order_increment": "order_increment",
            "lead_time_days": "czas_dostawy_dni",
        },
        "sales": {
            "id": "id",
            "date": "data",
            "qty": "ilosc",
            "net_value": "wartosc_netto",
            "cost": "koszt",
        },
    },
    "abc_xyz": {
        "abc_metric": "net_value",
        "a_pct": 80,
        "b_pct": 95,
        "x_cv": 0.5,
        "y_cv": 1.0,
        "window_days": 365,
    },
    "algorithm": {
        "buffer_days": 30,
        "sales_window_days": 365,
        "auto_min_abc": ["A", "B"],
        "auto_min_xyz": ["X"],
        "auto_min_tx_days": 5,
        "seasonality_enabled": False,
    },
    "ai": {"enabled": False, "provider": "none", "model": "", "api_key": ""},
    "stats": {"week_compare_from": ""},
}


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        data = deepcopy(DEFAULT_SETTINGS)
        save_settings(path, data)
        return data
    with path.open("r", encoding="utf-8") as f:
        stored = json.load(f)
    merged = deepcopy(DEFAULT_SETTINGS)
    _deep_update(merged, stored)
    return merged


def save_settings(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _deep_update(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
