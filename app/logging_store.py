from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def append_log(logs_dir: Path, level: str, message: str, context: dict[str, Any] | None = None) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = logs_dir / f"{day}.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "message": message,
        "context": context or {},
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_recent_logs(logs_dir: Path, *, days: int = 14, levels: set[str] | None = None) -> list[dict[str, Any]]:
    if not logs_dir.exists():
        return []
    levels = {x.upper() for x in (levels or {"WARN", "ERROR", "INFO"})}
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
                    ts = datetime.fromisoformat(item["ts"])
                    if ts >= cutoff:
                        rows.append(item)
        except Exception:
            continue
    rows.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return rows[:500]
