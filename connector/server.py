"""Nexo Connector — local HTTP API + setup UI."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from connector.config_store import load_config, public_config, save_config
from connector import nexo_sql

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample_data"

app = FastAPI(title="Nexo Connector", version="1.0.0")
_last_export: dict[str, Any] = {}


def _sample_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = Path(meipass) / "sample_data"
            if p.exists():
                return p
    return SAMPLE


def _auth(authorization: str | None = Header(default=None)) -> None:
    cfg = load_config()
    token = (cfg.get("api_token") or "").strip()
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Brak tokenu Authorization: Bearer …")
    if authorization[7:].strip() != token:
        raise HTTPException(403, "Nieprawidłowy token")


class SetupPayload(BaseModel):
    api_token: str = ""
    sql_server: str = ""
    sql_database: str = ""
    sql_user: str = ""
    sql_password: str = ""
    sql_trusted: bool = False
    export_dir: str = ""
    warehouses: list[str] = []
    exclude_types: list[str] = ["US"]
    sales_days: int = 365
    aggregate_warehouses: bool = True
    demo_mode: bool = False


class ScopePayload(BaseModel):
    warehouses: list[str] = []
    exclude_types: list[str] = ["US"]
    sales_days: int = 365
    aggregate_warehouses: bool = True


SETUP_HTML = """<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><title>Nexo Connector — konfiguracja</title>
<style>
body{{font-family:Segoe UI,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;color:#1a1a2e}}
h1{{font-size:22px}} label{{display:block;margin:12px 0 4px;font-weight:600;font-size:13px}}
input,textarea{{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}}
button{{margin-top:16px;padding:10px 20px;background:#1f4e79;color:#fff;border:0;border-radius:6px;cursor:pointer}}
.hint{{font-size:12px;color:#666;margin-top:4px}}
.ok{{background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:16px}}
</style></head><body>
<h1>Nexo Connector — konfiguracja</h1>
<p class="hint">Skopiuj <strong>Token API</strong> z panelu web → Integracje → Nexo Connector.</p>
<form method="post" action="/setup">
<label>Token API</label><input name="api_token" value="{api_token}">
<label>Serwer SQL</label><input name="sql_server" value="{sql_server}" placeholder="localhost\\NEXO">
<label>Baza danych</label><input name="sql_database" value="{sql_database}">
<label><input type="checkbox" name="sql_trusted" value="1" {trusted_checked}> Windows Authentication</label>
<label>Użytkownik SQL</label><input name="sql_user" value="{sql_user}">
<label>Hasło SQL</label><input type="password" name="sql_password" placeholder="(zostaw puste = bez zmiany)">
<label>Folder eksportu JSON</label><input name="export_dir" value="{export_dir}">
<label>Magazyny (symbole, po przecinku — puste = wszystkie)</label><input name="warehouses" value="{warehouses}">
<label>Wyklucz typy asortymentu</label><input name="exclude_types" value="{exclude_types}" placeholder="US">
<label>Okno sprzedaży (dni)</label><input name="sales_days" type="number" value="{sales_days}">
<label><input type="checkbox" name="demo_mode" value="1" {demo_checked}> Tryb demo (sample_data, bez SQL)</label>
<button type="submit">Zapisz</button>
</form>
<p class="hint">API: <a href="/v1/health">/v1/health</a> · Po zapisie uruchom eksport z panelu web.</p>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def root_page():
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/setup">')


@app.get("/setup", response_class=HTMLResponse)
async def setup_form():
    cfg = load_config()
    wh = ",".join(cfg.get("warehouses") or [])
    ex = ",".join(cfg.get("exclude_types") or ["US"])
    html = SETUP_HTML.format(
        api_token=cfg.get("api_token", ""),
        sql_server=cfg.get("sql_server", ""),
        sql_database=cfg.get("sql_database", ""),
        sql_user=cfg.get("sql_user", ""),
        export_dir=cfg.get("export_dir", ""),
        warehouses=wh,
        exclude_types=ex,
        sales_days=cfg.get("sales_days", 365),
        trusted_checked="checked" if cfg.get("sql_trusted") else "",
        demo_checked="checked" if cfg.get("demo_mode") else "",
    )
    return HTMLResponse(html)


@app.post("/setup", response_class=HTMLResponse)
async def setup_save(request: Request):
    form = await request.form()
    cfg = load_config()
    cfg["api_token"] = str(form.get("api_token") or "").strip()
    cfg["sql_server"] = str(form.get("sql_server") or "").strip()
    cfg["sql_database"] = str(form.get("sql_database") or "").strip()
    cfg["sql_user"] = str(form.get("sql_user") or "").strip()
    pwd = str(form.get("sql_password") or "").strip()
    if pwd:
        cfg["sql_password"] = pwd
    cfg["sql_trusted"] = form.get("sql_trusted") == "1"
    cfg["export_dir"] = str(form.get("export_dir") or cfg.get("export_dir") or "").strip()
    wh = str(form.get("warehouses") or "")
    cfg["warehouses"] = [x.strip() for x in wh.split(",") if x.strip()]
    ex = str(form.get("exclude_types") or "US")
    cfg["exclude_types"] = [x.strip() for x in ex.split(",") if x.strip()]
    cfg["sales_days"] = int(form.get("sales_days") or 365)
    cfg["demo_mode"] = form.get("demo_mode") == "1"
    save_config(cfg)
    return HTMLResponse(
        '<p class="ok">Zapisano. <a href="/setup">Wróć do konfiguracji</a></p>',
        status_code=200,
    )


@app.get("/v1/health")
async def health():
    cfg = load_config()
    return {
        "ok": True,
        "demo_mode": bool(cfg.get("demo_mode")),
        "database": cfg.get("sql_database"),
        "last_export": _last_export,
    }


@app.get("/v1/config")
async def get_config(_: None = Depends(_auth)):
    return public_config(load_config())


@app.get("/v1/catalog")
async def catalog(_: None = Depends(_auth)):
    cfg = load_config()
    if cfg.get("demo_mode"):
        return {
            "demo": True,
            "warehouses": [{"symbol": "MAG", "name": "Magazyn główny (demo)"}],
            "product_types": [{"symbol": "TW", "name": "Towar", "has_stock": True}],
            "departments": [],
        }
    try:
        return nexo_sql.fetch_catalog(cfg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Błąd SQL: {exc}") from exc


@app.post("/v1/sync-scope")
async def sync_scope(payload: ScopePayload, _: None = Depends(_auth)):
    cfg = load_config()
    cfg["warehouses"] = payload.warehouses
    cfg["exclude_types"] = payload.exclude_types
    cfg["sales_days"] = payload.sales_days
    cfg["aggregate_warehouses"] = payload.aggregate_warehouses
    save_config(cfg)
    return {"ok": True, "scope": public_config(cfg)}


@app.post("/v1/export")
async def run_export(_: None = Depends(_auth)):
    global _last_export
    cfg = load_config()
    export_dir = Path(cfg.get("export_dir") or "")
    try:
        if cfg.get("demo_mode"):
            stats = nexo_sql.export_demo(export_dir, _sample_dir())
        else:
            stats = nexo_sql.export_all(cfg, export_dir)
        _last_export = {
            **stats,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": True,
        }
        return _last_export
    except Exception as exc:  # noqa: BLE001
        _last_export = {
            "ok": False,
            "error": str(exc)[:500],
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        raise HTTPException(500, str(exc)) from exc


@app.get("/v1/files/{filename}")
async def get_file(filename: str, _: None = Depends(_auth)):
    allowed = {
        "products.json",
        "sales.json",
        "purchase_orders.json",
        "stock_moves.json",
    }
    if filename not in allowed:
        raise HTTPException(404, "Nieznany plik")
    cfg = load_config()
    path = Path(cfg.get("export_dir") or "") / filename
    if not path.exists():
        raise HTTPException(404, "Plik nie istnieje — uruchom eksport")
    return FileResponse(path, media_type="application/json", filename=filename)


def main() -> None:
    import uvicorn

    cfg = load_config()
    host = cfg.get("listen_host") or "0.0.0.0"
    port = int(cfg.get("listen_port") or 8765)
    print(f"Nexo Connector: http://127.0.0.1:{port}/setup")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
