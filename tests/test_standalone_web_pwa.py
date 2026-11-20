# -*- coding: utf-8 -*-
"""Tests for standalone browser Web App & PWA serving (manifest, sw.js, icon, SPA fallback)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app


def _build_mock_static_dir(tmp_path: Path) -> Path:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        '<!doctype html><html><head><link rel="manifest" href="/manifest.webmanifest" />'
        '<script type="module" src="/assets/app.js"></script></head><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('dsa-web');", encoding="utf-8")
    (static_dir / "manifest.webmanifest").write_text(
        json.dumps({"name": "DSA Quant", "display": "standalone", "start_url": "/discover"}),
        encoding="utf-8",
    )
    (static_dir / "sw.js").write_text("self.addEventListener('fetch', () => {});", encoding="utf-8")
    (static_dir / "dsa-icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    return static_dir


def test_standalone_pwa_assets_and_spa_deep_routes(tmp_path: Path) -> None:
    static_dir = _build_mock_static_dir(tmp_path)
    app = create_app(static_dir=static_dir)
    client = TestClient(app)

    # PWA manifest served with proper MIME & no-cache
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "application/manifest+json" in manifest.headers["content-type"]
    assert "no-cache" in manifest.headers.get("cache-control", "")
    assert manifest.json()["display"] == "standalone"

    # Service Worker served with JS MIME, no-cache, and root scope permission
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "javascript" in sw.headers["content-type"]
    assert "no-cache" in sw.headers.get("cache-control", "")
    assert sw.headers.get("service-worker-allowed") == "/"

    # Branded SVG icon served with image/svg+xml
    icon = client.get("/dsa-icon.svg")
    assert icon.status_code == 200
    assert "image/svg+xml" in icon.headers["content-type"]

    # Deep browser routes resolve to SPA index.html (no 404 on refresh)
    for route in ("/", "/discover", "/paper-trading", "/chat", "/settings"):
        res = client.get(route)
        assert res.status_code == 200
        assert "manifest.webmanifest" in res.text
        assert "no-store" in res.headers.get("cache-control", "")

    # Unknown API paths must stay strict JSON 404 (never fall back to index.html)
    api_miss = client.get("/api/v1/does-not-exist")
    assert api_miss.status_code == 404
    assert "application/json" in api_miss.headers["content-type"]
