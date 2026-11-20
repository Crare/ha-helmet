"""Check a Helmet library card against helmet.finna.fi without Home Assistant.

Run it yourself; it asks for the card number and PIN without echoing them and
never prints or stores them. The output is safe to share: it shows only whether
the login worked and how many items were read. Add --show to also list the
titles and dates (your own loan data, so check it before sharing). Add --rows
to print the text of each waiting reservation with its title removed, which
shows how Helmet words the queue position (check it before sharing too).

    python -m pip install aiohttp beautifulsoup4
    python scripts/check_login.py [--show]
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import sys
import types
from pathlib import Path

# Load the integration's api/parser modules without importing Home Assistant.
_PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "helmet"
_pkg = types.ModuleType("helmet_check")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules["helmet_check"] = _pkg
api = importlib.import_module("helmet_check.api")
parser_module = importlib.import_module("helmet_check.parser")
_holds_html: list[str] = []
_parse_holds = api.parse_holds


def _capture_holds(html: str):
    _holds_html.append(html)
    return _parse_holds(html)


api.parse_holds = _capture_holds


async def _run(show: bool, rows: bool) -> int:
    username = input("Library card number: ").strip()
    password = getpass.getpass("PIN (not shown): ")
    try:
        data = await api.HelmetClient(username, password).fetch()
    except api.HelmetAuthError as err:
        print(f"LOGIN REJECTED: {err}")
        return 1
    except api.HelmetError as err:
        print(f"SITE ERROR: {err}")
        return 2

    dated = sum(1 for loan in data.loans if loan.due_date)
    ready = [hold for hold in data.holds if hold.ready]
    print("Login OK")
    print(f"Loans: site count {data.loans_total}, read from page {len(data.loans)}, "
          f"with due date {dated}, overdue {data.loans_overdue}")
    print(f"Reservations: read from page {len(data.holds)}, ready for pickup: "
          f"site count {data.holds_ready}, read from page {len(ready)}, "
          f"with pickup deadline {sum(1 for hold in ready if hold.pickup_by)}")
    waiting = [hold for hold in data.holds if not hold.ready]
    print(f"Waiting reservations: {len(waiting)}, "
          f"with queue position {sum(1 for hold in waiting if hold.queue_position)}")
    print(f"Reservations with pickup location: "
          f"{sum(1 for hold in data.holds if hold.pickup_location)}")
    if show:
        for loan in data.loans:
            print(f"  loan  {loan.due_date or '?':<10}  {loan.title}")
        for hold in data.holds:
            if hold.ready:
                state = f"ready, pick up by {hold.pickup_by or '?'}"
            else:
                state = f"waiting, queue #{hold.queue_position or '?'}"
                state += f" of {hold.queue_length}" if hold.queue_length else ""
            place = f"  @ {hold.pickup_location}" if hold.pickup_location else ""
            print(f"  hold  {state:<30}  {hold.title}{place}")
    if rows and _holds_html:
        from bs4 import BeautifulSoup

        print("Waiting reservation rows (title removed):")
        for title, text in parser_module._rows(BeautifulSoup(_holds_html[0], "html.parser")):
            if not parser_module._READY_RE.search(text):
                print("  " + text.replace(title, "<title>"))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--show", action="store_true", help="also list titles and dates")
    parser.add_argument(
        "--rows", action="store_true", help="print waiting reservation rows without titles"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.show, args.rows)))


if __name__ == "__main__":
    main()
