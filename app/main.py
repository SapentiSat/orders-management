from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import bleach
import pandas as pd
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import PRODUCT_NAME, __version__
from app.config import ensure_dirs, get_settings
from app.engine.io_data import load_products, load_sales, peek_columns, resolve_data_path
from app.engine.pipeline import build_period_analytics, run_pipeline, week_stats
from app.engine.suggest import DEFAULT_FORMULA
from app.field_catalog import FORMULA_VARIABLES, dataset_labels, field_catalog
from app.connector_client import fetch_from_connector
from app.integration_monitor import check_integrations, monitor_loop, read_statuses
from app.licensing import LicensePayload, issue_license, verify_license
from app.logging_store import append_log, log_changes, read_recent_logs
from app.mail_report import send_report_email
from app.settings_store import ensure_connector_token, load_settings, save_settings

ROOT = Path(__file__).resolve().parent.parent
settings = get_settings()
ensure_dirs(settings)

app = FastAPI(title=PRODUCT_NAME, version=__version__)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
integration_status_file = settings.runtime_dir / "integration_status.json"
monitor_task = None


@app.on_event("startup")
async def start_integration_monitor() -> None:
    global monitor_task
    monitor_task = asyncio.create_task(
        monitor_loop(_app_settings, integration_status_file, interval_seconds=3600)
    )


@app.on_event("shutdown")
async def stop_integration_monitor() -> None:
    if monitor_task:
        monitor_task.cancel()


def _license_status():
    key = ""
    if settings.license_file.exists():
        key = settings.license_file.read_text(encoding="utf-8").strip()
    if not key:
        key = settings.license_key
    return verify_license(key, settings.license_signing_secret)


def _app_settings() -> dict:
    return load_settings(settings.settings_file)


def _sample_paths() -> tuple[Path, Path]:
    return ROOT / "sample_data" / "products.json", ROOT / "sample_data" / "sales.json"


def _uploaded_paths() -> tuple[Path | None, Path | None]:
    for ext in (".json", ".csv"):
        products = settings.uploads_dir / f"products{ext}"
        sales = settings.uploads_dir / f"sales{ext}"
        if products.exists() and sales.exists():
            return products, sales
    return None, None


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    lic = _license_status()
    app_cfg = _app_settings()
    exports = sorted(settings.exports_dir.glob("zamowienia_*.xlsx"), reverse=True)
    last = exports[0] if exports else None
    summary_path = settings.runtime_dir / "last_run.json"
    last_run = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    selected_range = request.query_params.get("range", "7d")
    if last_run and last_run.get("analytics"):
        try:
            products_path, sales_path = _sample_paths()
            up_p, up_s = _uploaded_paths()
            if up_p and up_s:
                products_path, sales_path = up_p, up_s
            sales = load_sales(sales_path, app_cfg["column_map"]["sales"])
            products = load_products(products_path, app_cfg["column_map"]["products"])
            end = sales["date"].max()
            ranges = {"day": 1, "7d": 7, "month": 30, "year": 365}
            if selected_range == "custom":
                custom_start = request.query_params.get("start", "")
                custom_end = request.query_params.get("end", "")
                start = pd.to_datetime(custom_start) if custom_start else end - pd.Timedelta(days=7)
                end = pd.to_datetime(custom_end) if custom_end else end
            else:
                start = end - pd.Timedelta(days=ranges.get(selected_range, 7))
            dynamic = build_period_analytics(sales, products, current_start=start, current_end=end)
            dynamic["abc_distribution"] = last_run["analytics"].get("abc_distribution", [])
            dynamic["xyz_distribution"] = last_run["analytics"].get("xyz_distribution", [])
            last_run["analytics"] = dynamic
        except Exception as exc:  # noqa: BLE001
            append_log(settings.logs_dir, "WARN", f"Nie udało się zmienić okresu dashboardu: {exc}")
    logs = read_recent_logs(settings.logs_dir, days=14, levels={"WARN", "ERROR", "INFO"})[:20]
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "license": lic.to_dict(),
            "last_run": last_run,
            "last_excel": last.name if last else None,
            "logs": logs,
            "sample_mode": settings.sample_mode,
            "schedule": app_cfg.get("schedule", {}),
            "integration_statuses": read_statuses(integration_status_file),
            "selected_range": selected_range,
            "custom_start": request.query_params.get("start", ""),
            "custom_end": request.query_params.get("end", ""),
        },
    )


