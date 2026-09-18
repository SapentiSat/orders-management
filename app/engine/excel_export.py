from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule, IconSetRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.properties import Outline
from openpyxl.worksheet.table import Table, TableStyleInfo


BASE_COLUMNS = [
    ("status_icon", "Status"),
    ("id", "ID produktu"),
    ("sku", "SKU"),
    ("ean", "EAN"),
    ("name", "Nazwa produktu"),
    ("producer", "Dostawca / producent"),
    ("group", "Grupa towarowa"),
    ("active", "Aktywny"),
    ("eol", "EOL"),
    ("stock", "Stan magazynowy"),
    ("reserved", "Rezerwacje"),
    ("free_stock", "Wolny stan"),
    ("min_qty", "Ilość minimalna"),
    ("moq", "MOQ"),
    ("order_increment", "Order Increment"),
    ("lead_time_days", "Lead time (dni)"),
    ("tx_days", "Dni z ruchem (okno)"),
    ("daily_avg_qty", "Śr. dzienna (szt.)"),
    ("daily_demand_adj", "Popyt skorygowany / dzień"),
    ("availability_factor", "Wsp. dostępności"),
    ("demand_decay_factor", "Wsp. spadku popytu"),
    ("seasonality_factor", "Wsp. sezonowości"),
    ("volatility_factor", "Wsp. zmienności"),
    ("inbound_qty", "W drodze (PO)"),
    ("reserved_horizon", "Rezerwacje w horyzoncie"),
    ("cover_days", "Okno pokrycia (dni)"),
    ("suggested_qty", "Sugerowana ilość"),
    ("suggested_value", "Wartość sugestii (PLN)"),
    ("ABC", "ABC"),
    ("XYZ", "XYZ"),
    ("ABC_XYZ", "ABC/XYZ"),
    ("mode", "Tryb zamówienia"),
    ("note", "Uwagi"),
]

COLUMN_NOTES: dict[str, str] = {
    "Status": "Ikona trybu: ✔ auto-ready, ⚠ do weryfikacji, ✖ skip.",
    "ID produktu": "Identyfikator produktu z ERP — klucz łączenia ze sprzedażą.",
    "SKU": "Kod magazynowy / handlowy produktu.",
    "EAN": "Kod kreskowy EAN (jeśli dostępny w danych).",
    "Nazwa produktu": "Nazwa handlowa z kartoteki produktów.",
    "Dostawca / producent": "Producent lub dostawca — używany we fragmentatorach Dashboard.",
    "Grupa towarowa": "Grupa asortymentowa — filtr wykresów na Dashboard.",
    "Aktywny": "Czy produkt jest aktywny w ofercie.",
    "EOL": "End of Life — produkt wycofywany / końcówka życia.",
    "Stan magazynowy": "Stan fizyczny w magazynie.",
    "Rezerwacje": "Ilość zarezerwowana (niedostępna do sprzedaży).",
    "Wolny stan": "Stan − rezerwacje. Bazowy zasób do pokrycia sprzedaży.",
    "Ilość minimalna": "Minimalny pożądany poziom zapasu (jeśli podany).",
    "MOQ": "Minimalna ilość zamówienia u dostawcy.",
    "Order Increment": "Krok zamówienia (zamawiamy wielokrotności tej wartości).",
    "Lead time (dni)": "Czas realizacji dostawy w dniach.",
    "Dni z ruchem (okno)": "Liczba dni z transakcją w oknie historii sprzedaży.",
    "Śr. dzienna (szt.)": "Surowa średnia dzienna sprzedaż sztuk w oknie.",
    "Popyt skorygowany / dzień": "Średnia po współczynnikach: dostępność × spadek × sezonowość.",
    "Wsp. dostępności": ">1 gdy historia sugeruje stockout / brak towaru.",
    "Wsp. spadku popytu": "<1 gdy sprzedaż spada mimo dostępnego stanu (rynek stygnie).",
    "Wsp. sezonowości": "Mnożnik aktualnego miesiąca vs średnia miesięczna SKU.",
    "Wsp. zmienności": "Mnożnik buforu z XYZ/CV.",
    "W drodze (PO)": "Suma otwartych zamówień do dostawcy.",
    "Rezerwacje w horyzoncie": "Rezerwacje nachodzące na LT+bufor (datowane, jeśli plik podany).",
    "Okno pokrycia (dni)": "LT + bufor×zmienność — na ile dni liczymy zapotrzebowanie.",
    "Sugerowana ilość": "Wynik formuły zakupowej + zaokrąglenie MOQ/OI.",
    "Wartość sugestii (PLN)": "Szacunkowa wartość sugestii zamówienia w PLN netto.",
    "ABC": "Klasa wartości sprzedaży: A najważniejsze, C najmniej.",
    "XYZ": "Stabilność popytu: X stabilny, Y zmienny, Z nieregularny.",
    "ABC/XYZ": "Połączenie klas ABC i XYZ (np. AX = wartościowy i stabilny).",
    "Tryb zamówienia": "auto-ready / do weryfikacji / skip — reguły panelu.",
    "Uwagi": "Wyjaśnienie decyzji + aktywne współczynniki.",
}


