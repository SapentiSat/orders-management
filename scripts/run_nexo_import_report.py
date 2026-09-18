#!/usr/bin/env python3
"""Import danych z folderu Nexo, raport ABC/XYZ, mail, HTML przykładu kalkulacji."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import ensure_dirs, get_settings
from app.engine.pipeline import run_pipeline
from app.engine.suggest import DEFAULT_FORMULA
from app.licensing import LicensePayload, LicenseStatus
from app.mail_report import send_report_email
from app.settings_store import load_settings

SOURCE = ROOT / "DANE POBRANE Z BAZY"
MAIL_TO = ["valiantsin12@gmail.com"]


def _copy_data(uploads: Path) -> dict[str, int]:
    mapping = {
        "products.json": SOURCE / "AsortymentyMasterData.json",
        "sales.json": SOURCE / "Pozycji_z_dokumentow.json",
        "stock_moves.json": SOURCE / "RuchMagazynowy.json",
    }
    counts: dict[str, int] = {}
    for dst_name, src in mapping.items():
        if not src.exists():
            raise FileNotFoundError(f"Brak pliku: {src}")
        dst = uploads / dst_name
        shutil.copy2(src, dst)
        data = json.loads(dst.read_text(encoding="utf-8"))
        counts[dst_name] = len(data) if isinstance(data, list) else 0
    return counts


def _pick_example_row(merged) -> dict:
    candidates = merged[
        (merged["suggested_qty"] > 0)
        & (merged["qty_sum"] > 0)
        & (merged["ABC"].isin(["A", "B"]))
        & (~merged.get("product_type", "").astype(str).str.lower().str.contains("usl", na=False))
    ].sort_values("suggested_value", ascending=False)
    if candidates.empty:
        candidates = merged[merged["qty_sum"] > 0].sort_values("net_sum", ascending=False)
    row = candidates.iloc[0]
    return row.to_dict()


def _build_calc_html(row: dict, algo: dict, report_date: str) -> str:
    """HTML z prostym opisem krok po kroku — dla osoby bez doświadczenia."""
    import math

    buffer_days = float(algo.get("buffer_days", 31))
    window_days = int(algo.get("sales_window_days", 365))
    lt = float(row.get("lead_time_days") or 30)
    vol = float(row.get("volatility_factor") or 1)
    cover = lt + buffer_days * vol

    base = float(row.get("daily_demand_base") or row.get("avg_qty_90") or row.get("daily_avg_qty") or 0)
    avg30 = float(row.get("avg_qty_30") or 0)
    avg90 = float(row.get("avg_qty_90") or 0)
    avail = float(row.get("availability_factor") or 1)
    decay = float(row.get("demand_decay_factor") or 1)
    season = float(row.get("seasonality_factor") or 1)
    dda = float(row.get("daily_demand_adj") or 0)

    qty_sum = float(row.get("qty_sum") or 0)
    net_sum = float(row.get("net_sum") or 0)
    tx_days = int(row.get("tx_days") or 0)
    free = float(row.get("free_stock") or 0)
    inbound = float(row.get("inbound_qty") or 0)
    reserved_h = float(row.get("reserved_horizon") or 0)
    backlog = float(row.get("backlog_qty") or 0)
    min_qty = float(row.get("min_qty") or 0)
    moq = float(row.get("moq") or 0)
    inc = max(float(row.get("order_increment") or 1), 1)
    trend = float(row.get("trend_ratio") or 1)

    demand_cover = dda * cover
    raw_formula = (
        dda * cover - free - inbound + backlog - reserved_h
    )
    below_min = max(min_qty - free, 0)
    raw_need = max(raw_formula, below_min, 0)
    sug = int(row.get("suggested_qty") or 0)
    unit = (net_sum / qty_sum) if qty_sum > 0 else 0
    sug_value = float(row.get("suggested_value") or sug * unit)

    def fnum(v, d=2):
        try:
            return f"{float(v):,.{d}f}".replace(",", " ")
        except (TypeError, ValueError):
            return str(v)

    def factor_line(label: str, value: float, ok_text: str, change_text: str) -> str:
        if abs(value - 1.0) < 0.02:
            return f"<li><strong>{label} = {fnum(value, 2)}</strong> — {ok_text}</li>"
        return f"<li><strong>{label} = {fnum(value, 2)}</strong> — {change_text}</li>"

    # Wyjaśnienia korekt w prostym języku
    if avail > 1.02:
        avail_expl = f"Podbijamy tempo, bo w historii brakowało towaru (stockout)."
    else:
        avail_expl = "Bez korekty — nie wykryto braków magazynowych w historii."

    if decay < 0.98 and free > 0:
        decay_expl = (
            f"Obniżamy tempo, bo ostatnie 30 dni ({fnum(avg30, 3)} szt./dzień) "
            f"jest słabsze niż 90 dni ({fnum(avg90, 3)} szt./dzień) przy stanie > 0."
        )
    elif free <= 0:
        decay_expl = "Bez obniżki — produkt ma stan 0, więc nie zakładamy „stygnięcia rynku”."
    else:
        decay_expl = "Bez obniżki — sprzedaż nie spada istotnie w krótkim oknie."

    if abs(season - 1.0) > 0.05:
        season_expl = f"Miesiąc {report_date[5:7]} historycznie odbiega od średniej rocznej."
    else:
        season_expl = "Bieżący miesiąc jest blisko średniej — bez korekty sezonowej."

    xyz = str(row.get("XYZ") or "Y")
    vol_labels = {"X": "stabilna (×1,0)", "Y": "umiarkowana (×1,1)", "Z": "nieregularna (×1,25)"}
    vol_expl = vol_labels.get(xyz, f"×{fnum(vol, 2)}")

    moq_note = ""
    if sug > 0 and raw_need > 0 and sug != math.ceil(raw_need):
        moq_note = (
            f"<p class='hint'>Zaokrąglenie: surowa potrzeba {fnum(raw_need, 1)} szt. "
            f"→ zaokrąglamy do kroku {fnum(inc, 0)} szt."
            + (f" i minimum MOQ {fnum(moq, 0)} szt." if moq > 0 else "")
            + f" → <strong>{sug} szt.</strong></p>"
        )
    elif sug == math.ceil(raw_need) and raw_need != int(raw_need):
        moq_note = (
            f"<p class='hint'>Zaokrąglenie w górę: {fnum(raw_need, 1)} szt. → "
            f"<strong>{sug} szt.</strong> (pełne sztuki / krok zamówienia).</p>"
        )

    sku = row.get("sku", "")
    name = row.get("name", "")

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>Jak liczymy zamówienie — {sku}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; background:#eef1f6; margin:0; padding:20px; color:#1a2332; line-height:1.55; }}
    .wrap {{ max-width:780px; margin:0 auto; }}
    header {{ background:#172033; color:#fff; padding:22px 26px; border-radius:12px 12px 0 0; }}
    header h1 {{ margin:0 0 8px; font-size:22px; }}
    header p {{ margin:0; opacity:.9; font-size:14px; }}
    .card {{ background:#fff; padding:22px 26px; margin-bottom:14px; border-radius:10px; box-shadow:0 1px 8px rgba(0,0,0,.05); }}
    .card h2 {{ margin:0 0 12px; font-size:16px; color:#1F4E79; border-bottom:2px solid #e8ecf2; padding-bottom:8px; }}
    .card p, .card li {{ font-size:14px; margin:8px 0; }}
    .goal {{ background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; padding:16px 20px; margin:14px 0; font-size:15px; }}
    .math {{ background:#f8faff; border-left:4px solid #3267e3; padding:14px 18px; margin:12px 0; font-family: Consolas, monospace; font-size:14px; line-height:1.7; }}
    .math .big {{ font-size:17px; font-weight:700; color:#1F4E79; }}
    .result {{ background:#172033; color:#fff; padding:20px 24px; border-radius:10px; text-align:center; margin-top:14px; }}
    .result .num {{ font-size:32px; font-weight:800; }}
    .hint {{ font-size:13px; color:#64748b; margin-top:10px; }}
    ul {{ padding-left:20px; }}
    .badge {{ display:inline-block; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:700; }}
    .A {{ background:#C6EFCE; }} .B {{ background:#FFE699; }} .X {{ background:#C6EFCE; }} .Y {{ background:#FFE699; }}
    table.src {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:8px; }}
    table.src th, table.src td {{ padding:8px 10px; border-bottom:1px solid #e8ecf2; text-align:left; }}
    table.src th {{ background:#f8faff; width:45%; color:#445268; }}
    footer {{ text-align:center; font-size:12px; color:#94a3b8; padding:16px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Jak system liczy sugestię zamówienia</h1>
      <p><strong>{sku}</strong> — {name}<br>Raport {report_date} · przykład dla jednego produktu</p>
    </header>

    <div class="goal card" style="margin-top:0;border-radius:0 0 10px 10px">
      <strong>Cel w prostych słowach:</strong> System patrzy ile tego produktu <em>sprzedajecie</em>,
      mnoży przez <em>ile dni musi wystarczyć zapas</em> (czas dostawy + bufor), odejmuje to co
      <em>już macie na magazynie</em> i to co <em>jedzie od dostawcy</em> — wychodzi ile sztuk warto domówić.
    </div>

    <div class="card">
      <h2>Krok 1 · Skąd bierzemy dane?</h2>
      <p>Wszystko startuje z eksportu Nexo (pliki JSON skopiowane do systemu):</p>
      <table class="src">
        <tr><th>Sprzedaż (ostatnie {window_days} dni)</th><td><strong>{fnum(qty_sum, 1)} szt.</strong> · {fnum(net_sum, 0)} PLN netto</td></tr>
        <tr><th>Dni, w których była sprzedaż</th><td>{tx_days} dni (nie każdy dzień musi mieć ruch)</td></tr>
        <tr><th>Stan wolny (dostępny)</th><td><strong>{fnum(free, 1)} szt.</strong> — stan minus rezerwacje</td></tr>
        <tr><th>W drodze od dostawcy (ZD)</th><td><strong>{fnum(inbound, 1)} szt.</strong> — brak pliku ZD → 0</td></tr>
        <tr><th>Czas dostawy (lead time)</th><td><strong>{fnum(lt, 0)} dni</strong> — z karty produktu</td></tr>
      </table>
    </div>

    <div class="card">
      <h2>Krok 2 · Ile sprzedajemy dziennie? (tempo sprzedaży)</h2>
      <p>Bierzemy <strong>ostatnie 90 dni</strong> — to dokładniejsze niż cały rok, gdy produkt sprzedaje się sezonowo:</p>
      <div class="math">
        Średnia dzienna (90 dni) = sprzedaż w 90 dni ÷ 90<br>
        = <strong>{fnum(avg90 * 90 if avg90 else qty_sum, 1)} szt. ÷ 90</strong> ≈ <span class="big">{fnum(base, 3)} szt./dzień</span>
      </div>
      <p class="hint">Dla porównania: średnia z całego okna {window_days} dni = {fnum(qty_sum, 1)} ÷ {window_days} = {fnum(qty_sum / max(window_days, 1), 3)} szt./dzień.
      Ostatnie 30 dni: {fnum(avg30, 3)} szt./dzień · trend 30/90 = {fnum(trend, 2)}.</p>
    </div>

    <div class="card">
      <h2>Krok 3 · Korekty tempa (opcjonalne mnożniki)</h2>
      <p>Tempo bazowe mnożymy przez współczynniki. Gdy współczynnik = 1,00 — <em>nic nie zmienia</em>:</p>
      <ul>
        {factor_line("Dostępność (stockout)", avail, avail_expl, avail_expl)}
        {factor_line("Spadek popytu", decay, decay_expl, decay_expl)}
        {factor_line("Sezonowość", season, season_expl, season_expl)}
      </ul>
      <div class="math">
        Popyt dzienny (po korektach) = {fnum(base, 3)} × {fnum(avail, 2)} × {fnum(decay, 2)} × {fnum(season, 2)}<br>
        = <span class="big">{fnum(dda, 3)} szt./dzień</span>
      </div>
    </div>

    <div class="card">
      <h2>Krok 4 · Na ile dni liczymy zapas?</h2>
      <p>Musimy mieć towar na czas dostawy <em>plus</em> bufor bezpieczeństwa. Klasa XYZ ({xyz}) oznacza popyt {vol_expl}:</p>
      <div class="math">
        Okno pokrycia = lead time + bufor × zmienność<br>
        = {fnum(lt, 0)} + {fnum(buffer_days, 0)} × {fnum(vol, 2)}<br>
        = <span class="big">{fnum(cover, 1)} dni</span>
      </div>
    </div>

    <div class="card">
      <h2>Krok 5 · Ile sztuk potrzebujemy na to okno?</h2>
      <div class="math">
        Potrzeba brutto = popyt dzienny × okno pokrycia<br>
        = {fnum(dda, 3)} × {fnum(cover, 1)}<br>
        = <span class="big">{fnum(demand_cover, 1)} szt.</span>
      </div>
      <p>To ile powinniśmy mieć łącznie, żeby starczyło na {fnum(cover, 0)} dni sprzedaży.</p>
    </div>

    <div class="card">
      <h2>Krok 6 · Odejmujemy to, co już mamy</h2>
      <div class="math">
        Surowa potrzeba = potrzeba brutto − stan wolny − w drodze + zaległości − rezerwacje<br>
        = {fnum(demand_cover, 1)} − {fnum(free, 1)} − {fnum(inbound, 1)} + {fnum(backlog, 1)} − {fnum(reserved_h, 1)}<br>
        = <span class="big">{fnum(raw_formula, 1)} szt.</span>
      </div>
      {"<p>Minimalny stan magazynowy: " + fnum(min_qty, 0) + " szt. — sprawdzamy czy nie trzeba podbić do minimum.</p>" if min_qty > 0 else ""}
      {moq_note}
    </div>

    <div class="card">
      <h2>Klasy ABC / XYZ (informacyjnie)</h2>
      <p>
        <span class="badge {row.get('ABC', '')}">ABC: {row.get('ABC')}</span>
        — {row.get('ABC')} oznacza udział w <strong>łącznej wartości sprzedaży</strong> całego asortymentu
        (A = najważniejsze pod względem obrotu).
        &nbsp;
        <span class="badge {row.get('XYZ', '')}">XYZ: {row.get('XYZ')}</span>
        — {row.get('XYZ')} oznacza <strong>stabilność</strong> sprzedaży (X = regularnie, Z = skokowo).
        Razem: <strong>{row.get('ABC_XYZ')}</strong>.
      </p>
    </div>

    <div class="result">
      <div style="font-size:14px;opacity:.85;margin-bottom:6px">SUGEROWANE ZAMÓWIENIE</div>
      <div class="num">{sug} szt.</div>
      <div style="margin-top:8px;opacity:.9">≈ {fnum(sug_value, 0)} PLN netto · tryb: <strong>{row.get('mode')}</strong></div>
      <div style="font-size:12px;margin-top:10px;opacity:.75">{row.get('note') or ''}</div>
    </div>

    <footer>
      Orders Management · formuła: popyt_skorygowany × (LT + bufor × zmienność) − stan − w_drodze<br>
      Ten plik to przykład edukacyjny — liczby pochodzą z raportu {report_date}.
    </footer>
  </div>
</body>
</html>"""


