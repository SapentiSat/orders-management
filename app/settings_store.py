from __future__ import annotations

import json
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "schedule": {"weekday": "monday", "hour": 7, "minute": 0, "enabled": False},
    "nexo_connector": {
        "enabled": False,
        "base_url": "http://127.0.0.1:8765",
        "api_token": "",
        "warehouses": [],
        "exclude_types": ["US"],
        "sales_days": 365,
        "aggregate_warehouses": True,
    },
    "mail": {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "from_addr": "",
        "report_recipients": [],
        "alert_recipients": [],
        "report_subject": "Cotygodniowy raport zamówień — {date}",
        "report_body": "<p>Dzień dobry,</p><p>Przesyłamy cotygodniowy raport zamówień.</p>",
        "report_template": "professional",
        "alert_subject": "Orders Management — błąd przetwarzania",
        "alert_body": "Wystąpił błąd podczas generowania raportu. Szczegóły są dostępne w panelu.",
    },
    "panel_users": ["admin"],
    "column_map": {
        "products": {
            "id": "ID_produktu",
            "sku": "SKU",
            "ean": "EAN",
            "name": "Nazwa",
            "producer": "Nazwa_producenta",
            "group": "Grupa_produktu",
            "warehouse": "",
            "active": "Status_produktu",
            "eol": "",
            "stock": "Stan_magazynowy",
            "reserved": "Rezerwacja",
            "available": "Ilosc_dostepna",
            "inbound_qty": "",
            "min_qty": "",
            "moq": "",
            "order_increment": "",
            "lead_time_days": "",
        },
        "sales": {
            "id": "AsortymentAktualnyId",
            "date": "DataSprzedazy",
            "qty": "IloscWJednostceBazowej",
            "net_value": "Wartosc_Netto_PLN",
            "cost": "KosztEwidencyjny",
        },
        "purchase_orders": {
            "id": "",
            "qty": "",
            "qty_open": "",
            "eta": "",
            "status": "",
            "document_symbol": "",
            "supplier": "",
            "warehouse": "",
        },
        "stock_moves": {
            "id": "",
            "date": "",
            "qty": "",
            "move_type": "",
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
        "seasonality_enabled": True,
        "decay_threshold": 0.75,
        "availability_strength": 0.8,
        "order_formula": (
            "daily_demand_adj * (lead_time_days + buffer_days * volatility_factor) "
            "- free_stock - inbound_qty + backlog_qty - reserved_horizon"
        ),
    },
    "stats": {"week_compare_from": ""},
}


def ensure_connector_token(cfg: dict[str, Any]) -> dict[str, Any]:
    nc = cfg.setdefault("nexo_connector", {})
    if not (nc.get("api_token") or "").strip():
        nc["api_token"] = secrets.token_urlsafe(32)
    return cfg


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        data = deepcopy(DEFAULT_SETTINGS)
        ensure_connector_token(data)
        save_settings(path, data)
        return data
    with path.open("r", encoding="utf-8") as f:
        stored = json.load(f)
    merged = deepcopy(DEFAULT_SETTINGS)
    _deep_update(merged, stored)
    ensure_connector_token(merged)
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