FILLS = {
    "auto-ready": PatternFill("solid", fgColor="C6EFCE"),
    "do weryfikacji": PatternFill("solid", fgColor="FFEB9C"),
    "skip": PatternFill("solid", fgColor="D9D9D9"),
    "header": PatternFill("solid", fgColor="1F4E79"),
    "subhead": PatternFill("solid", fgColor="2E75B6"),
    "month_header": PatternFill("solid", fgColor="5B9BD5"),
    "filter": PatternFill("solid", fgColor="FFF2CC"),
    "kpi": PatternFill("solid", fgColor="E8F0FE"),
    "A": PatternFill("solid", fgColor="C6EFCE"),
    "B": PatternFill("solid", fgColor="FFE699"),
    "C": PatternFill("solid", fgColor="F8CBAD"),
    "X": PatternFill("solid", fgColor="C6EFCE"),
    "Y": PatternFill("solid", fgColor="FFE699"),
    "Z": PatternFill("solid", fgColor="FFC7CE"),
    "up": PatternFill("solid", fgColor="C6EFCE"),
    "down": PatternFill("solid", fgColor="FFC7CE"),
}

ICON_MAP = {"auto-ready": "✔", "do weryfikacji": "⚠", "skip": "✖"}

THIN = Border(
    left=Side(style="thin", color="D0D7DE"),
    right=Side(style="thin", color="D0D7DE"),
    top=Side(style="thin", color="D0D7DE"),
    bottom=Side(style="thin", color="D0D7DE"),
)


def _month_qty_matrix(sales: pd.DataFrame, product_ids: pd.Series, window_days: int) -> tuple[list[str], pd.DataFrame]:
    if sales is None or sales.empty or product_ids.empty:
        return [], pd.DataFrame(index=product_ids)
    max_date = sales["date"].max()
    cutoff = max_date - pd.Timedelta(days=int(window_days))
    s = sales[(sales["date"] >= cutoff) & (sales["id"].isin(set(product_ids)))].copy()
    if s.empty:
        return [], pd.DataFrame(index=product_ids)
    s["month"] = s["date"].dt.to_period("M").astype(str)
    months = sorted(s["month"].unique().tolist())
    pivot = s.groupby(["id", "month"], as_index=False)["qty"].sum()
    wide = pivot.pivot(index="id", columns="month", values="qty").reindex(product_ids).fillna(0)
    return months, wide.reindex(columns=months, fill_value=0)


def _margin_pct(net: float, cost: float) -> float | None:
    if net and net > 0:
        return round((1.0 - cost / net) * 100.0, 2)
    return None


def _period_metrics(sales: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "id", "sku", "name", "producer", "group", "ABC", "XYZ", "ABC_XYZ",
        "mode", "suggested_qty", "suggested_value",
    ]
    base = products[[c for c in cols if c in products.columns]].copy()
    for c in cols:
        if c not in base.columns:
            base[c] = "" if c not in {"suggested_qty", "suggested_value"} else 0

    metric_cols = (
        "net_7d", "cost_7d", "margin_7d",
        "net_month", "cost_month", "margin_month",
        "net_year", "cost_year", "margin_year",
    )
    if sales is None or sales.empty:
        for col in metric_cols:
            base[col] = 0.0
        return base

    max_date = sales["date"].max()
    d7 = max_date - pd.Timedelta(days=7)
    month_start = max_date.replace(day=1)
    year_start = max_date.replace(month=1, day=1)

    def agg(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["id", f"net_{prefix}", f"cost_{prefix}", f"margin_{prefix}"])
        g = frame.groupby("id", as_index=False).agg(net=("net_value", "sum"), cost=("cost", "sum"))
        g[f"net_{prefix}"] = g["net"]
        g[f"cost_{prefix}"] = g["cost"]
        g[f"margin_{prefix}"] = g["net"] - g["cost"]
        return g[["id", f"net_{prefix}", f"cost_{prefix}", f"margin_{prefix}"]]

    out = (
        base.merge(agg(sales[sales["date"] >= d7], "7d"), on="id", how="left")
        .merge(agg(sales[sales["date"] >= month_start], "month"), on="id", how="left")
        .merge(agg(sales[sales["date"] >= year_start], "year"), on="id", how="left")
    )
    for col in metric_cols:
        out[col] = out[col].fillna(0) if col in out.columns else 0.0
    return out


def _style_header_row(ws, row: int, start_col: int, end_col: int, fill: PatternFill) -> None:
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row, col)
        cell.fill = fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")


def _add_header_notes(ws, headers: list[str], window_days: int) -> None:
    for idx, label in enumerate(headers, start=1):
        note = COLUMN_NOTES.get(label)
        if not note:
            if label.startswith("Sprzedaż netto (") and "dni)" in label:
                note = f"Suma sprzedaży netto PLN w oknie {window_days} dni."
            elif label.startswith("Koszt (") and "dni)" in label:
                note = f"Suma kosztu ewidencyjnego w oknie {window_days} dni."
            elif label.startswith("Marża (") and "dni)" in label:
                note = f"Netto − koszt w oknie {window_days} dni."
            elif label.startswith("Sprzedaż netto 20"):
                note = "Sprzedaż w sztukach w danym miesiącu kalendarzowym (blok zwijany)."
            elif label.startswith("Sprzedaż szt."):
                note = "Sprzedaż w sztukach w danym miesiącu kalendarzowym (blok zwijany)."
            elif label == "Marża %":
                note = "Marża procentowa: (1 − koszt / sprzedaż netto) × 100."
            elif label == "Zysk":
                note = "Zysk brutto: sprzedaż netto − koszt ewidencyjny (PLN)."
            elif label.startswith("Miesiące"):
                note = "Kliknij „+” nad kolumnami, aby rozwinąć sprzedaż netto po miesiącach."
        if note:
            ws.cell(1, idx).comment = Comment(note, "Orders Management", width=280, height=80)


