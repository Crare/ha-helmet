"""Client that signs in to helmet.finna.fi and reads loans and reservations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import BASE_URL, LIBRARY_TARGET
from .parser import (
    Hold,
    parse_alerts,
    Loan,
    is_login_form,
    parse_csrf,
    parse_hold_summary,
    parse_holds,
    parse_loan_summary,
    parse_loans,
)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
# helmet.finna.fi answers 403 to crawler-style user agents (brackets, links,
# "compatible;", default Python/curl ones). A plain product token is accepted
# and still says honestly which client this is.
_HEADERS = {"User-Agent": "HomeAssistant-Helmet/0.1.2", "Accept-Language": "fi"}


class HelmetError(Exception):
    """The library site could not be read."""


class HelmetAuthError(HelmetError):
    """The card number or PIN was rejected."""


@dataclass(frozen=True)
class HelmetData:
    """Loans and reservations from one update."""

    loans: list[Loan]
    loans_total: int
    loans_due_soon: int
    loans_overdue: int
    holds: list[Hold]
    holds_ready: int


class HelmetClient:
    """Signs in fresh on every fetch, so no session state is kept between polls."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    async def fetch(self) -> HelmetData:
        """Sign in, read loans and reservations, and sign out."""
        try:
            async with aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(), headers=_HEADERS, timeout=_TIMEOUT
            ) as session:
                await self._login(session)
                try:
                    return await self._read(session)
                finally:
                    await self._get(session, "/MyResearch/Logout")
        except aiohttp.ClientResponseError as err:
            if err.status == 403:
                raise HelmetError(
                    f"{BASE_URL} refused the request (403); it may be blocking "
                    "this client"
                ) from err
            raise HelmetError(f"{BASE_URL} answered {err.status}") from err
        except aiohttp.ClientError as err:
            raise HelmetError(f"Could not reach {BASE_URL}: {err}") from err

    async def _get(self, session: aiohttp.ClientSession, path: str) -> str:
        async with session.get(f"{BASE_URL}{path}") as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _ajax(self, session: aiohttp.ClientSession, method: str) -> Any:
        async with session.get(f"{BASE_URL}/AJAX/JSON", params={"method": method}) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _login(self, session: aiohttp.ClientSession) -> None:
        csrf = parse_csrf(
            await self._get(session, "/MyResearch/UserLogin?layout=lightbox&lng=fi")
        )
        if csrf is None:
            raise HelmetError("Login form not found; the site may have changed")
        form = {
            "target": LIBRARY_TARGET,
            "username": self._username,
            "password": self._password,
            "auth_method": "MultiILS",
            "csrf": csrf,
            "processLogin": "Kirjaudu",
        }
        async with session.post(f"{BASE_URL}/MyResearch/Home", data=form) as resp:
            resp.raise_for_status()
            page = await resp.text()
            if is_login_form(page):
                message = "; ".join(parse_alerts(page)) or "no message"
                raise HelmetAuthError(f"Helmet did not accept the login: {message}")

    async def _read(self, session: aiohttp.ClientSession) -> HelmetData:
        loan_counts = parse_loan_summary(await self._ajax(session, "getUserTransactions"))
        hold_counts = parse_hold_summary(await self._ajax(session, "getUserHolds"))
        if loan_counts is None or hold_counts is None:
            raise HelmetAuthError("Not signed in after login")
        return HelmetData(
            loans=parse_loans(await self._get(session, "/MyResearch/CheckedOut?lng=fi")),
            loans_total=loan_counts["total"],
            loans_due_soon=loan_counts["warn"],
            loans_overdue=loan_counts["overdue"],
            holds=parse_holds(await self._get(session, "/Holds/List?lng=fi")),
            holds_ready=hold_counts["available"],
        )