def _build_calc_email_snippet(row: dict, algo: dict) -> str:
    buffer_days = float(algo.get("buffer_days", 31))
    lt = float(row.get("lead_time_days") or 30)
    vol = float(row.get("volatility_factor") or 1)
    cover = lt + buffer_days * vol
    dda = float(row.get("daily_demand_adj") or 0)
    demand_cover = dda * cover
    free = float(row.get("free_stock") or 0)
    raw = float(row.get("raw_need") or 0)
    sug = int(row.get("suggested_qty") or 0)

    def fnum(v, d=2):
        try:
            return f"{float(v):,.{d}f}".replace(",", " ")
        except (TypeError, ValueError):
            return str(v)

    steps = [
        ("Produkt", f"<strong>{row.get('sku')}</strong> — {str(row.get('name', ''))[:50]}"),
        ("ABC / XYZ", f"{row.get('ABC')} / {row.get('XYZ')} → {row.get('ABC_XYZ')}"),
        ("Popyt dzienny skorygowany", f"{fnum(dda, 3)} szt./dzień"),
        ("Pokrycie (LT + bufor × vol)", f"{fnum(lt, 0)} + {fnum(buffer_days, 0)} × {fnum(vol, 2)} = {fnum(cover, 1)} dni"),
        ("Zapotrzebowanie na okno", f"{fnum(dda, 3)} × {fnum(cover, 1)} = <strong>{fnum(demand_cover, 1)} szt.</strong>"),
        ("Wolny stan", f"{fnum(free, 1)} szt."),
        ("Surota potrzeba", f"<strong>{fnum(raw, 1)} szt.</strong>"),
        ("Sugestia (MOQ/increment)", f"<strong>{sug} szt.</strong> ({fnum(row.get('suggested_value'), 0)} PLN netto)"),
        ("Tryb", str(row.get("mode") or "")),
    ]
    rows_html = "".join(
        f"<tr><td style='padding:4px 8px;color:#78716c;white-space:nowrap'>{k}</td>"
        f"<td style='padding:4px 8px'>{v}</td></tr>"
        for k, v in steps
    )
    return (
        f"<table style='width:100%;border-collapse:collapse;font-size:12px;line-height:1.45'>"
        f"{rows_html}</table>"
    )


