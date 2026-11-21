"""Client address behind reverse proxies — what the login rate limit is keyed on."""

from __future__ import annotations

import pytest
from flask import Flask, request

from app import create_app

CLIENT = "203.0.113.7"
CADDY = "172.18.0.5"
NGINX = "172.18.0.6"


def _app_with_proxies(monkeypatch: pytest.MonkeyPatch, count: int) -> Flask:
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", str(count))
    app = create_app()

    @app.get("/_test/remote-addr")
    def remote_addr() -> str:
        return request.remote_addr or ""

    return app


def _seen_address(app: Flask, forwarded_for: str | None) -> str:
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    response = app.test_client().get(
        "/_test/remote-addr", headers=headers, environ_base={"REMOTE_ADDR": NGINX}
    )
    return response.get_data(as_text=True)


def test_behind_caddy_and_nginx_the_client_address_is_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_proxies(monkeypatch, 2)
    assert _seen_address(app, f"{CLIENT}, {CADDY}") == CLIENT


def test_a_client_cannot_choose_its_address_by_prepending_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The client sent "X-Forwarded-For: 1.1.1.1"; the proxies appended the real hops after it.
    app = _app_with_proxies(monkeypatch, 2)
    assert _seen_address(app, f"1.1.1.1, {CLIENT}, {CADDY}") == CLIENT


def test_without_trusted_proxies_the_header_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_proxies(monkeypatch, 0)
    assert _seen_address(app, f"1.1.1.1, {CLIENT}") == NGINX
