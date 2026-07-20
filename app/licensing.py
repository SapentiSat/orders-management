"""Commercial license key issue / verify (HMAC-signed, proprietary)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any


KEY_PREFIX = "OM1"


@dataclass
class LicensePayload:
    customer: str
    email: str = ""
    edition: str = "standard"  # trial | standard | pro
    expires: str = ""  # YYYY-MM-DD, empty = no expiry
    max_skus: int = 5000
    features: list[str] | None = None
    issued: str = ""

    def __post_init__(self) -> None:
        if self.features is None:
            self.features = ["core", "excel", "abc_xyz", "panel"]
        if not self.issued:
            self.issued = date.today().isoformat()


@dataclass
class LicenseStatus:
    valid: bool
    reason: str
    payload: LicensePayload | None = None
    mode: str = "unlicensed"  # unlicensed | trial | licensed
    demo_limits: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "mode": self.mode,
            "payload": asdict(self.payload) if self.payload else None,
            "demo_limits": self.demo_limits,
        }


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def issue_license(payload: LicensePayload, signing_secret: str) -> str:
    body = {
        "customer": payload.customer,
        "email": payload.email,
        "edition": payload.edition,
        "expires": payload.expires,
        "max_skus": int(payload.max_skus),
        "features": payload.features or [],
        "issued": payload.issued or date.today().isoformat(),
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(signing_secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return f"{KEY_PREFIX}.{_b64url_encode(raw)}.{_b64url_encode(sig)}"


def verify_license(license_key: str, signing_secret: str, *, now: date | None = None) -> LicenseStatus:
    demo = {
        "max_skus": 50,
        "features": ["core", "excel", "abc_xyz", "panel"],
        "note": "Tryb testowy bez ważnej licencji — limit 50 SKU, dane sample.",
    }

    key = (license_key or "").strip()
    if not key:
        return LicenseStatus(
            valid=False,
            reason="Brak klucza licencji — działa tryb testowy (ograniczony).",
            mode="unlicensed",
            demo_limits=demo,
        )

    parts = key.split(".")
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        return LicenseStatus(
            valid=False,
            reason="Nieprawidłowy format klucza licencji.",
            mode="unlicensed",
            demo_limits=demo,
        )

    try:
        raw = _b64url_decode(parts[1])
        sig = _b64url_decode(parts[2])
    except Exception:
        return LicenseStatus(
            valid=False,
            reason="Nie można odczytać klucza licencji.",
            mode="unlicensed",
            demo_limits=demo,
        )

    expected = hmac.new(signing_secret.encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return LicenseStatus(
            valid=False,
            reason="Podpis klucza nieprawidłowy (zły sekret lub klucz sfałszowany).",
            mode="unlicensed",
            demo_limits=demo,
        )

    try:
        body = json.loads(raw.decode("utf-8"))
        payload = LicensePayload(
            customer=str(body.get("customer", "")),
            email=str(body.get("email", "")),
            edition=str(body.get("edition", "standard")),
            expires=str(body.get("expires", "")),
            max_skus=int(body.get("max_skus", 5000)),
            features=list(body.get("features") or []),
            issued=str(body.get("issued", "")),
        )
    except Exception:
        return LicenseStatus(
            valid=False,
            reason="Uszkodzona treść licencji.",
            mode="unlicensed",
            demo_limits=demo,
        )

    today = now or datetime.now(timezone.utc).date()
    if payload.expires:
        try:
            exp = date.fromisoformat(payload.expires)
        except ValueError:
            return LicenseStatus(
                valid=False,
                reason="Nieprawidłowa data wygaśnięcia w licencji.",
                mode="unlicensed",
                demo_limits=demo,
            )
        if today > exp:
            return LicenseStatus(
                valid=False,
                reason=f"Licencja wygasła {payload.expires}.",
                mode="unlicensed",
                payload=payload,
                demo_limits=demo,
            )

    mode = "trial" if payload.edition == "trial" else "licensed"
    return LicenseStatus(valid=True, reason="OK", payload=payload, mode=mode)


def effective_max_skus(status: LicenseStatus) -> int:
    if status.valid and status.payload:
        return int(status.payload.max_skus)
    if status.demo_limits:
        return int(status.demo_limits.get("max_skus", 50))
    return 50
