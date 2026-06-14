#!/usr/bin/env python3
"""Migrate Bulbul agent_persona rows from Supabase into Goa memory.

Goa memory is owner-scoped to the authenticated participant, so per-user
persona values are namespaced into keys:

    user:{user_id}:persona:{key}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

import httpx
from dotenv import load_dotenv
from supabase import create_client


PAGE_SIZE = 500
DEFAULT_GOA_URL = "http://195.35.0.64"


def load_env() -> None:
    for path in (".env", "/app/.env"):
        if os.path.exists(path):
            load_dotenv(path)
            return
    load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def deserialize_supabase_value(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def goa_key(row: dict[str, Any]) -> str:
    return f"user:{row['user_id']}:persona:{row['key']}"


def goa_value(row: dict[str, Any], migrated_at: str, value_shape: str) -> Any:
    value = deserialize_supabase_value(row.get("value"))
    if value_shape == "direct":
        return value

    return {
        "type": "agent_persona_value",
        "source": "supabase.agent_persona",
        "user_id": str(row["user_id"]),
        "key": str(row["key"]),
        "value": value,
        "supabase_updated_at": row.get("updated_at"),
        "migrated_at": migrated_at,
    }


def goa_tags(row: dict[str, Any]) -> list[str]:
    tags = ["bulbul", "persona", "migrated", "source:supabase"]
    key_tag = f"persona:{row['key']}"
    if len(key_tag) <= 64:
        tags.append(key_tag)
    user_tag = f"user:{row['user_id']}"
    if len(user_tag) <= 64:
        tags.append(user_tag)
    return tags


def fetch_supabase_persona() -> list[dict[str, Any]]:
    supabase = create_client(
        require_env("SUPABASE_URL"),
        require_env("SUPABASE_SERVICE_KEY"),
    )

    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        result = (
            supabase.table("agent_persona")
            .select("*")
            .order("user_id")
            .order("key")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        page = result.data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return rows


class GoaMemoryClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def upsert(self, row: dict[str, Any], migrated_at: str, value_shape: str) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/memory",
            json={
                "key": goa_key(row),
                "value": goa_value(row, migrated_at, value_shape),
                "tags": goa_tags(row),
            },
        )
        raise_for_goa_status(response, "upsert Goa persona")
        return response.json()

    def get_key(self, key: str) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.base_url}/memory", params={"key": key})
        raise_for_goa_status(response, "read Goa persona")
        return response.json().get("entries", [])

    def verify_row(self, row: dict[str, Any]) -> tuple[bool, str]:
        key = goa_key(row)
        entries = self.get_key(key)
        if len(entries) != 1:
            return False, f"{key}: expected 1 Goa entry, found {len(entries)}"

        stored = entries[0].get("value")
        expected = deserialize_supabase_value(row.get("value"))
        if isinstance(stored, dict) and stored.get("type") == "agent_persona_value":
            if stored.get("value") != expected:
                return False, f"{key}: value mismatch"
            if str(stored.get("user_id")) != str(row["user_id"]):
                return False, f"{key}: user_id mismatch"
            if str(stored.get("key")) != str(row["key"]):
                return False, f"{key}: key mismatch"
            return True, key

        if stored != expected:
            return False, f"{key}: value mismatch"

        return True, key

    def close(self) -> None:
        self.client.close()


def raise_for_goa_status(response: httpx.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text.strip()
        raise RuntimeError(
            f"Failed to {action}: HTTP {response.status_code} {response.reason_phrase}"
            f"\nURL: {response.request.url}"
            f"\nResponse: {body or '<empty>'}"
        ) from exc


def preflight_goa_memory(base_url: str, api_key: str) -> None:
    client = httpx.Client(
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        response = client.get(f"{base_url.rstrip('/')}/memory", params={"key": "__bulbul_preflight__"})
        raise_for_goa_status(response, "preflight Goa memory")
        try:
            data = response.json()
        except JSONDecodeError as exc:
            body = response.text.strip()
            raise RuntimeError(
                "Goa /memory preflight did not return JSON."
                f"\nURL: {response.request.url}"
                f"\nContent-Type: {response.headers.get('content-type', '<missing>')}"
                f"\nResponse: {body[:500] or '<empty>'}"
            ) from exc

        if not isinstance(data, dict) or "entries" not in data:
            raise RuntimeError("Goa /memory preflight returned an unexpected response shape.")
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Supabase agent_persona values into Goa /memory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read Supabase and print which persona keys would be migrated without writing values to Goa.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not write; verify that Supabase rows already exist in Goa.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check that Goa /memory returns the expected JSON shape.",
    )
    parser.add_argument(
        "--goa-url",
        default=os.getenv("GOA_URL", DEFAULT_GOA_URL),
        help=f"Goa base URL. Defaults to GOA_URL or {DEFAULT_GOA_URL}.",
    )
    parser.add_argument(
        "--goa-api-key-env",
        default="GOA_AGENT_API_KEY" if os.getenv("GOA_AGENT_API_KEY") else "GOA_API_KEY",
        help=(
            "Environment variable containing the Goa participant API key that "
            "should own the migrated persona. Defaults to GOA_AGENT_API_KEY if "
            "set, otherwise GOA_API_KEY."
        ),
    )
    parser.add_argument(
        "--value-shape",
        choices=["rich", "direct"],
        default="rich",
        help=(
            "How to store Goa persona values. 'rich' stores a JSON object with "
            "migration metadata. 'direct' stores the persona value directly."
        ),
    )
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()

    goa_api_key = require_env(args.goa_api_key_env)
    print(f"Using Goa API key from {args.goa_api_key_env}.")
    preflight_goa_memory(args.goa_url, goa_api_key)

    if args.preflight_only:
        print("Goa /memory preflight passed.")
        return 0

    rows = fetch_supabase_persona()
    print(f"Found {len(rows)} Supabase agent_persona row(s).")

    if args.dry_run:
        for row in rows:
            print(f"DRY RUN {goa_key(row)}")
        return 0

    goa = GoaMemoryClient(args.goa_url, goa_api_key)
    migrated_at = datetime.now(timezone.utc).isoformat()
    try:
        if not args.verify_only:
            created_or_updated = 0
            for row in rows:
                goa.upsert(row, migrated_at, args.value_shape)
                created_or_updated += 1
            print(
                f"Upserted {created_or_updated} row(s) into Goa persona "
                f"using {args.value_shape!r} values."
            )

        verified = 0
        failures: list[str] = []
        for row in rows:
            ok, message = goa.verify_row(row)
            if ok:
                verified += 1
            else:
                failures.append(message)

        print(f"Verified {verified}/{len(rows)} Goa persona row(s).")
        if failures:
            print("Verification failures:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1

        return 0
    finally:
        goa.close()


if __name__ == "__main__":
    raise SystemExit(main())
