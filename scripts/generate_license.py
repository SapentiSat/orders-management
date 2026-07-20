"""Vendor CLI: issue commercial license keys (keep signing secret private)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.licensing import LicensePayload, issue_license  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Issue Orders Management license key")
    p.add_argument("--secret", required=True, help="LICENSE_SIGNING_SECRET (vendor only)")
    p.add_argument("--customer", required=True)
    p.add_argument("--email", default="")
    p.add_argument("--edition", default="standard", choices=["trial", "standard", "pro"])
    p.add_argument("--expires", default="", help="YYYY-MM-DD or empty")
    p.add_argument("--max-skus", type=int, default=5000)
    args = p.parse_args()

    key = issue_license(
        LicensePayload(
            customer=args.customer,
            email=args.email,
            edition=args.edition,
            expires=args.expires,
            max_skus=args.max_skus,
        ),
        args.secret,
    )
    print(key)


if __name__ == "__main__":
    main()
