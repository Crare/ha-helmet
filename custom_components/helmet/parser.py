"""Pure HTML/JSON parsing for helmet.finna.fi pages (no Home Assistant imports)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup, Tag

_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
# Labels in Finnish, English and Swedish, since the page language can vary.
_DUE_LABEL_RE = re.compile(r"eräpäivä|due|förfallodag", re.IGNORECASE)
_PICKUP_BY_RE = re.compile(
    r"viimeistään|noudettava|pick ?up by|last pick ?up|senast|avhämtas", re.IGNORECASE
)
_READY_RE = re.compile(
    r"noudettavissa|available for pick ?up|ready for pick ?up|kan avhämtas|"
    r"finns att hämta",
    re.IGNORECASE,
)
_ROW_SELECTORS = ".myresearch-row, li.result, div.result, tr.myresearch-row"
_TITLE_SELECTORS = ".record-title, a.title, .title, h2 a, h3 a, h2, h3"


@dataclass(frozen=True)
class Loan:
    """One checked-out item."""

    title: str
    due_date: date | None


@dataclass(frozen=True)
class Hold:
    """One reservation; pickup_by is set when it is waiting at the library."""

    title: str
    ready: bool
    pickup_by: date | None


def parse_csrf(html: str) -> str | None:
    """Return the CSRF token from the login form, if present."""
    field = BeautifulSoup(html, "html.parser").select_one(
        "form#loginForm input[name=csrf]"
    )
    return field.get("value") if field else None


def is_login_form(html: str) -> bool:
    """True when the page still shows the login form (login failed)."""
    return BeautifulSoup(html, "html.parser").select_one("form#loginForm") is not None


def _counts(payload: dict, keys: tuple[str, ...]) -> dict[str, int] | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    return {key: int(data.get(key) or 0) for key in keys}


def parse_loan_summary(payload: dict) -> dict[str, int] | None:
    """Counts from VuFind's getUserTransactions; None when not logged in."""
    counts = _counts(payload, ("ok", "warn", "overdue"))
    if counts is not None:
        counts["total"] = int(payload["data"].get("total") or sum(counts.values()))
    return counts


def parse_hold_summary(payload: dict) -> dict[str, int] | None:
    """Counts from VuFind's getUserHolds; None when not logged in."""
    return _counts(payload, ("available", "in_transit", "other"))


def _find_date(text: str, label: re.Pattern[str]) -> date | None:
    """First date after a label, or None when the label or date is missing."""
    found = label.search(text)
    match = _DATE_RE.search(text, found.end()) if found else None
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _any_date(text: str) -> date | None:
    return _find_date(text, re.compile(r"^"))


def _rows(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """(title, row text) for each item on a My account list page."""
    rows: list[Tag] = soup.select(_ROW_SELECTORS)
    if not rows:
        # Fallback: each item has a selection checkbox; use its nearest block.
        for box in soup.select('input[name$="IDS[]"]'):
            parent = box.find_parent(["li", "tr", "div"], class_=True)
            if parent is not None and parent not in rows:
                rows.append(parent)
    result = []
    for row in rows:
        title_tag = row.select_one(_TITLE_SELECTORS)
        title = " ".join(title_tag.get_text(" ", strip=True).split()) if title_tag else ""
        if title:
            result.append((title, " ".join(row.get_text(" ", strip=True).split())))
    return result


def parse_loans(html: str) -> list[Loan]:
    """Parse the Checked out items page, soonest due first."""
    loans = [
        Loan(title, _find_date(text, _DUE_LABEL_RE) or _any_date(text))
        for title, text in _rows(BeautifulSoup(html, "html.parser"))
    ]
    loans.sort(key=lambda loan: (loan.due_date is None, loan.due_date or date.max))
    return loans


def parse_holds(html: str) -> list[Hold]:
    """Parse the Holds page; items ready for pickup first, earliest deadline first."""
    holds = []
    for title, text in _rows(BeautifulSoup(html, "html.parser")):
        ready = bool(_READY_RE.search(text))
        pickup_by = _find_date(text, _PICKUP_BY_RE) if ready else None
        holds.append(Hold(title, ready, pickup_by))
    holds.sort(
        key=lambda hold: (not hold.ready, hold.pickup_by is None, hold.pickup_by or date.max)
    )
    return holds
