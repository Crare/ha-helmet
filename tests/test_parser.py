"""Parser tests. Run: python -m pytest tests (needs beautifulsoup4 and pytest)."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

# Load parser.py directly so Home Assistant is not needed for the tests.
_PATH = Path(__file__).parents[1] / "custom_components" / "helmet" / "parser.py"
_SPEC = importlib.util.spec_from_file_location("helmet_parser", _PATH)
parser = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = parser
_SPEC.loader.exec_module(parser)

LOGIN = """<form method="post" action="/MyResearch/Home" id="loginForm">
<input type="hidden" name="csrf" value="abc-123"></form>"""

LOANS = """
<div class="myresearch-row">
  <a class="record-title" href="/Record/1">Muumipeikko   ja pyrstötähti</a>
  <span>Eräpäivä: 3.12.2026</span>
</div>
<div class="myresearch-row">
  <a class="record-title" href="/Record/2">Tove Jansson</a>
  <span>Lainattu 1.11.2026</span> <span>Eräpäivä 25.11.2026</span>
</div>
<div class="myresearch-row"><span>no title here 1.1.2026</span></div>
"""

HOLDS = """
<ul>
  <li class="result"><a class="title">Odottaa</a> Jonossa: 4</li>
  <li class="result"><a class="title">Valmis B</a> Noudettavissa.
     Noudettava viimeistään 28.11.2026</li>
  <li class="result"><a class="title">Valmis A</a> Noudettavissa.
     Noudettava viimeistään 24.11.2026</li>
</ul>
"""

CHECKBOX_ONLY = """
<ul><li class="item"><input type="checkbox" name="renewSelectedIDS[]">
<h3>Kirja</h3> Due 2.1.2027</li></ul>
"""


def test_login_form():
    assert parser.parse_csrf(LOGIN) == "abc-123"
    assert parser.is_login_form(LOGIN)
    assert not parser.is_login_form("<p>Omat tiedot</p>")
    assert parser.parse_csrf("<p></p>") is None


def test_summaries():
    assert parser.parse_loan_summary({"data": ""}) is None
    assert parser.parse_loan_summary({"data": {"ok": 2, "warn": 1, "overdue": 0}}) == {
        "ok": 2, "warn": 1, "overdue": 0, "total": 3,
    }
    assert parser.parse_hold_summary({"data": {"available": "2", "in_transit": 1}}) == {
        "available": 2, "in_transit": 1, "other": 0,
    }


def test_loans_sorted_by_due_date_using_due_label():
    loans = parser.parse_loans(LOANS)
    assert [(loan.title, loan.due_date) for loan in loans] == [
        ("Tove Jansson", date(2026, 11, 25)),
        ("Muumipeikko ja pyrstötähti", date(2026, 12, 3)),
    ]


def test_holds_ready_first_with_deadline():
    holds = parser.parse_holds(HOLDS)
    assert [(h.title, h.ready, h.pickup_by) for h in holds] == [
        ("Valmis A", True, date(2026, 11, 24)),
        ("Valmis B", True, date(2026, 11, 28)),
        ("Odottaa", False, None),
    ]


def test_checkbox_fallback_and_english_label():
    assert parser.parse_loans(CHECKBOX_ONLY) == [parser.Loan("Kirja", date(2027, 1, 2))]


def test_invalid_date_is_ignored():
    assert parser.parse_loans(
        '<div class="result"><a class="title">X</a> Eräpäivä 31.2.2026</div>'
    ) == [parser.Loan("X", None)]


def test_alerts():
    html = '<div class="alert alert-danger">Tunnus/salasana ei  täsmää.</div><div class="alert"> </div>'
    assert parser.parse_alerts(html) == ["Tunnus/salasana ei täsmää."]


def _queue_of(text):
    html = f'<li class="result"><a class="title">T</a> {text}</li>'
    hold = parser.parse_holds(html)[0]
    return hold.queue_position, hold.queue_length


def test_queue_position_wordings():
    assert _queue_of("Jonossa: 4") == (4, None)
    assert _queue_of("Sija jonossa 3 / 12") == (3, 12)
    assert _queue_of("Sijasi varausjonossa: 2") == (2, None)
    assert _queue_of("Position in queue: 7 of 20") == (7, 20)
    assert _queue_of("Plats i kön: 5") == (5, None)
    assert _queue_of("3. jonossa") == (3, None)
    assert _queue_of("Queue position 1") == (1, None)


def test_queue_position_ignores_dates_and_ready():
    assert _queue_of("Jonossa Varattu 24.11.2026") == (None, None)
    assert _queue_of("Jonossa. Voimassa 1.6.2027") == (None, None)
    assert _queue_of("Noudettavissa. Noudettava viimeistään 28.11.2026 Jonossa: 1") == (None, None)