def _source_columns() -> dict:
    """Columns discovered in uploaded files (fallback: sample_data for products/sales)."""
    up_p, up_s = _uploaded_paths()
    sample_p, sample_s = _sample_paths()
    products_path = up_p or sample_p
    sales_path = up_s or sample_s
    optional = {}
    for stem in ("purchase_orders",):
        path = resolve_data_path(settings.uploads_dir, stem)
        optional[stem] = peek_columns(path) if path else []
        optional[f"{stem}_source"] = path.name if path else ""
    return {
        "products": peek_columns(products_path) if products_path else [],
        "sales": peek_columns(sales_path) if sales_path else [],
        "products_source": str(products_path.name) if products_path and products_path.exists() else "",
        "sales_source": str(sales_path.name) if sales_path and sales_path.exists() else "",
        "using_uploads": bool(up_p and up_s),
        **optional,
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "cfg": _app_settings(),
            "license": _license_status().to_dict(),
            "saved": request.query_params.get("saved") == "1",
            "mapping_saved": request.query_params.get("mapping") == "1",
            "uploaded": request.query_params.get("uploaded") == "1",
            "fields": field_catalog(),
            "dataset_labels": dataset_labels(),
            "formula_variables": FORMULA_VARIABLES,
            "default_formula": DEFAULT_FORMULA,
            "source_columns": _source_columns(),
        },
    )


def _last_run() -> dict | None:
    summary_path = settings.runtime_dir / "last_run.json"
    return json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    exports = sorted(settings.exports_dir.glob("zamowienia_*.xlsx"), reverse=True)
    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "last_run": _last_run(),
            "exports": [item.name for item in exports[:20]],
        },
    )


@app.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request):
    cfg = ensure_connector_token(_app_settings())
    save_settings(settings.settings_file, cfg)
    return templates.TemplateResponse(
        "integrations.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "cfg": cfg,
            "statuses": read_statuses(integration_status_file),
            "saved": request.query_params.get("saved") == "1",
            "checked": request.query_params.get("checked") == "1",
            "fetched": request.query_params.get("fetched") == "1",
            "fetch_error": request.query_params.get("fetch_error", ""),
        },
    )


@app.get("/downloads/nexo-connector")
async def download_nexo_connector():
    """Pobierz łącznik Nexo (EXE lub paczka ZIP)."""
    exe = ROOT / "connector" / "dist" / "NexoConnector.exe"
    if exe.exists():
        return FileResponse(
            exe,
            media_type="application/octet-stream",
            filename="NexoConnector.exe",
        )
    zip_path = ROOT / "connector" / "dist" / "NexoConnector.zip"
    if zip_path.exists():
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="NexoConnector.zip",
        )
    # Fallback: paczka źródeł + skrypt uruchomienia
    launcher = ROOT / "connector" / "run-connector.bat"
    if not launcher.exists():
        launcher.write_text(
            "@echo off\r\n"
            "cd /d %~dp0\r\n"
            "python -m pip install -q -r requirements.txt\r\n"
            "python -m connector.server\r\n",
            encoding="utf-8",
        )
    import io
    import zipfile

    from fastapi.responses import StreamingResponse

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        pack = [
            ("URUCHOM.bat", ROOT / "connector" / "URUCHOM.bat"),
            ("connector/__init__.py", ROOT / "connector" / "__init__.py"),
            ("connector/__main__.py", ROOT / "connector" / "__main__.py"),
            ("connector/server.py", ROOT / "connector" / "server.py"),
            ("connector/config_store.py", ROOT / "connector" / "config_store.py"),
            ("connector/nexo_sql.py", ROOT / "connector" / "nexo_sql.py"),
            ("connector/requirements.txt", ROOT / "connector" / "requirements.txt"),
            ("connector/README.md", ROOT / "connector" / "README.md"),
        ]
        for arc, path in pack:
            if path.exists():
                zf.write(path, arc)
        sample = ROOT / "sample_data"
        if sample.exists():
            for name in ("products.json", "sales.json", "purchase_orders.json", "stock_moves.json"):
                p = sample / name
                if p.exists():
                    zf.write(p, f"sample_data/{name}")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="NexoConnector.zip"'},
    )


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "license": _license_status().to_dict(),
            "cfg": _app_settings(),
        },
    )


