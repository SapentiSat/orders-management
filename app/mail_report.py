"""Build and send weekly report e-mails (SMTP + Excel attachment)."""

from __future__ import annotations

import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def _fmt_money(value: float | int | None) -> str:
    try:
        return f"{float(value or 0):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def build_report_html(
    mail_cfg: dict[str, Any],
    *,
    summary: dict[str, Any] | None,
    report_date: str,
    excel_name: str,
    calc_snippet_html: str | None = None,
) -> str:
    intro = (mail_cfg.get("report_body") or "").replace("{date}", report_date).replace(
        "{report_link}", excel_name
    ).replace("{company}", "Suuhouse")
    modes = (summary or {}).get("modes") or {}
    suggested_value = (summary or {}).get("suggested_value_sum", 0)
    auto_ready = int(modes.get("auto-ready", 0))
    review = int(modes.get("do weryfikacji", 0))
    rows = int((summary or {}).get("rows", 0))

    calc_block = ""
    if calc_snippet_html:
        calc_block = (
            f'<div style="background:#fffbeb;border:1px solid #fde68a;'
            f'border-left:4px solid #d97706;border-radius:8px;padding:16px;margin:16px 0">'
            f'<div style="font-size:14px;font-weight:700;color:#92400e;margin-bottom:8px">'
            f"📐 Przykład kalkulacji (jak liczymy sugestię)</div>"
            f"{calc_snippet_html}"
            f'<p style="margin:10px 0 0;font-size:11px;color:#78716c">'
            f"Pełny opis krok po kroku — w załączniku HTML (otwórz w przeglądarce).</p>"
            f"</div>"
        )

    template = mail_cfg.get("report_template") or "professional"
    header_bg = {"professional": "#f8faff", "minimal": "#ffffff", "dark": "#172033"}.get(template, "#f8faff")
    header_color = "#ffffff" if template == "dark" else "#172033"
    logo_bg = "#ffffff" if template == "dark" else "#3267e3"
    logo_color = "#172033" if template == "dark" else "#ffffff"

    return f"""<!DOCTYPE html>
<html><body style="margin:0;background:#edf0f5;font-family:Arial,sans-serif">
  <div style="max-width:560px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden">
    <div style="padding:18px 20px;display:flex;align-items:center;gap:12px;background:{header_bg};border-bottom:1px solid #e6eaf0;color:{header_color}">
      <div style="width:32px;height:32px;border-radius:8px;background:{logo_bg};color:{logo_color};text-align:center;line-height:32px;font-weight:800;font-size:11px">OM</div>
      <div><strong style="display:block;font-size:14px">Orders Management</strong>
      <small style="color:#778398">Cotygodniowy raport — {report_date}</small></div>
    </div>
    <div style="padding:20px;color:#354158;font-size:13px;line-height:1.55">
      {intro}
      <div style="display:flex;gap:8px;margin:16px 0">
        <div style="flex:1;background:#f5f7fb;border-radius:7px;padding:10px;text-align:center">
          <strong style="display:block;font-size:15px">{_fmt_money(suggested_value)} zł</strong>
          <span style="font-size:10px;color:#7a879a">wartość sugestii</span>
        </div>
        <div style="flex:1;background:#f5f7fb;border-radius:7px;padding:10px;text-align:center">
          <strong style="display:block;font-size:15px">{auto_ready}</strong>
          <span style="font-size:10px;color:#7a879a">auto-ready</span>
        </div>
        <div style="flex:1;background:#f5f7fb;border-radius:7px;padding:10px;text-align:center">
          <strong style="display:block;font-size:15px">{review}</strong>
          <span style="font-size:10px;color:#7a879a">do weryfikacji</span>
        </div>
      </div>
      <p style="margin:0 0 8px;color:#59657a">Raport obejmuje <strong>{rows}</strong> SKU. Plik Excel w załączniku.</p>
      {calc_block}
      <p style="text-align:center;color:#99a3b2;font-size:11px;margin-top:20px">
        Raport wygenerowany przez Orders Management · załącznik: {excel_name}
      </p>
    </div>
  </div>
</body></html>"""


def send_report_email(
    mail_cfg: dict[str, Any],
    *,
    excel_path: Path,
    summary: dict[str, Any] | None = None,
    extra_attachments: list[Path] | None = None,
    calc_snippet_html: str | None = None,
) -> dict[str, Any]:
    recipients = [x.strip() for x in (mail_cfg.get("report_recipients") or []) if str(x).strip()]
    if not recipients:
        raise ValueError("Brak odbiorców raportu (Powiadomienia → Odbiorcy)")
    if not mail_cfg.get("smtp_host"):
        raise ValueError("Brak konfiguracji SMTP")
    if not excel_path.exists():
        raise FileNotFoundError(f"Brak pliku Excel: {excel_path}")

    report_date = date.today().isoformat()
    subject = (mail_cfg.get("report_subject") or "Raport zamówień — {date}").replace("{date}", report_date)
    html = build_report_html(
        mail_cfg,
        summary=summary,
        report_date=report_date,
        excel_name=excel_path.name,
        calc_snippet_html=calc_snippet_html,
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_cfg.get("from_addr") or mail_cfg.get("smtp_user") or recipients[0]
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        "Cotygodniowy raport zamówień. Otwórz wiadomość w kliencie HTML albo pobierz załącznik Excel."
    )
    msg.add_alternative(html, subtype="html")

    data = excel_path.read_bytes()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=excel_path.name,
    )

    attached_names = [excel_path.name]
    for path in extra_attachments or []:
        if not path.exists():
            continue
        payload = path.read_bytes()
        if path.suffix.lower() == ".html":
            msg.add_attachment(payload, maintype="text", subtype="html", filename=path.name)
        else:
            msg.add_attachment(payload, maintype="application", subtype="octet-stream", filename=path.name)
        attached_names.append(path.name)

    host = mail_cfg["smtp_host"]
    port = int(mail_cfg.get("smtp_port") or 587)
    user = mail_cfg.get("smtp_user") or ""
    password = mail_cfg.get("smtp_password") or ""

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=60) as client:
            if user:
                client.login(user, password)
            client.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as client:
            client.ehlo()
            if port == 587:
                client.starttls()
                client.ehlo()
            if user:
                client.login(user, password)
            client.send_message(msg)

    return {
        "ok": True,
        "recipients": recipients,
        "subject": subject,
        "excel": excel_path.name,
        "attachments": attached_names,
    }
