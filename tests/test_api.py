"""Login safety tests against local fake sites. Run: python -m pytest tests
(needs aiohttp, beautifulsoup4 and pytest; no Home Assistant, no network).

The card number and PIN must never reach any origin other than the library site,
even when the site answers the login with a redirect elsewhere.
"""

import asyncio
import importlib
import sys
import types
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from yarl import URL

# Load api.py and parser.py as a package without importing Home Assistant.
_PKG_DIR = Path(__file__).parents[1] / "custom_components" / "helmet"
_pkg = types.ModuleType("helmet_api_test")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules["helmet_api_test"] = _pkg
api = importlib.import_module("helmet_api_test.api")

CARD, PIN = "1234567890", "9876"
LOGIN_FORM = """<form method="post" action="/MyResearch/Home" id="loginForm">
<input type="hidden" name="csrf" value="abc-123"></form>"""
LOANS = """<div class="myresearch-row">
<a class="record-title" href="/Record/1">Muumipeikko</a><span>Eräpäivä: 3.12.2026</span>
</div>"""


class FakeSite:
    """A local web server that records every request and its body."""

    def __init__(self, routes):
        self.requests: list[tuple[str, str, str]] = []
        self._routes = routes
        self._runner = None
        self.origin = None

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        body = await request.text()
        self.requests.append((request.method, request.path, body))
        handler = self._routes.get((request.method, request.path))
        if handler is None:
            return web.Response(status=404)
        return handler(self, request)

    async def __aenter__(self):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        port = self._runner.addresses[0][1]
        self.origin = URL(f"http://127.0.0.1:{port}")
        return self

    async def __aexit__(self, *exc):
        await self._runner.cleanup()

    def saw_credentials(self) -> bool:
        return any(CARD in body or PIN in body for _, _, body in self.requests)


def _html(text: str) -> web.Response:
    return web.Response(text=text, content_type="text/html")


def helmet_routes(login_post=None):
    """Routes of a working library site; login_post overrides the login answer."""
    return {
        ("GET", "/MyResearch/UserLogin"): lambda s, r: _html(LOGIN_FORM),
        ("POST", "/MyResearch/Home"): login_post or (lambda s, r: _html("<p>Omat tiedot</p>")),
        ("GET", "/MyResearch/Home"): lambda s, r: _html("<p>Omat tiedot</p>"),
        ("GET", "/AJAX/JSON"): lambda s, r: web.json_response(
            {"data": {"ok": 1, "warn": 0, "overdue": 0, "total": 1,
                      "available": 0, "in_transit": 0, "other": 0}}
        ),
        ("GET", "/MyResearch/CheckedOut"): lambda s, r: _html(LOANS),
        ("GET", "/Holds/List"): lambda s, r: _html(""),
        ("GET", "/MyResearch/Logout"): redirect(302, "/"),
        ("GET", "/"): lambda s, r: _html("home"),
    }


def redirect(status: int, location):
    return lambda site, request: web.Response(status=status, headers={"Location": str(location)})


async def _fetch(monkeypatch, helmet: FakeSite):
    monkeypatch.setattr(api, "_ORIGIN", helmet.origin)
    return await api.HelmetClient(CARD, PIN).fetch()


def test_plain_login_still_works(monkeypatch):
    async def run():
        async with FakeSite(helmet_routes()) as helmet:
            data = await _fetch(monkeypatch, helmet)
            assert [loan.title for loan in data.loans] == ["Muumipeikko"]
            assert ("POST", "/MyResearch/Home") in [r[:2] for r in helmet.requests]
            assert helmet.requests[-1][:2] == ("GET", "/")  # logged out

    asyncio.run(run())


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_within_site_is_followed_without_the_form(monkeypatch, status):
    async def run():
        async with FakeSite(helmet_routes(redirect(status, "/MyResearch/Home"))) as helmet:
            data = await _fetch(monkeypatch, helmet)
            assert data.loans_total == 1
            followed = [r for r in helmet.requests if r[:2] == ("GET", "/MyResearch/Home")]
            assert followed == [("GET", "/MyResearch/Home", "")]
            posts = [r for r in helmet.requests if r[0] == "POST"]
            assert len(posts) == 1  # the form was sent once, to the site only

    asyncio.run(run())


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_login_redirect_to_another_site_is_refused(monkeypatch, status):
    async def run():
        async with FakeSite({}) as evil:
            evil_url = evil.origin / "steal"
            async with FakeSite(helmet_routes(redirect(status, evil_url))) as helmet:
                with pytest.raises(api.HelmetError, match="another site"):
                    await _fetch(monkeypatch, helmet)
            assert evil.requests == []

    asyncio.run(run())


def test_page_redirect_to_another_site_is_refused(monkeypatch):
    async def run():
        async with FakeSite({}) as evil:
            routes = helmet_routes()
            routes[("GET", "/MyResearch/CheckedOut")] = redirect(302, evil.origin / "x")
            async with FakeSite(routes) as helmet:
                with pytest.raises(api.HelmetError, match="another site"):
                    await _fetch(monkeypatch, helmet)
            # aiohttp follows GET redirects itself; only a bodiless GET can get there.
            assert not evil.saw_credentials()

    asyncio.run(run())


def test_invalid_login_redirect_is_a_helmet_error(monkeypatch):
    async def run():
        async with FakeSite(helmet_routes(redirect(302, "http://[bad"))) as helmet:
            with pytest.raises(api.HelmetError, match="invalid redirect"):
                await _fetch(monkeypatch, helmet)

    asyncio.run(run())


def test_redirect_loop_after_login_stops(monkeypatch):
    async def run():
        routes = helmet_routes(redirect(302, "/MyResearch/Home"))
        routes[("GET", "/MyResearch/Home")] = redirect(302, "/MyResearch/Home")
        async with FakeSite(routes) as helmet:
            with pytest.raises(api.HelmetError, match="Too many redirects"):
                await _fetch(monkeypatch, helmet)

    asyncio.run(run())


def test_without_the_guard_aiohttp_would_leak_the_pin():
    """Shows why the guard exists: aiohttp resends the form on 307 to any host."""

    async def run():
        async with FakeSite({("POST", "/steal"): lambda s, r: _html("thanks")}) as evil:
            async with FakeSite(helmet_routes(redirect(307, evil.origin / "steal"))) as helmet:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        helmet.origin / "MyResearch" / "Home",
                        data={"username": CARD, "password": PIN},
                    ) as resp:
                        await resp.text()
            assert evil.saw_credentials()

    asyncio.run(run())