def _apply_abc_xyz_cf(ws, headers: list[str], last_row: int) -> None:
    if last_row < 2:
        return
    for col_name, mapping in (
        ("ABC", {"A": FILLS["A"], "B": FILLS["B"], "C": FILLS["C"]}),
        ("XYZ", {"X": FILLS["X"], "Y": FILLS["Y"], "Z": FILLS["Z"]}),
    ):
        if col_name not in headers:
            continue
        letter = get_column_letter(headers.index(col_name) + 1)
        rng = f"{letter}2:{letter}{last_row}"
        for value, fill in mapping.items():
            ws.conditional_formatting.add(
                rng, FormulaRule(formula=[f'{letter}2="{value}"'], fill=fill, font=Font(bold=True))
            )
    if "ABC/XYZ" not in headers:
        return
    letter = get_column_letter(headers.index("ABC/XYZ") + 1)
    rng = f"{letter}2:{letter}{last_row}"
    for abc, fill in (("A", FILLS["A"]), ("B", FILLS["B"]), ("C", FILLS["C"])):
        ws.conditional_formatting.add(
            rng, FormulaRule(formula=[f'LEFT({letter}2,1)="{abc}"'], fill=fill, font=Font(bold=True))
        )
    ws.conditional_formatting.add(
        rng,
        FormulaRule(
            formula=[f'RIGHT({letter}2,1)="Z"'],
            fill=PatternFill("solid", fgColor="F4B183"),
            font=Font(bold=True, color="843C0C"),
        ),
    )


