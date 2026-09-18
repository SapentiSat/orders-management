from __future__ import annotations

import asyncio
import json
import smtplib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _result(state: str, message: str) -> dict[str, str]:
    return {
        "state": state,
        "message": message,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _smtp(cfg: dict[str, Any]) -> dict[str, str]:
    if not cfg.get("smtp_host"):
        return _result("disabled", "Nie skonfigurowano")
    try:
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587)), timeout=10) as client:
            client.ehlo()
            if int(cfg.get("smtp_port", 587)) == 587:
                client.starttls()
                client.ehlo()
            if cfg.get("smtp_user"):
                client.login(cfg["smtp_user"], cfg.get("smtp_password", ""))
        return _result("active", "Połączenie i logowanie działają")
    except Exception as exc:  # noqa: BLE001
        return _result("error", _safe_error(exc))


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:180]


def _nexo_connector(cfg: dict[str, Any]) -> dict[str, str]:
    from app.connector_client import check_connector

    return check_connector(cfg)


CHECKS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, str]]]] = {
    "smtp": ("mail", _smtp),
    "nexo_connector": ("nexo_connector", _nexo_connector),
}


def check_integrations(cfg: dict[str, Any], status_file: Path) -> dict[str, dict[str, str]]:
    statuses = {}
    for name, (section, checker) in CHECKS.items():
        statuses[name] = checker(cfg.get(section, {}))
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")
    return statuses


def read_statuses(status_file: Path) -> dict[str, dict[str, str]]:
    if status_file.exists():
        try:
            return json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {name: _result("disabled", "Jeszcze nie sprawdzono") for name in CHECKS}


async def monitor_loop(
    load_config: Callable[[], dict[str, Any]],
    status_file: Path,
    *,
    interval_seconds: int = 3600,
) -> None:
    while True:
        await asyncio.to_thread(check_integrations, load_config(), status_file)
        await asyncio.sleep(interval_seconds)