def main() -> None:
    settings_app = get_settings()
    ensure_dirs(settings_app)
    cfg = load_settings(settings_app.settings_file)
    uploads = settings_app.uploads_dir
    exports = settings_app.exports_dir

    counts = _copy_data(uploads)
    print("Skopiowano:", counts)

    license_status = LicenseStatus(
        valid=True,
        reason="local run",
        mode="licensed",
        payload=LicensePayload(customer="dev", max_skus=10**9),
    )

    result = run_pipeline(
        products_path=uploads / "products.json",
        sales_path=uploads / "sales.json",
        settings=cfg,
        exports_dir=exports,
        license_status=license_status,
        uploads_dir=uploads,
    )
    if not result.ok or not result.excel_path:
        raise RuntimeError(result.message)

    print(result.message)
    print("Excel:", result.excel_path)

    # Re-load merged for HTML — re-run minimal merge for example row
    import pandas as pd
    from app.engine.abc_xyz import assign_abc_xyz
    from app.engine.demand_engine import enrich_demand
    from app.engine.io_data import aggregate_sales, filter_stock_catalog, load_products, load_purchase_orders, load_sales
    from app.engine.suggest import suggest_orders

    cmap = cfg.get("column_map", {})
    products = load_products(uploads / "products.json", cmap.get("products", {}))
    sales = load_sales(uploads / "sales.json", cmap.get("sales", {}))
    products, sales, _, _ = filter_stock_catalog(
        products, sales, None, cfg.get("exclude_product_types")
    )
    window = int(cfg.get("algorithm", {}).get("sales_window_days", 365))
    sales_agg = aggregate_sales(sales, window)
    merged = products.merge(sales_agg, on="id", how="left").fillna(0)
    merged = assign_abc_xyz(merged, cfg.get("abc_xyz", {}))
    merged = enrich_demand(merged, sales, purchase_orders=load_purchase_orders(None, {}), algo=cfg.get("algorithm", {}))
    merged = suggest_orders(merged, cfg.get("algorithm", {}))

    example = _pick_example_row(merged)
    report_date = date.today().isoformat()
    html_path = exports / f"przyklad_kalkulacji_{example.get('sku', 'sku')}.html"
    html_path.write_text(_build_calc_html(example, cfg.get("algorithm", {}), report_date), encoding="utf-8")
    print("HTML przykład:", html_path)

    mail_cfg = dict(cfg.get("mail") or {})
    mail_cfg["report_recipients"] = MAIL_TO
    mail_cfg["report_body"] = (
        "<p>Dzień dobry,</p>"
        "<p>W załączeniu raport zamówień z danych Nexo (towary + komplety; <strong>usługi wykluczone</strong>). "
        "ABC/XYZ na całym asortymencie towarowym. Bez ZD — w drodze = 0.</p>"
    )

    mail_result = send_report_email(
        mail_cfg,
        excel_path=result.excel_path,
        summary=result.summary,
        extra_attachments=[html_path],
        calc_snippet_html=_build_calc_email_snippet(example, cfg.get("algorithm", {})),
    )
    print("Mail:", mail_result)

    summary_path = exports / "last_run_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "counts": counts,
                "pipeline": result.summary,
                "mail": mail_result,
                "example_html": str(html_path.name),
                "excel": result.excel_path.name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Podsumowanie:", summary_path)


if __name__ == "__main__":
    main()
