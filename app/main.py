from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import PRODUCT_NAME, __version__
from app.config import ensure_dirs, get_settings
from app.engine.io_data import load_sales
from app.engine.pipeline import run_pipeline, week_stats
from app.licensing import LicensePayload, issue_license, verify_license
from app.logging_store import append_log, read_recent_logs
from app.settings_store import load_settings, save_settings

ROOT = Path(__file__).resolve().parent.parent
settings = get_settings()
ensure_dirs(settings)

app = FastAPI(title=PRODUCT_NAME, version=__version__)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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
    return ROOT / "sample_data" / "products.csv", ROOT / "sample_data" / "sales.csv"


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    lic = _license_status()
    app_cfg = _app_settings()
    exports = sorted(settings.exports_dir.glob("zamowienia_*.xlsx"), reverse=True)
    last = exports[0] if exports else None
    summary_path = settings.runtime_dir / "last_run.json"
    last_run = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
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
        },
    )


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
        },
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
    report_recipients: str = Form(""),
    alert_recipients: str = Form(""),
):
    cfg = _app_settings()
    cfg["algorithm"]["buffer_days"] = buffer_days
    cfg["algorithm"]["sales_window_days"] = sales_window_days
    cfg["abc_xyz"]["a_pct"] = a_pct
    cfg["abc_xyz"]["b_pct"] = b_pct
    cfg["abc_xyz"]["x_cv"] = x_cv
    cfg["abc_xyz"]["y_cv"] = y_cv
    cfg["schedule"]["weekday"] = weekday
    cfg["schedule"]["hour"] = hour
    cfg["mail"]["report_recipients"] = [x.strip() for x in report_recipients.split(",") if x.strip()]
    cfg["mail"]["alert_recipients"] = [x.strip() for x in alert_recipients.split(",") if x.strip()]
    save_settings(settings.settings_file, cfg)
    append_log(settings.logs_dir, "INFO", "Zapisano ustawienia")
    return RedirectResponse("/settings?saved=1", status_code=303)


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
    up_p = settings.uploads_dir / "products.csv"
    up_s = settings.uploads_dir / "sales.csv"
    if up_p.exists() and up_s.exists():
        products_path, sales_path = up_p, up_s

    try:
        result = run_pipeline(
            products_path=products_path,
            sales_path=sales_path,
            settings=cfg,
            exports_dir=settings.exports_dir,
            license_status=lic,
        )
        sales_df = load_sales(sales_path, cfg["column_map"]["sales"])
        stats = week_stats(sales_df, cfg.get("stats", {}).get("week_compare_from") or None)
        payload = {
            "message": result.message,
            "summary": result.summary,
            "preview": result.preview,
            "stats": stats,
            "ai_summary": _demo_ai_summary(result.summary, stats),
        }
        (settings.runtime_dir / "last_run.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        append_log(settings.logs_dir, "INFO", "Run OK", result.summary)
    except Exception as exc:  # noqa: BLE001
        append_log(settings.logs_dir, "ERROR", f"Run failed: {exc}")
        (settings.runtime_dir / "last_run.json").write_text(
            json.dumps({"message": f"Błąd: {exc}", "summary": None}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return RedirectResponse("/", status_code=303)


@app.post("/upload")
async def upload_files(request: Request):
    form = await request.form()
    products = form.get("products")
    sales = form.get("sales")
    if products is None or sales is None or not hasattr(products, "file"):
        append_log(settings.logs_dir, "WARN", "Upload bez plików")
        return RedirectResponse("/settings?saved=0", status_code=303)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    with (settings.uploads_dir / "products.csv").open("wb") as f:
        shutil.copyfileobj(products.file, f)
    with (settings.uploads_dir / "sales.csv").open("wb") as f:
        shutil.copyfileobj(sales.file, f)
    append_log(settings.logs_dir, "INFO", "Wgrano pliki products/sales")
    return RedirectResponse("/settings?saved=1", status_code=303)


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


def _demo_ai_summary(summary: dict | None, stats: dict) -> str:
    if not summary:
        return "Brak danych do podsumowania."
    modes = summary.get("modes", {})
    return (
        f"Podsumowanie (warstwa AI — placeholder MVP): "
        f"{modes.get('auto-ready', 0)} SKU auto-ready, "
        f"{modes.get('do weryfikacji', 0)} do weryfikacji, "
        f"{modes.get('skip', 0)} skip. "
        f"Wartość sugestii ~ {summary.get('suggested_value_sum', 0):,.0f}. "
        f"Sprzedaż okna: {stats.get('week_qty', 0):.0f} szt / {stats.get('week_net', 0):,.0f} netto; "
        f"porównanie 30 dni wstecz: {stats.get('prev_month_qty', 0):.0f} szt."
    )


@app.get("/vendor/issue-demo-key")
async def vendor_issue_demo_key():
    if settings.app_env == "production":
        return HTMLResponse("Disabled in production", status_code=403)
    key = issue_license(
        LicensePayload(
            customer="Demo Customer",
            email="demo@example.com",
            edition="trial",
            expires="2027-12-31",
            max_skus=500,
            features=["core", "excel", "abc_xyz", "panel", "ai"],
        ),
        settings.license_signing_secret,
    )
    return {"license_key": key}
