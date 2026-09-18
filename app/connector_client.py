from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


FILE_STEMS = ("products", "sales", "purchase_orders", "stock_moves")


def _headers(token: str) -> dict[str, str]:
    h: dict[str, str] = {}
    if token.strip():
        h["Authorization"] = f"Bearer {token.strip()}"
    return h


def check_connector(cfg: dict[str, Any]) -> dict[str, str]:
    from app.integration_monitor import _result

    if not cfg.get("enabled"):
        return _result("disabled", "Nie skonfigurowano")
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        return _result("disabled", "Podaj adres łącznika")
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{base}/v1/health", headers=_headers(cfg.get("api_token", "")))
            r.raise_for_status()
            data = r.json()
        msg = "Połączono"
        if data.get("demo_mode"):
            msg += " (tryb demo)"
        elif data.get("database"):
            msg += f" · baza: {data.get('database')}"
        last = data.get("last_export") or {}
        if last.get("at"):
            msg += f" · ostatni eksport: {last.get('at')[:16]}"
        return _result("active", msg)
    except Exception as exc:  # noqa: BLE001
        return _result("error", str(exc)[:180])


def fetch_from_connector(cfg: dict[str, Any], uploads_dir: Path) -> dict[str, Any]:
    base = (cfg.get("base_url") or "").rstrip("/")
    token = cfg.get("api_token", "")
    if not base:
        raise ValueError("Brak adresu łącznika (base_url)")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    headers = _headers(token)
    saved: dict[str, str] = {}
    with httpx.Client(timeout=300) as client:
        sync_cfg = {
            "warehouses": cfg.get("warehouses") or [],
            "exclude_types": cfg.get("exclude_types") or ["US"],
            "sales_days": int(cfg.get("sales_days") or 365),
            "aggregate_warehouses": bool(cfg.get("aggregate_warehouses", True)),
        }
        try:
            client.post(f"{base}/v1/sync-scope", json=sync_cfg, headers=headers)
        except httpx.HTTPError:
            pass
        exp = client.post(f"{base}/v1/export", headers=headers)
        exp.raise_for_status()
        export_stats = exp.json()
        for stem in FILE_STEMS:
            r = client.get(f"{base}/v1/files/{stem}.json", headers=headers)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            dest = uploads_dir / f"{stem}.json"
            dest.write_bytes(r.content)
            saved[stem] = str(dest)
    return {"saved": saved, "export": export_stats}


def fetch_catalog(cfg: dict[str, Any]) -> dict[str, Any]:
    base = (cfg.get("base_url") or "").rstrip("/")
    token = cfg.get("api_token", "")
    with httpx.Client(timeout=30) as client:
        r = client.get(f"{base}/v1/catalog", headers=_headers(token))
        r.raise_for_status()
        return r.json()
