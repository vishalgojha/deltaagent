#!/usr/bin/env python3
"""Post-deploy smoke checks for DeltaAgent API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request_json(method: str, url: str, data: dict | None = None, timeout: int = 10) -> tuple[int, dict | str]:
    payload = None
    headers = {}
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return exc.code, body
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run post-deploy smoke checks against DeltaAgent backend.")
    parser.add_argument("--base-url", required=True, help="Backend base URL, for example https://your-app.onrender.com")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail if /health/ready is not 200.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    checks: list[tuple[str, bool, str]] = []

    status, body = request_json("GET", f"{base_url}/health")
    checks.append(("/health", status == 200 and body.get("status") == "ok", f"status={status} body={body}"))

    status, body = request_json("GET", f"{base_url}/openapi.json")
    has_strategy_paths = False
    if status == 200 and isinstance(body, dict):
        paths = body.get("paths", {})
        has_strategy_paths = all(
            endpoint in paths
            for endpoint in (
                "/strategy-template",
                "/strategy-template/{template_id}",
                "/strategy-template/{template_id}/resolve",
                "/strategy-template/{template_id}/execute",
            )
        )
    checks.append(("/openapi.json strategy endpoints", status == 200 and has_strategy_paths, f"status={status}"))

    ready_status, ready_body = request_json("GET", f"{base_url}/health/ready")
    ready_ok = ready_status == 200
    ready_reachable = ready_status in (200, 503)
    checks.append(
        (
            "/health/ready",
            ready_reachable and (ready_ok or (not args.require_ready)),
            f"status={ready_status} body={ready_body}",
        )
    )

    print("Smoke check results:")
    failures = 0
    for name, ok, detail in checks:
        badge = "PASS" if ok else "FAIL"
        print(f"- {badge}: {name} ({detail})")
        if not ok:
            failures += 1

    if failures:
        print(f"Smoke checks failed: {failures} failed checks.")
        return 2
    print("Smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
