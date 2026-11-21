#!/usr/bin/env python3
"""Post-deploy smoke test. Standard library only, so it runs on a bare CI runner or server.

    python scripts/smoke_test.py https://staging.example.com --expect-commit "$GITHUB_SHA"

Checks, in order, and fails fast on the first that does not hold:

1. /api/v1/health answers 200 within --timeout seconds (the container came up).
2. /api/v1/ready answers 200 (database reachable, schema at this build's migration head).
3. /api/v1/version reports --expect-commit, when given (the NEW build is serving, not the
   old one that a failed rollout left running).
4. The frontend root serves HTML (Nginx is routing to the SPA).

Exit status 0 means every check passed; anything else is a failed deploy.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

API_PREFIX = "/api/v1"


@dataclass(frozen=True, slots=True)
class HttpResult:
    status: int
    body: str
    content_type: str

    def json(self) -> dict[str, Any]:
        return json.loads(self.body)


class SmokeTestFailure(Exception):
    pass


def fetch(url: str, *, timeout: float = 10.0) -> HttpResult:
    request = urllib.request.Request(url, headers={"Accept": "application/json, text/html"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(
                status=response.status,
                body=response.read().decode("utf-8", errors="replace"),
                content_type=response.headers.get("Content-Type", ""),
            )
    except urllib.error.HTTPError as error:
        return HttpResult(
            status=error.code,
            body=error.read().decode("utf-8", errors="replace"),
            content_type=error.headers.get("Content-Type", "") if error.headers else "",
        )


def wait_for_health(base_url: str, *, timeout: float, interval: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            result = fetch(f"{base_url}{API_PREFIX}/health")
            if result.status == 200:
                print(f"ok   health ({result.status})")
                return
            last_error = f"HTTP {result.status}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = str(error)
        time.sleep(interval)
    raise SmokeTestFailure(f"health never returned 200 within {timeout:.0f}s: {last_error}")


def check_ready(base_url: str) -> None:
    result = fetch(f"{base_url}{API_PREFIX}/ready")
    if result.status != 200:
        raise SmokeTestFailure(f"ready returned {result.status}: {result.body}")
    print(f"ok   ready (schema at {result.json().get('applied_revisions')})")


def check_version(base_url: str, expect_commit: str | None) -> None:
    result = fetch(f"{base_url}{API_PREFIX}/version")
    if result.status != 200:
        raise SmokeTestFailure(f"version returned {result.status}: {result.body}")
    info = result.json()
    commit = str(info.get("commit", ""))
    # Accept a short SHA on either side: images are tagged with the full SHA, people type 7.
    if expect_commit and not (commit.startswith(expect_commit) or expect_commit.startswith(commit)):
        raise SmokeTestFailure(f"expected commit {expect_commit}, serving {commit or 'unknown'}")
    print(f"ok   version {info.get('version')} @ {commit}")


def check_frontend(base_url: str) -> None:
    result = fetch(f"{base_url}/")
    if result.status != 200 or "html" not in result.content_type:
        raise SmokeTestFailure(f"frontend root returned {result.status} ({result.content_type})")
    print("ok   frontend")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url", help="e.g. https://staging.example.com (no trailing slash)")
    parser.add_argument("--expect-commit", default=None, help="git SHA the deploy should serve")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for health")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between attempts")
    parser.add_argument("--skip-frontend", action="store_true", help="API-only deployments")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_url: str = args.base_url.rstrip("/")
    try:
        wait_for_health(base_url, timeout=args.timeout, interval=args.interval)
        check_ready(base_url)
        check_version(base_url, args.expect_commit)
        if not args.skip_frontend:
            check_frontend(base_url)
    except SmokeTestFailure as failure:
        print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
