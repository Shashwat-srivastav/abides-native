#!/usr/bin/env python3
"""Build submission.zip (submission.json + team-claim.json) per the CodaBench T3
Submission Format page.

Run this yourself in a real interactive terminal. It prompts for the Team Key via
getpass (hidden input, never a CLI arg or env var) and never writes it to disk.
Do NOT run this through a tool/agent session whose commands or output get logged --
type the key at a terminal you control.

What it does:
  1. Reads the existing submission.json (source of truth for everything except team_id).
  2. Derives team_id from your team number + Team Key and writes it into the descriptor.
  3. Reseals descriptor_digest via qfbench2_common (RFC 8785 canonical digest).
  4. Computes the team-claim.json proof (HMAC over the sealed descriptor's exact bytes).
  5. Writes submission.zip (mode 0600) containing submission.json + team-claim.json.
  6. Updates the on-disk submission.json with the resealed body (team_id is not secret;
     the Team Key itself is never written anywhere).
"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON = HERE.parent / "toolkit-v2.5.1" / "common"  # fetched by scripts/fetch_upstream.sh
sys.path.insert(0, str(COMMON))

from qfbench2_common.contracts.descriptor import seal_descriptor_digest  # noqa: E402

TEAM_NUMBER = 36  # Team 36 (S2WISH), per agenthon.net registration
SOURCE_DESCRIPTOR = HERE / "submission.json"
OUTPUT_ZIP = HERE / "submission.zip"


def main() -> None:
    team_key = getpass.getpass("Team Key (from agenthon.net, hidden): ")
    if not team_key:
        raise SystemExit("empty Team Key")

    team_id = "team-" + hashlib.sha256(
        f"agenthon2026-team-alias:{TEAM_NUMBER}:{team_key}".encode()
    ).hexdigest()[:32]

    body = json.loads(SOURCE_DESCRIPTOR.read_text())
    body["team_id"] = team_id
    sealed = seal_descriptor_digest(body)

    # The claim binds to the *exact bytes* the zip will carry, so build them first.
    descriptor_bytes = (json.dumps(sealed, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor_sha256 = hashlib.sha256(descriptor_bytes).hexdigest()

    proof_key = hashlib.sha256(f"agenthon2026-team-proof-key:v2:{team_key}".encode()).digest()
    message = f"agenthon2026-team-claim:v2:{TEAM_NUMBER}:{descriptor_sha256}".encode()
    proof = hmac.new(proof_key, message, hashlib.sha256).hexdigest()

    claim = {
        "schema_version": "2.0",
        "site_team_id": TEAM_NUMBER,
        "descriptor_sha256": descriptor_sha256,
        "proof": proof,
    }

    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    fd = os.open(OUTPUT_ZIP, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with zipfile.ZipFile(os.fdopen(fd, "wb"), "w") as archive:
        archive.writestr("submission.json", descriptor_bytes)
        archive.writestr(
            "team-claim.json", json.dumps(claim, separators=(",", ":"), sort_keys=True)
        )

    SOURCE_DESCRIPTOR.write_text(json.dumps(sealed, indent=2) + "\n")

    print(f"wrote {OUTPUT_ZIP}")
    print(f"team_id = {team_id}")
    print(f"updated {SOURCE_DESCRIPTOR} with the resealed descriptor")


if __name__ == "__main__":
    main()