def _write_orders_sheet(wb: Workbook, df: pd.DataFrame, *, window_days: int, sales: pd.DataFrame | None) -> None:
    ws = wb.active
    ws.title = "Tabela zamówień"
    view = df.copy()
    view["status_icon"] = view["mode"].map(ICON_MAP).fillna("•")
    mode_order = {"auto-ready": 0, "do weryfikacji": 1, "skip": 2}
    view["_mode_ord"] = view["mode"].map(mode_order).fillna(9)
    view = view.sort_values(by=["_mode_ord", "ABC", "suggested_value"], ascending=[True, True, False])
    view = view.drop(columns=["_mode_ord"])

    months, month_wide = _month_qty_matrix(sales if sales is not None else pd.DataFrame(), view["id"], window_days)

    if "net_sum" in view.columns and "cost_sum" in view.columns:
        view["profit_window"] = view["net_sum"].fillna(0) - view["cost_sum"].fillna(0)
        view["margin_pct"] = view.apply(
            lambda r: _margin_pct(float(r.get("net_sum") or 0), float(r.get("cost_sum") or 0)),
            axis=1,
        )
    else:
        view["profit_window"] = 0
        view["net_sum"] = view.get("net_sum", 0)
        view["cost_sum"] = view.get("cost_sum", 0)
        view["margin_pct"] = None

    headers: list[str] = []
    keys: list[str] = []
    for key, label in BASE_COLUMNS:
        if key not in view.columns:
            continue
        if key == "tx_days":
            headers.extend([
                f"Sprzedaż netto ({window_days} dni)",
                f"Koszt ({window_days} dni)",
                "Marża %",
                "Zysk",
            ])
            keys.extend(["net_sum", "cost_sum", "margin_pct", "profit_window"])
        headers.append(label)
        keys.append(key)

    month_anchor_col = month_start_col = month_end_col = None
    if months:
        headers.append(f"Miesiące ({window_days} dni) →")
        month_anchor_col = len(headers)
        month_start_col = len(headers) + 1
        headers.extend([f"Sprzedaż szt. {m}" for m in months])
        month_end_col = len(headers)

    ws.append(headers)
    _style_header_row(ws, 1, 1, len(headers), FILLS["header"])
    if months and month_anchor_col and month_start_col and month_end_col:
        ws.cell(1, month_anchor_col).fill = FILLS["subhead"]
        for col in range(month_start_col, month_end_col + 1):
            ws.cell(1, col).fill = FILLS["month_header"]
    _add_header_notes(ws, headers, window_days)

    for _, row in view.iterrows():
        values = []
        for key in keys:
            if key == "margin_pct":
                mp = row.get("margin_pct")
                values.append(float(mp) if mp is not None and pd.notna(mp) else "")
            elif key in {"net_sum", "cost_sum", "profit_window", "suggested_value"}:
                values.append(round(float(row.get(key, 0) or 0), 2))
            elif key in {"daily_avg_qty", "daily_demand_adj"}:
                values.append(round(float(row.get(key, 0) or 0), 2))
            elif key in {"suggested_qty"}:
                values.append(float(row.get(key, 0) or 0))
            elif key == "demand_decay_factor":
                values.append(round(float(row.get(key, 0) or 0), 2))
            elif key in {"availability_factor", "seasonality_factor", "volatility_factor"}:
                values.append(round(float(row.get(key, 0) or 0), 2))
            else:
                values.append(row.get(key, ""))
        if months:
            values.append("")
            pid = row["id"]
            if pid in month_wide.index:
                values.extend([float(month_wide.loc[pid, m]) for m in months])
            else:
                values.extend([0.0] * len(months))
        ws.append(values)

    last_row = ws.max_row
    mode_idx = headers.index("Tryb zamówienia") + 1 if "Tryb zamówienia" in headers else None
    qty_idx = headers.index("Sugerowana ilość") + 1 if "Sugerowana ilość" in headers else None
    free_idx = headers.index("Wolny stan") + 1 if "Wolny stan" in headers else None
    icon_idx = headers.index("Status") + 1 if "Status" in headers else None

    margin_pct_idx = headers.index("Marża %") + 1 if "Marża %" in headers else None
    profit_idx = headers.index("Zysk") + 1 if "Zysk" in headers else None
    abc_idx = headers.index("ABC") + 1 if "ABC" in headers else None
    xyz_idx = headers.index("XYZ") + 1 if "XYZ" in headers else None
    abcxyz_idx = headers.index("ABC/XYZ") + 1 if "ABC/XYZ" in headers else None
    decay_idx = headers.index("Wsp. spadku popytu") + 1 if "Wsp. spadku popytu" in headers else None

    daily_avg_idx = headers.index("Śr. dzienna (szt.)") + 1 if "Śr. dzienna (szt.)" in headers else None
    daily_adj_idx = headers.index("Popyt skorygowany / dzień") + 1 if "Popyt skorygowany / dzień" in headers else None
    net_idx = headers.index(f"Sprzedaż netto ({window_days} dni)") + 1 if f"Sprzedaż netto ({window_days} dni)" in headers else None
    cost_idx = headers.index(f"Koszt ({window_days} dni)") + 1 if f"Koszt ({window_days} dni)" in headers else None
    sug_val_idx = headers.index("Wartość sugestii (PLN)") + 1 if "Wartość sugestii (PLN)" in headers else None

    for r in range(2, last_row + 1):
        if mode_idx:
            mode_val = str(ws.cell(r, mode_idx).value or "")
            fill = FILLS.get(mode_val)
            if fill:
                ws.cell(r, mode_idx).fill = fill
                ws.cell(r, mode_idx).font = Font(bold=True)
                if icon_idx:
                    ws.cell(r, icon_idx).fill = fill
                    ws.cell(r, icon_idx).alignment = Alignment(horizontal="center")
                    ws.cell(r, icon_idx).font = Font(bold=True, size=12)
        if abc_idx:
            abc_val = str(ws.cell(r, abc_idx).value or "")
            if abc_val in FILLS:
                ws.cell(r, abc_idx).fill = FILLS[abc_val]
                ws.cell(r, abc_idx).font = Font(bold=True)
                ws.cell(r, abc_idx).alignment = Alignment(horizontal="center")
        if xyz_idx:
            xyz_val = str(ws.cell(r, xyz_idx).value or "")
            if xyz_val in FILLS:
                ws.cell(r, xyz_idx).fill = FILLS[xyz_val]
                ws.cell(r, xyz_idx).font = Font(bold=True)
                ws.cell(r, xyz_idx).alignment = Alignment(horizontal="center")
        if abcxyz_idx:
            combo = str(ws.cell(r, abcxyz_idx).value or "")
            if combo:
                abc_part = combo[0] if combo else ""
                xyz_part = combo[-1] if len(combo) >= 2 else ""
                fill = FILLS.get(abc_part) or FILLS.get(xyz_part)
                if fill:
                    ws.cell(r, abcxyz_idx).fill = fill
                ws.cell(r, abcxyz_idx).font = Font(bold=True)
                ws.cell(r, abcxyz_idx).alignment = Alignment(horizontal="center")
        if decay_idx:
            try:
                ws.cell(r, decay_idx).number_format = "0.00"
            except (TypeError, ValueError):
                pass
        for label in ("Wsp. dostępności", "Wsp. sezonowości", "Wsp. zmienności"):
            fidx = headers.index(label) + 1 if label in headers else None
            if fidx:
                ws.cell(r, fidx).number_format = "0.00"
        for idx in (daily_avg_idx, daily_adj_idx):
            if idx:
                ws.cell(r, idx).number_format = "0.00"
        for idx in (net_idx, cost_idx, profit_idx, sug_val_idx):
            if idx:
                ws.cell(r, idx).number_format = "#,##0.00"
        if margin_pct_idx:
            ws.cell(r, margin_pct_idx).number_format = '0.00"%"'
        for c in range(1, len(headers) + 1):
            ws.cell(r, c).border = THIN

    _apply_abc_xyz_cf(ws, headers, last_row)
    if margin_pct_idx and last_row >= 2:
        mcol = get_column_letter(margin_pct_idx)
        ws.conditional_formatting.add(
            f"{mcol}2:{mcol}{last_row}",
            IconSetRule("3TrafficLights1", "num", [10, 20, 100], showValue=True, reverse=True),
        )
    if free_idx and last_row >= 2:
        free_range = f"{get_column_letter(free_idx)}2:{get_column_letter(free_idx)}{last_row}"
        ws.conditional_formatting.add(
            free_range,
            ColorScaleRule(
                start_type="min", start_color="FFC7CE",
                mid_type="percentile", mid_value=50, mid_color="FFEB9C",
                end_type="max", end_color="C6EFCE",
            ),
        )

    for i, label in enumerate(headers, start=1):
        width = 14
        if "Nazwa" in label:
            width = 30
        elif label in {"ABC", "XYZ", "ABC/XYZ", "Status", "Marża %", "Zysk"}:
            width = 10
        elif label.startswith("Sprzedaż szt."):
            width = 11
        elif any(x in label for x in ("Sprzedaż", "Koszt", "Marża", "Wartość")):
            width = 15
        ws.column_dimensions[get_column_letter(i)].width = width

    ws.row_dimensions[1].height = 40
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
    if months and month_start_col and month_end_col:
        for col in range(month_start_col, month_end_col + 1):
            ws.column_dimensions[get_column_letter(col)].outline_level = 1
            ws.column_dimensions[get_column_letter(col)].hidden = True
        if month_anchor_col:
            ws.column_dimensions[get_column_letter(month_anchor_col)].width = 16
        ws.sheet_properties.outlinePr = Outline(summaryRight=False, summaryBelow=True)
    ws.sheet_properties.tabColor = "1F4E79"


