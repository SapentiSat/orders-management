from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SECRET_KEYS = {
    "password",
    "smtp_password",
    "api_key",
    "access_token",
    "license_key",
    "secret",
}


def append_log(
    logs_dir: Path,
    level: str,
    message: str,
    context: dict[str, Any] | None = None,
    *,
    category: str = "system",
) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = logs_dir / f"{day}.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "category": category,
        "message": message,
        "context": context or {},
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in SECRET_KEYS or "password" in k.lower() or "token" in k.lower() or "key" in k.lower() else _mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


def diff_settings(before: dict[str, Any], after: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    keys = sorted(set(before) | set(after))
    for key in keys:
        path = f"{prefix}.{key}" if prefix else key
        old = before.get(key)
        new = after.get(key)
        if isinstance(old, dict) and isinstance(new, dict):
            changes.extend(diff_settings(old, new, path))
            continue
        if old != new:
            secret = key.lower() in SECRET_KEYS or "password" in key.lower() or "token" in key.lower() or "key" in key.lower()
            changes.append(
                {
                    "field": path,
                    "from": "***" if secret and old not in (None, "", []) else _mask(old),
                    "to": "***" if secret and new not in (None, "", []) else _mask(new),
                }
            )
    return changes


def log_changes(
    logs_dir: Path,
    *,
    area: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    changes = diff_settings(before, after)
    if not changes:
        append_log(logs_dir, "INFO", f"Zapis {area}: brak zmian", {"area": area}, category="change")
        return
    append_log(
        logs_dir,
        "CHANGE",
        f"Zmieniono ustawienia: {area} ({len(changes)} pól)",
        {"area": area, "changes": changes[:80], "count": len(changes)},
        category="change",
    )


def read_recent_logs(
    logs_dir: Path,
    *,
    days: int = 30,
    levels: set[str] | None = None,
    category: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    if not logs_dir.exists():
        return []
    levels = {x.upper() for x in (levels or {"WARN", "ERROR", "INFO", "CHANGE"})}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for path in sorted(logs_dir.glob("*.jsonl")):
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("level", "").upper() not in levels:
                        continue
                    if category and item.get("category", "system") != category:
                        continue
                    ts = datetime.fromisoformat(item["ts"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        rows.append(item)
        except Exception:
            continue
    rows.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return rows[:limit]