@app.get("/docs", response_class=HTMLResponse)
async def docs_page(request: Request):
    return templates.TemplateResponse(
        "docs.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    level = request.query_params.get("level", "all")
    category = request.query_params.get("category", "all")
    levels = None if level == "all" else {level.upper()}
    cat = None if category == "all" else category
    logs = read_recent_logs(
        settings.logs_dir,
        days=30,
        levels=levels or {"INFO", "WARN", "ERROR", "CHANGE"},
        category=cat,
        limit=1000,
    )
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "logs": logs,
            "selected_level": level,
            "selected_category": category,
            "counts": {
                "all": len(read_recent_logs(settings.logs_dir, days=30, limit=1000)),
                "change": len(read_recent_logs(settings.logs_dir, days=30, category="change", limit=1000)),
                "error": len(
                    read_recent_logs(settings.logs_dir, days=30, levels={"ERROR"}, limit=1000)
                ),
            },
        },
    )


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    cfg = _app_settings()
    body = cfg["mail"].get("report_body", "")
    if "<" not in body and "\n" in body:
        body = "".join(f"<p>{line}</p>" for line in body.splitlines() if line.strip())
    cfg["mail"]["report_body"] = _sanitize_email_html(body)
    return templates.TemplateResponse(
        "notifications.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "cfg": cfg,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@app.post("/notifications/save")
async def notifications_save(
    from_addr: str = Form(""),
    report_recipients: str = Form(""),
    alert_recipients: str = Form(""),
    report_subject: str = Form(""),
    report_body: str = Form(""),
    report_template: str = Form("professional"),
    alert_subject: str = Form(""),
    alert_body: str = Form(""),
):
    before = _app_settings()
    cfg = deepcopy(before)
    cfg["mail"].update(
        {
            "from_addr": from_addr,
            "report_recipients": [x.strip() for x in report_recipients.split(",") if x.strip()],
            "alert_recipients": [x.strip() for x in alert_recipients.split(",") if x.strip()],
            "report_subject": report_subject,
            "report_body": _sanitize_email_html(report_body),
            "report_template": report_template,
            "alert_subject": alert_subject,
            "alert_body": alert_body,
        }
    )
    save_settings(settings.settings_file, cfg)
    log_changes(settings.logs_dir, area="powiadomienia", before=before, after=cfg)
    return RedirectResponse("/notifications?saved=1", status_code=303)


def _sanitize_email_html(value: str) -> str:
    return bleach.clean(
        value,
        tags={
            "p",
            "br",
            "strong",
            "b",
            "em",
            "i",
            "u",
            "ul",
            "ol",
            "li",
            "a",
            "h1",
            "h2",
            "h3",
            "blockquote",
        },
        attributes={"a": ["href", "target", "rel"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )


@app.post("/settings/save")
async def settings_save(
    buffer_days: int = Form(30),
    sales_window_days: int = Form(365),
    a_pct: float = Form(80),
    b_pct: float = Form(95),
    x_cv: float = Form(0.5),
    y_cv: float = Form(1.0),
    weekday: str = Form("monday"),
    hour: int = Form(7),
    seasonality_enabled: str | None = Form(None),
    decay_threshold: float = Form(0.75),
    availability_strength: float = Form(0.8),
    order_formula: str = Form(""),
):
    before = _app_settings()
    cfg = deepcopy(before)
    cfg["algorithm"]["buffer_days"] = buffer_days
    cfg["algorithm"]["sales_window_days"] = sales_window_days
    cfg["algorithm"]["seasonality_enabled"] = seasonality_enabled == "on"
    cfg["algorithm"]["decay_threshold"] = decay_threshold
    cfg["algorithm"]["availability_strength"] = availability_strength
    if order_formula.strip():
        cfg["algorithm"]["order_formula"] = order_formula.strip()
    cfg["abc_xyz"]["a_pct"] = a_pct
    cfg["abc_xyz"]["b_pct"] = b_pct
    cfg["abc_xyz"]["x_cv"] = x_cv
    cfg["abc_xyz"]["y_cv"] = y_cv
    cfg["schedule"]["weekday"] = weekday
    cfg["schedule"]["hour"] = hour
    save_settings(settings.settings_file, cfg)
    log_changes(settings.logs_dir, area="reguly_i_dane", before=before, after=cfg)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/mapping")
async def settings_mapping_save(request: Request):
    form = await request.form()
    before = _app_settings()
    cfg = deepcopy(before)
    catalog = field_catalog()
    missing: list[str] = []
    for dataset, fields in catalog.items():
        mapped: dict[str, str] = {}
        for field in fields:
            key = field["key"]
            mapped[key] = str(form.get(f"{dataset}__{key}", "") or "").strip()
            if field["required"] and dataset in {"products", "sales"} and not mapped[key]:
                missing.append(f"{dataset}:{field['label']}")
        cfg["column_map"][dataset] = mapped
    if missing:
        append_log(
            settings.logs_dir,
            "WARN",
            "Mapowanie niekompletne",
            {"missing": missing},
            category="change",
        )
        return RedirectResponse("/settings#mapping", status_code=303)
    save_settings(settings.settings_file, cfg)
    log_changes(settings.logs_dir, area="mapowanie", before=before, after=cfg)
    return RedirectResponse("/settings?mapping=1#mapping", status_code=303)


@app.post("/integrations/save")
async def integrations_save(
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    nexo_enabled: str | None = Form(None),
    nexo_base_url: str = Form("http://127.0.0.1:8765"),
    nexo_api_token: str = Form(""),
    nexo_warehouses: str = Form(""),
    nexo_exclude_types: str = Form("US"),
    nexo_sales_days: int = Form(365),
    nexo_aggregate: str | None = Form(None),
):
    before = _app_settings()
    cfg = deepcopy(before)
    cfg["mail"].update(
        {
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
        }
    )
    if smtp_password:
        cfg["mail"]["smtp_password"] = smtp_password
    wh = [x.strip() for x in (nexo_warehouses or "").split(",") if x.strip()]
    ex = [x.strip() for x in (nexo_exclude_types or "US").split(",") if x.strip()]
    nc = cfg.setdefault("nexo_connector", {})
    nc.update(
        {
            "enabled": nexo_enabled == "on",
            "base_url": nexo_base_url.strip(),
            "warehouses": wh,
            "exclude_types": ex or ["US"],
            "sales_days": max(30, min(nexo_sales_days, 730)),
            "aggregate_warehouses": nexo_aggregate == "on",
        }
    )
    if nexo_api_token.strip():
        nc["api_token"] = nexo_api_token.strip()
    ensure_connector_token(cfg)
    save_settings(settings.settings_file, cfg)
    log_changes(settings.logs_dir, area="integracje", before=before, after=cfg)
    return RedirectResponse("/integrations?saved=1", status_code=303)


@app.post("/integrations/check")
async def integrations_check():
    await asyncio.to_thread(
        check_integrations,
        _app_settings(),
        integration_status_file,
    )
    append_log(
        settings.logs_dir,
        "INFO",
        "Sprawdzono stan integracji",
        category="integration",
    )
    return RedirectResponse("/integrations?checked=1", status_code=303)


@app.post("/integrations/nexo/fetch")
async def integrations_nexo_fetch():
    cfg = _app_settings()
    nc = cfg.get("nexo_connector", {})
    try:
        result = await asyncio.to_thread(
            fetch_from_connector,
            nc,
            settings.uploads_dir,
        )
        append_log(
            settings.logs_dir,
            "INFO",
            "Pobrano dane z łącznika Nexo",
            result,
            category="integration",
        )
        return RedirectResponse("/integrations?fetched=1#nexo", status_code=303)
    except Exception as exc:  # noqa: BLE001
        append_log(settings.logs_dir, "ERROR", f"Łącznik Nexo: {exc}", category="integration")
        return RedirectResponse(
            f"/integrations?fetch_error={quote(str(exc)[:200])}#nexo",
            status_code=303,
        )


@app.post("/integrations/nexo/regenerate-token")
async def integrations_nexo_regenerate_token():
    before = _app_settings()
    cfg = deepcopy(before)
    cfg.setdefault("nexo_connector", {})["api_token"] = secrets.token_urlsafe(32)
    save_settings(settings.settings_file, cfg)
    log_changes(settings.logs_dir, area="nexo_connector_token", before=before, after=cfg)
    return RedirectResponse("/integrations?saved=1#nexo", status_code=303)


def _license_history_path() -> Path:
    return settings.runtime_dir / "issued_licenses.json"


def _load_license_history() -> list[dict]:
    path = _license_history_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _admin_session_token() -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        b"om-vendor-admin-session-v1",
        hashlib.sha256,
    ).hexdigest()


def _is_vendor_admin(request: Request) -> bool:
    cookie = request.cookies.get("om_vendor_admin", "")
    if not cookie or not settings.admin_password:
        return False
    return hmac.compare_digest(cookie, _admin_session_token())


def _require_vendor_admin(request: Request) -> RedirectResponse | None:
    if _is_vendor_admin(request):
        return None
    return RedirectResponse("/admin/login", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if _is_vendor_admin(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        "admin_login.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "error": request.query_params.get("error"),
        },
    )


@app.post("/admin/login")
async def admin_login(password: str = Form("")):
    expected = settings.admin_password or ""
    if not expected or not hmac.compare_digest(password.strip(), expected):
        append_log(settings.logs_dir, "WARN", "Nieudane logowanie do panelu vendora", category="change")
        return RedirectResponse("/admin/login?error=Błędne%20hasło", status_code=303)
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        "om_vendor_admin",
        _admin_session_token(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    append_log(settings.logs_dir, "INFO", "Zalogowano do panelu vendora", category="change")
    return response


@app.post("/admin/logout")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie("om_vendor_admin")
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    gate = _require_vendor_admin(request)
    if gate:
        return gate
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "history": _load_license_history()[:200],
            "issued_key": request.query_params.get("key"),
            "issued_meta": {
                "customer": request.query_params.get("customer", ""),
                "edition": request.query_params.get("edition", ""),
                "expires": request.query_params.get("expires", ""),
                "max_skus": request.query_params.get("max_skus", ""),
            },
            "error": request.query_params.get("error"),
        },
    )


@app.post("/admin/issue")
async def admin_issue(
    request: Request,
    customer: str = Form(...),
    email: str = Form(""),
    edition: str = Form("standard"),
    max_skus: int = Form(5000),
    expires: str = Form(""),
):
    gate = _require_vendor_admin(request)
    if gate:
        return gate
    if settings.app_env == "production" and not settings.license_signing_secret:
        return RedirectResponse("/admin?error=Brak%20LICENSE_SIGNING_SECRET", status_code=303)
    customer = customer.strip()
    if not customer:
        return RedirectResponse("/admin?error=Podaj%20nazwę%20klienta", status_code=303)
    expires = expires.strip()
    key = issue_license(
        LicensePayload(
            customer=customer,
            email=email.strip(),
            edition=edition,
            expires=expires,
            max_skus=max(50, int(max_skus)),
        ),
        settings.license_signing_secret,
    )
    history = _load_license_history()
    history.insert(
        0,
        {
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "customer": customer,
            "email": email.strip(),
            "edition": edition,
            "expires": expires,
            "max_skus": max_skus,
            "key": key,
            "key_preview": key[:18] + "…",
        },
    )
    _license_history_path().write_text(json.dumps(history[:200], ensure_ascii=False, indent=2), encoding="utf-8")
    append_log(
        settings.logs_dir,
        "CHANGE",
        f"Wystawiono licencję dla {customer}",
        {"edition": edition, "expires": expires or "bezterminowo", "max_skus": max_skus},
        category="change",
    )
    return RedirectResponse(
        "/admin?key="
        + quote(key)
        + f"&customer={quote(customer)}&edition={quote(edition)}&expires={quote(expires)}&max_skus={max_skus}",
        status_code=303,
    )


@app.get("/license", response_class=HTMLResponse)
async def license_page(request: Request):
    return templates.TemplateResponse(
        "license.html",
        {
            "request": request,
            "product": PRODUCT_NAME,
            "version": __version__,
            "license": _license_status().to_dict(),
            "error": request.query_params.get("error"),
            "ok": request.query_params.get("ok") == "1",
        },
    )


@app.post("/license/activate")
async def license_activate(license_key: str = Form("")):
    status = verify_license(license_key, settings.license_signing_secret)
    if not status.valid:
        append_log(settings.logs_dir, "WARN", "Nieudana aktywacja licencji", {"reason": status.reason})
        return RedirectResponse(f"/license?error={status.reason}", status_code=303)
    settings.license_file.write_text(license_key.strip(), encoding="utf-8")
    append_log(
        settings.logs_dir,
        "INFO",
        "Aktywowano licencję",
        {"customer": status.payload.customer if status.payload else ""},
    )
    return RedirectResponse("/license?ok=1", status_code=303)


@app.post("/run")
async def run_now():
    lic = _license_status()
    cfg = _app_settings()
    products_path, sales_path = _sample_paths()
    up_p, up_s = _uploaded_paths()
    if up_p and up_s:
        products_path, sales_path = up_p, up_s

    try:
        result = run_pipeline(
            products_path=products_path,
            sales_path=sales_path,
            settings=cfg,
            exports_dir=settings.exports_dir,
            license_status=lic,
            uploads_dir=settings.uploads_dir,
        )
        sales_df = load_sales(sales_path, cfg["column_map"]["sales"])
        stats = week_stats(sales_df, cfg.get("stats", {}).get("week_compare_from") or None)
        payload = {
            "message": result.message,
            "summary": result.summary,
            "preview": result.preview,
            "stats": stats,
            "analytics": result.analytics,
        }
        (settings.runtime_dir / "last_run.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        append_log(settings.logs_dir, "INFO", "Run OK", result.summary)
        try:
            mail_result = send_report_email(
                cfg.get("mail") or {},
                excel_path=result.excel_path,
                summary=result.summary,
            )
            append_log(settings.logs_dir, "INFO", "Mail wysłany", mail_result)
            payload["mail"] = mail_result
            (settings.runtime_dir / "last_run.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as mail_exc:  # noqa: BLE001
            append_log(settings.logs_dir, "ERROR", f"Mail failed: {mail_exc}")
            payload["mail_error"] = str(mail_exc)
            (settings.runtime_dir / "last_run.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:  # noqa: BLE001
        append_log(settings.logs_dir, "ERROR", f"Run failed: {exc}")
        (settings.runtime_dir / "last_run.json").write_text(
            json.dumps({"message": f"Błąd: {exc}", "summary": None}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return RedirectResponse("/", status_code=303)


@app.post("/notifications/send-test")
async def notifications_send_test():
    """Wyślij raport e-mail wg bieżących ustawień (ostatni Excel + last_run)."""
    cfg = _app_settings()
    last = _last_run() or {}
    excel_name = (last.get("summary") or {}).get("excel")
    excel_path = settings.exports_dir / excel_name if excel_name else None
    if not excel_path or not excel_path.exists():
        exports = sorted(settings.exports_dir.glob("zamowienia_*.xlsx"), reverse=True)
        excel_path = exports[0] if exports else None
    if not excel_path:
        append_log(settings.logs_dir, "ERROR", "Mail: brak pliku Excel do wysyłki")
        return RedirectResponse("/notifications?mail=0", status_code=303)
    try:
        mail_result = send_report_email(
            cfg.get("mail") or {},
            excel_path=excel_path,
            summary=last.get("summary"),
        )
        append_log(settings.logs_dir, "INFO", "Mail wysłany (ręcznie)", mail_result)
        return RedirectResponse("/notifications?mail=1", status_code=303)
    except Exception as exc:  # noqa: BLE001
        append_log(settings.logs_dir, "ERROR", f"Mail failed: {exc}")
        return RedirectResponse("/notifications?mail=0", status_code=303)


@app.post("/upload")
async def upload_files(request: Request):
    form = await request.form()
    products = form.get("products")
    sales = form.get("sales")
    if products is None or sales is None or not hasattr(products, "file"):
        append_log(settings.logs_dir, "WARN", "Upload bez plików")
        return RedirectResponse("/settings?saved=0", status_code=303)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _ext(upload, default: str = ".json") -> str:
        name = getattr(upload, "filename", "") or ""
        suffix = Path(name).suffix.lower()
        return suffix if suffix in {".json", ".csv"} else default

    def _save(stem: str, upload) -> str | None:
        if upload is None or not hasattr(upload, "file"):
            return None
        filename = getattr(upload, "filename", "") or ""
        if not filename:
            return None
        for old in settings.uploads_dir.glob(f"{stem}.*"):
            old.unlink(missing_ok=True)
        name = f"{stem}{_ext(upload)}"
        with (settings.uploads_dir / name).open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        return name

    products_name = _save("products", products)
    sales_name = _save("sales", sales)
    saved = {
        "products": products_name,
        "sales": sales_name,
        "purchase_orders": _save("purchase_orders", form.get("purchase_orders")),
    }
    append_log(
        settings.logs_dir,
        "CHANGE",
        "Wgrano pliki danych",
        {k: v for k, v in saved.items() if v},
        category="change",
    )
    return RedirectResponse("/settings?uploaded=1#mapping", status_code=303)


@app.get("/exports/{name}")
async def download_export(name: str):
    path = settings.exports_dir / name
    if not path.exists() or not name.startswith("zamowienia_"):
        return HTMLResponse("Nie znaleziono", status_code=404)
    return FileResponse(path, filename=name)


@app.get("/api/health")
async def health():
    lic = _license_status()
    return {"ok": True, "version": __version__, "license_mode": lic.mode, "license_valid": lic.valid}


@app.get("/vendor/issue-demo-key")
async def vendor_issue_demo_key(request: Request):
    if settings.app_env == "production":
        return HTMLResponse("Disabled in production", status_code=403)
    gate = _require_vendor_admin(request)
    if gate:
        return gate
    key = issue_license(
        LicensePayload(
            customer="Demo Customer",
            email="demo@example.com",
            edition="trial",
            expires="2027-12-31",
            max_skus=500,
            features=["core", "excel", "abc_xyz", "panel"],
        ),
        settings.license_signing_secret,
    )
    return {"license_key": key}