def _sumifs_money(period_cell: str, col_7: str, col_m: str, col_y: str, prod_crit: str, grp_crit: str) -> str:
    return (
        f'=IF({period_cell}="7 dni",'
        f"SUMIFS('Źródło filtrów'!{col_7}:{col_7},'Źródło filtrów'!A:A,{prod_crit},'Źródło filtrów'!B:B,{grp_crit}),"
        f'IF({period_cell}="miesiąc",'
        f"SUMIFS('Źródło filtrów'!{col_m}:{col_m},'Źródło filtrów'!A:A,{prod_crit},'Źródło filtrów'!B:B,{grp_crit}),"
        f"SUMIFS('Źródło filtrów'!{col_y}:{col_y},'Źródło filtrów'!A:A,{prod_crit},'Źródło filtrów'!B:B,{grp_crit})))"
    )


def _write_source_and_dashboard(
    wb: Workbook,
    df: pd.DataFrame,
    analytics: dict,
    sales: pd.DataFrame | None,
    window_days: int,
) -> None:
    metrics = _period_metrics(sales if sales is not None else pd.DataFrame(), df)

    src = wb.create_sheet("Źródło filtrów", 1)
    # A Dostawca B Grupa C SKU D Nazwa E ABC F XYZ G ABC/XYZ H Tryb
    # I net7 J cost7 K margin7 | L netM M costM N marginM | O netY P costY Q marginY | R sugestia
    src_headers = [
        "Dostawca", "Grupa towarowa", "SKU", "Nazwa", "ABC", "XYZ", "ABC/XYZ", "Tryb",
        "Netto 7 dni", "Koszt 7 dni", "Marża 7 dni",
        "Netto miesiąc", "Koszt miesiąc", "Marża miesiąc",
        "Netto rok", "Koszt rok", "Marża rok",
        "Sugestia PLN",
    ]
    src.append(src_headers)
    _style_header_row(src, 1, 1, len(src_headers), FILLS["header"])
    for _, row in metrics.iterrows():
        src.append([
            row.get("producer") or "(brak)",
            row.get("group") or "(brak)",
            row.get("sku") or "",
            row.get("name") or "",
            row.get("ABC") or "",
            row.get("XYZ") or "",
            row.get("ABC_XYZ") or "",
            row.get("mode") or "",
            float(row.get("net_7d") or 0),
            float(row.get("cost_7d") or 0),
            float(row.get("margin_7d") or 0),
            float(row.get("net_month") or 0),
            float(row.get("cost_month") or 0),
            float(row.get("margin_month") or 0),
            float(row.get("net_year") or 0),
            float(row.get("cost_year") or 0),
            float(row.get("margin_year") or 0),
            float(row.get("suggested_value") or 0),
        ])
    src_last = src.max_row
    _apply_abc_xyz_cf(src, src_headers, src_last)
    if src_last >= 2:
        table = Table(displayName="DaneFiltrow", ref=f"A1:R{src_last}")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False, showLastColumn=False, showColumnStripes=False
        )
        src.add_table(table)
    for i in range(1, len(src_headers) + 1):
        src.column_dimensions[get_column_letter(i)].width = 14
    src.column_dimensions["D"].width = 28
    src.freeze_panes = "A2"
    src.sheet_properties.tabColor = "5B9BD5"

    producers = sorted({str(x) for x in metrics["producer"].fillna("(brak)") if str(x).strip()}) or ["(brak)"]
    groups = sorted({str(x) for x in metrics["group"].fillna("(brak)") if str(x).strip()}) or ["(brak)"]

    lists = wb.create_sheet("_Listy", 2)
    lists.sheet_state = "hidden"
    lists["A1"], lists["B1"], lists["C1"] = "Dostawca", "Grupa", "Okres"
    for i, p in enumerate(producers, start=2):
        lists.cell(i, 1, p)
    for i, g in enumerate(groups, start=2):
        lists.cell(i, 2, g)
    for i, label in enumerate(("7 dni", "miesiąc", "rok"), start=2):
        lists.cell(i, 3, label)
    lists.cell(len(producers) + 2, 1, "(wszyscy)")
    lists.cell(len(groups) + 2, 2, "(wszystkie)")

    dash = wb.create_sheet("Dashboard", 0)
    dash.sheet_view.showGridLines = False
    dash["A1"] = "ORDERS MANAGEMENT — Dashboard"
    dash["A1"].font = Font(bold=True, size=18, color="1F4E79")
    dash["A2"] = (
        "Fragmentatory (żółte listy): Dostawca · Grupa · Okres. "
        "KPI i wykresy liczą NETTO / KOSZT / MARŻĘ — bez sztuk jako głównej metryki."
    )
    dash["A2"].font = Font(color="667788", italic=True)
    dash.merge_cells("A2:L2")

    # --- Fragmentatory panel (compact, Power BI-like filters) ---
    dash["A4"] = "FRAGMENTATORY"
    dash["A4"].font = Font(bold=True, size=12, color="1F4E79")
    for r, label, default in ((5, "Dostawca", "(wszyscy)"), (6, "Grupa towarowa", "(wszystkie)"), (7, "Okres", "7 dni")):
        dash.cell(r, 1, label).font = Font(bold=True)
        dash.cell(r, 2, default)
        dash.cell(r, 2).fill = FILLS["filter"]
        dash.cell(r, 2).border = THIN
        dash.cell(r, 2).font = Font(bold=True)
    dash["D5"] = "Zmień żółte komórki → KPI i wykresy poniżej przeliczają się jak w Power BI."
    dash["D5"].font = Font(color="667788", italic=True)
    dash.merge_cells("D5:L5")

    dv_prod = DataValidation(type="list", formula1=f"'_Listy'!$A$2:$A${len(producers) + 2}", allow_blank=True)
    dv_grp = DataValidation(type="list", formula1=f"'_Listy'!$B$2:$B${len(groups) + 2}", allow_blank=True)
    dv_period = DataValidation(type="list", formula1="'_Listy'!$C$2:$C$4", allow_blank=False)
    for dv, cell in ((dv_prod, "B5"), (dv_grp, "B6"), (dv_period, "B7")):
        dash.add_data_validation(dv)
        dv.add(dash[cell])

    prod_crit = 'IF($B$5="(wszyscy)","*",$B$5)'
    grp_crit = 'IF($B$6="(wszystkie)","*",$B$6)'

    # --- KPI: Netto / Koszt / Marża ---
    dash["A9"] = "KPI FINANSOWE (wg filtrów)"
    dash["A9"].font = Font(bold=True, size=13, color="1F4E79")
    kpis = [
        (10, "Netto (PLN)", _sumifs_money("$B$7", "I", "L", "O", prod_crit, grp_crit)),
        (11, "Koszt (PLN)", _sumifs_money("$B$7", "J", "M", "P", prod_crit, grp_crit)),
        (12, "Marża (PLN)", _sumifs_money("$B$7", "K", "N", "Q", prod_crit, grp_crit)),
        (13, "Sugestia zamówień (PLN)", f"=SUMIFS('Źródło filtrów'!R:R,'Źródło filtrów'!A:A,{prod_crit},'Źródło filtrów'!B:B,{grp_crit})"),
    ]
    for r, label, formula in kpis:
        dash.cell(r, 1, label).fill = FILLS["kpi"]
        dash.cell(r, 1).font = Font(bold=True, color="1F4E79")
        dash.cell(r, 2, formula)
        dash.cell(r, 2).font = Font(bold=True, size=14)
        dash.cell(r, 2).number_format = '#,##0'
        dash.cell(r, 2).border = THIN

    counts = df["mode"].value_counts().to_dict() if "mode" in df.columns else {}
    dash["D10"] = "Tryby (cały raport)"
    dash["D10"].font = Font(bold=True, color="1F4E79")
    for r, label, key, fill in (
        (11, "✔ Auto-ready", "auto-ready", "auto-ready"),
        (12, "⚠ Do weryfikacji", "do weryfikacji", "do weryfikacji"),
        (13, "✖ Skip", "skip", "skip"),
    ):
        dash.cell(r, 4, label)
        dash.cell(r, 5, int(counts.get(key, 0))).fill = FILLS[fill]

    # --- Chart data (netto by group / producer) — placed LEFT, charts on RIGHT of data ---
    # Layout map (no overlap):
    #  Rows 16-30: group table A-B + producer table D-E
    #  Charts: group at G16, producer at G32
    #  ABC/XYZ tables A34 / D34, pies G48 / J48
    #  Comparisons from row 62, daily/top further down

    top_groups = groups[:10]
    top_producers = producers[:10]
    g_start = 16
    dash.cell(g_start, 1, "Grupa")
    dash.cell(g_start, 2, "Netto (filtr)")
    _style_header_row(dash, g_start, 1, 2, FILLS["header"])
    for i, g in enumerate(top_groups, start=1):
        g_esc = str(g).replace('"', '""')
        dash.cell(g_start + i, 1, g)
        dash.cell(
            g_start + i,
            2,
            (
                f'=IF(OR($B$6="(wszystkie)",$B$6="{g_esc}"),'
                f'IF($B$7="7 dni",SUMIFS(\'Źródło filtrów\'!I:I,\'Źródło filtrów\'!B:B,"{g_esc}",\'Źródło filtrów\'!A:A,{prod_crit}),'
                f'IF($B$7="miesiąc",SUMIFS(\'Źródło filtrów\'!L:L,\'Źródło filtrów\'!B:B,"{g_esc}",\'Źródło filtrów\'!A:A,{prod_crit}),'
                f'SUMIFS(\'Źródło filtrów\'!O:O,\'Źródło filtrów\'!B:B,"{g_esc}",\'Źródło filtrów\'!A:A,{prod_crit}))),0)'
            ),
        )
        dash.cell(g_start + i, 2).number_format = '#,##0'
    g_end = g_start + len(top_groups)

    p_start = 16
    dash.cell(p_start, 4, "Dostawca")
    dash.cell(p_start, 5, "Netto (filtr)")
    _style_header_row(dash, p_start, 4, 5, FILLS["header"])
    for i, p in enumerate(top_producers, start=1):
        p_esc = str(p).replace('"', '""')
        dash.cell(p_start + i, 4, p)
        dash.cell(
            p_start + i,
            5,
            (
                f'=IF(OR($B$5="(wszyscy)",$B$5="{p_esc}"),'
                f'IF($B$7="7 dni",SUMIFS(\'Źródło filtrów\'!I:I,\'Źródło filtrów\'!A:A,"{p_esc}",\'Źródło filtrów\'!B:B,{grp_crit}),'
                f'IF($B$7="miesiąc",SUMIFS(\'Źródło filtrów\'!L:L,\'Źródło filtrów\'!A:A,"{p_esc}",\'Źródło filtrów\'!B:B,{grp_crit}),'
                f'SUMIFS(\'Źródło filtrów\'!O:O,\'Źródło filtrów\'!A:A,"{p_esc}",\'Źródło filtrów\'!B:B,{grp_crit}))),0)'
            ),
        )
        dash.cell(p_start + i, 5).number_format = '#,##0'
    p_end = p_start + len(top_producers)

    if top_groups:
        bar_g = BarChart()
        bar_g.type = "col"
        bar_g.style = 10
        bar_g.title = "Netto wg grupy (fragmentatory)"
        bar_g.y_axis.title = "PLN"
        bar_g.height = 9
        bar_g.width = 14
        bar_g.add_data(Reference(dash, min_col=2, min_row=g_start, max_row=g_end), titles_from_data=True)
        bar_g.set_categories(Reference(dash, min_col=1, min_row=g_start + 1, max_row=g_end))
        dash.add_chart(bar_g, "G16")

    if top_producers:
        bar_p = BarChart()
        bar_p.type = "bar"
        bar_p.style = 12
        bar_p.title = "Netto wg dostawcy (fragmentatory)"
        bar_p.x_axis.title = "PLN"
        bar_p.height = 9
        bar_p.width = 14
        bar_p.add_data(Reference(dash, min_col=5, min_row=p_start, max_row=p_end), titles_from_data=True)
        bar_p.set_categories(Reference(dash, min_col=4, min_row=p_start + 1, max_row=p_end))
        dash.add_chart(bar_p, "G32")

    abc_row = 34
    dash.cell(abc_row, 1, "ABC")
    dash.cell(abc_row, 2, "SKU")
    _style_header_row(dash, abc_row, 1, 2, FILLS["header"])
    for i, letter in enumerate(("A", "B", "C"), start=1):
        dash.cell(abc_row + i, 1, letter).fill = FILLS[letter]
        dash.cell(
            abc_row + i,
            2,
            f'=COUNTIFS(\'Źródło filtrów\'!E:E,"{letter}",\'Źródło filtrów\'!A:A,{prod_crit},\'Źródło filtrów\'!B:B,{grp_crit})',
        )

    dash.cell(abc_row, 4, "XYZ")
    dash.cell(abc_row, 5, "SKU")
    _style_header_row(dash, abc_row, 4, 5, FILLS["header"])
    for i, letter in enumerate(("X", "Y", "Z"), start=1):
        dash.cell(abc_row + i, 4, letter).fill = FILLS[letter]
        dash.cell(
            abc_row + i,
            5,
            f'=COUNTIFS(\'Źródło filtrów\'!F:F,"{letter}",\'Źródło filtrów\'!A:A,{prod_crit},\'Źródło filtrów\'!B:B,{grp_crit})',
        )

    pie_abc = PieChart()
    pie_abc.title = "ABC (filtr)"
    pie_abc.height = 8
    pie_abc.width = 10
    pie_abc.add_data(Reference(dash, min_col=2, min_row=abc_row, max_row=abc_row + 3), titles_from_data=True)
    pie_abc.set_categories(Reference(dash, min_col=1, min_row=abc_row + 1, max_row=abc_row + 3))
    dash.add_chart(pie_abc, "G48")

    pie_xyz = PieChart()
    pie_xyz.title = "XYZ (filtr)"
    pie_xyz.height = 8
    pie_xyz.width = 10
    pie_xyz.add_data(Reference(dash, min_col=5, min_row=abc_row, max_row=abc_row + 3), titles_from_data=True)
    pie_xyz.set_categories(Reference(dash, min_col=4, min_row=abc_row + 1, max_row=abc_row + 3))
    dash.add_chart(pie_xyz, "J48")

    analytics = analytics or {}
    week = analytics.get("week") or analytics
    month = analytics.get("month") or {}

    # Comparisons far below charts to avoid overlap
    cmp_row = 78
    dash.cell(cmp_row, 1, "Porównanie tygodnia (netto / koszt / marża)")
    dash.cell(cmp_row, 1).font = Font(bold=True, size=13, color="1F4E79")
    dash.cell(cmp_row + 1, 1, "Metryka")
    dash.cell(cmp_row + 1, 2, "Ten tydzień")
    dash.cell(cmp_row + 1, 3, "Poprzedni")
    dash.cell(cmp_row + 1, 4, "Zmiana %")
    _style_header_row(dash, cmp_row + 1, 1, 4, FILLS["header"])
    r = cmp_row + 2
    current, previous = week.get("current", {}), week.get("previous", {})
    for key, label in (("net", "Netto"), ("cost", "Koszt"), ("margin", "Marża"), ("products", "Aktywne SKU")):
        old = float(previous.get(key, 0) or 0)
        new = float(current.get(key, 0) or 0)
        pct = ((new - old) / old * 100) if old else 0
        dash.cell(r, 1, label)
        dash.cell(r, 2, new).number_format = '#,##0.00' if key != "products" else "0"
        dash.cell(r, 3, old).number_format = '#,##0.00' if key != "products" else "0"
        dash.cell(r, 4, round(pct, 1)).fill = FILLS["up"] if pct >= 0 else FILLS["down"]
        r += 1

    dash.cell(r + 1, 1, "Porównanie miesiąca (netto / koszt / marża)")
    dash.cell(r + 1, 1).font = Font(bold=True, size=13, color="1F4E79")
    dash.cell(r + 2, 1, "Metryka")
    dash.cell(r + 2, 2, "Ten miesiąc")
    dash.cell(r + 2, 3, "Poprzedni")
    dash.cell(r + 2, 4, "Zmiana %")
    _style_header_row(dash, r + 2, 1, 4, FILLS["header"])
    r = r + 3
    m_current, m_previous = month.get("current", {}), month.get("previous", {})
    for key, label in (("net", "Netto"), ("cost", "Koszt"), ("margin", "Marża"), ("products", "Aktywne SKU")):
        old = float(m_previous.get(key, 0) or 0)
        new = float(m_current.get(key, 0) or 0)
        pct = ((new - old) / old * 100) if old else 0
        dash.cell(r, 1, label)
        dash.cell(r, 2, new).number_format = '#,##0.00' if key != "products" else "0"
        dash.cell(r, 3, old).number_format = '#,##0.00' if key != "products" else "0"
        dash.cell(r, 4, round(pct, 1)).fill = FILLS["up"] if pct >= 0 else FILLS["down"]
        r += 1

    top = analytics.get("top_products", []) or week.get("top_products", [])
    top_start = r + 3
    dash.cell(top_start, 1, "Top 10 — sprzedaż netto (bieżący tydzień)")
    dash.cell(top_start, 1).font = Font(bold=True, size=13, color="1F4E79")
    dash.cell(top_start + 1, 1, "SKU")
    dash.cell(top_start + 1, 2, "Nazwa")
    dash.cell(top_start + 1, 3, "Netto")
    _style_header_row(dash, top_start + 1, 1, 3, FILLS["header"])
    for idx, row in enumerate(top, start=top_start + 2):
        dash.cell(idx, 1, row.get("sku", ""))
        dash.cell(idx, 2, row.get("name", ""))
        dash.cell(idx, 3, row.get("net", 0)).number_format = '#,##0.00'
    if top:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Top 10 netto"
        chart.height = 8
        chart.width = 12
        chart.add_data(Reference(dash, min_col=3, min_row=top_start + 1, max_row=top_start + 1 + len(top)), titles_from_data=True)
        chart.set_categories(Reference(dash, min_col=1, min_row=top_start + 2, max_row=top_start + 1 + len(top)))
        dash.add_chart(chart, "F78")

    daily = analytics.get("daily_sales", [])
    if daily:
        d_start = top_start + max(len(top), 1) + 4
        dash.cell(d_start, 1, "Dzień")
        dash.cell(d_start, 2, "Netto")
        _style_header_row(dash, d_start, 1, 2, FILLS["header"])
        for idx, row in enumerate(daily, start=d_start + 1):
            dash.cell(idx, 1, row.get("date"))
            dash.cell(idx, 2, row.get("net", 0)).number_format = '#,##0.00'
        line = LineChart()
        line.title = "Netto dziennie"
        line.height = 8
        line.width = 14
        line.add_data(Reference(dash, min_col=2, min_row=d_start, max_row=d_start + len(daily)), titles_from_data=True)
        line.set_categories(Reference(dash, min_col=1, min_row=d_start + 1, max_row=d_start + len(daily)))
        dash.add_chart(line, "F96")

    for col in range(1, 12):
        dash.column_dimensions[get_column_letter(col)].width = 16
    dash.column_dimensions["B"].width = 18
    dash.column_dimensions["D"].width = 22
    dash.freeze_panes = "A4"
    dash.sheet_properties.tabColor = "C65911"


def export_excel(
    df: pd.DataFrame,
    path: Path,
    analytics: dict | None = None,
    *,
    sales: pd.DataFrame | None = None,
    window_days: int = 365,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    _write_orders_sheet(wb, df, window_days=window_days, sales=sales)
    wb.save(path)
    return path
