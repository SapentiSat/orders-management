from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows


EXPORT_COLUMNS = [
    ("id", "ID"),
    ("sku", "SKU"),
    ("ean", "EAN"),
    ("name", "Nazwa"),
    ("producer", "Producent"),
    ("group", "Grupa"),
    ("active", "Aktywny"),
    ("eol", "EOL"),
    ("stock", "Stan"),
    ("reserved", "Rezerwacje"),
    ("free_stock", "Wolny stan"),
    ("min_qty", "Ilość min"),
    ("moq", "MOQ"),
    ("order_increment", "Order Increment"),
    ("lead_time_days", "LT (dni)"),
    ("qty_sum", "Sprzedaż szt."),
    ("net_sum", "Sprzedaż netto"),
    ("tx_days", "Dni z ruchem"),
    ("daily_avg_qty", "Śr. dzienna"),
    ("cover_days", "Okno pokrycia"),
    ("suggested_qty", "Sugerowana ilość"),
    ("suggested_value", "Wartość sugestii"),
    ("ABC", "ABC"),
    ("XYZ", "XYZ"),
    ("ABC_XYZ", "ABC/XYZ"),
    ("mode", "Tryb"),
    ("note", "Uwagi"),
]


FILLS = {
    "auto-ready": PatternFill("solid", fgColor="C6EFCE"),
    "do weryfikacji": PatternFill("solid", fgColor="FFEB9C"),
    "skip": PatternFill("solid", fgColor="D9D9D9"),
    "header": PatternFill("solid", fgColor="1F4E79"),
}


def export_excel(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c, _ in EXPORT_COLUMNS if c in df.columns]
    view = df[cols].copy()
    mode_order = {"auto-ready": 0, "do weryfikacji": 1, "skip": 2}
    view["_mode_ord"] = view["mode"].map(mode_order).fillna(9)
    view = view.sort_values(by=["_mode_ord", "ABC", "suggested_value"], ascending=[True, True, False])
    view = view.drop(columns=["_mode_ord"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Propozycje"
    headers = [label for key, label in EXPORT_COLUMNS if key in cols]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = FILLS["header"]
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")

    for row in dataframe_to_rows(view, index=False, header=False):
        ws.append(list(row))

    mode_idx = headers.index("Tryb") + 1 if "Tryb" in headers else None
    for r in range(2, ws.max_row + 1):
        if mode_idx:
            mode_val = str(ws.cell(r, mode_idx).value or "")
            fill = FILLS.get(mode_val)
            if fill:
                for c in range(1, ws.max_column + 1):
                    ws.cell(r, c).fill = fill

    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 14
    ws.column_dimensions["D"].width = 28
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # ikony / status sheet summary
    summary = wb.create_sheet("Podsumowanie", 0)
    summary["A1"] = "Orders Management — podsumowanie runu"
    summary["A1"].font = Font(bold=True, size=14)
    counts = view["mode"].value_counts().to_dict() if "mode" in view.columns else {}
    summary["A3"] = "auto-ready"
    summary["B3"] = int(counts.get("auto-ready", 0))
    summary["A4"] = "do weryfikacji"
    summary["B4"] = int(counts.get("do weryfikacji", 0))
    summary["A5"] = "skip"
    summary["B5"] = int(counts.get("skip", 0))
    summary["A7"] = "Suma sugerowanej wartości"
    summary["B7"] = float(view["suggested_value"].sum()) if "suggested_value" in view.columns else 0
    summary["A9"] = "Uwaga"
    summary["B9"] = "Jedna tabela propozycji — filtruj po kolumnie Tryb."

    wb.save(path)
    return path
