"""
Smart year inference for `MM-DD` check-in dates from Excel imports.

LOCKED 2026-04-29 (decision Q1=b):
  MM-DD on/after issue's ISO Monday → same year as the issue
  MM-DD before  issue's ISO Monday → next year (rolling into next year)

These tests pin the rule so future tweaks are intentional.
"""
import pytest

from app.excel import infer_check_in_year, parse_cell


# ─── infer_check_in_year — pure logic ─────────────────────────────────

def test_after_issue_week_same_year():
    """8/15 after wk626 (2026-06-22) → 2026."""
    assert infer_check_in_year(8, 15, 2026, 26) == 2026


def test_before_issue_week_next_year():
    """2/20 before wk626 (2026-06-22) → 2027 (next-year planning)."""
    assert infer_check_in_year(2, 20, 2026, 26) == 2027


def test_exactly_on_iso_monday_same_year():
    """On the ISO Monday boundary: same year (≥ comparison)."""
    # wk626 ISO Monday = 2026-06-22 → 6/22 → 2026
    assert infer_check_in_year(6, 22, 2026, 26) == 2026


def test_one_day_before_iso_monday_next_year():
    """Strict next-year for one day before."""
    # wk626 ISO Monday = 2026-06-22 → 6/21 → 2027
    assert infer_check_in_year(6, 21, 2026, 26) == 2027


def test_invalid_date_falls_back_to_issue_year():
    """2/30 doesn't exist — don't crash, return issue_week_year."""
    assert infer_check_in_year(2, 30, 2026, 26) == 2026


def test_early_year_issue_late_check_in():
    """Issue in wk601 (Jan 2026), check-in 12/15 → same year (after Jan)."""
    assert infer_check_in_year(12, 15, 2026, 1) == 2026


def test_late_year_issue_early_check_in():
    """Issue in wk652 (late Dec 2026), check-in 1/10 → 2027."""
    assert infer_check_in_year(1, 10, 2026, 52) == 2027


# ─── parse_cell with week info ────────────────────────────────────────

def test_parse_cell_returns_yyyy_mm_dd_when_week_supplied():
    """When called with issue week, check_in_date is full YYYY-MM-DD."""
    state, ci, _ = parse_cell("UAT\n2/20",
                              issue_week_year=2026, issue_week_number=26)
    assert state == "uat"
    assert ci == "2027-02-20"  # before wk626 → 2027


def test_parse_cell_uat_done_with_check_in():
    state, ci, _ = parse_cell("UAT done\n8/15 deployed",
                              issue_week_year=2026, issue_week_number=26)
    assert state == "uat_done"
    assert ci == "2026-08-15"  # after → same year


def test_parse_cell_no_check_in_date():
    state, ci, note = parse_cell("Done",
                                 issue_week_year=2026, issue_week_number=26)
    assert state == "done"
    assert ci is None
    assert note is None


def test_parse_cell_legacy_no_week_returns_mm_dd():
    """Backward compatibility: when caller doesn't pass week, MM-DD as before.
    Keeps existing standalone tests/uses (e.g. unit fixtures) working."""
    state, ci, _ = parse_cell("UAT\n2/20")
    assert state == "uat"
    assert ci == "02-20"


def test_parse_cell_short_note_preserved():
    state, ci, note = parse_cell("Developing\n3/10\n等 spec 確認",
                                 issue_week_year=2026, issue_week_number=10)
    assert state == "developing"
    # wk610 Monday = 2026-03-02; 3/10 ≥ 3/02 → same year 2026
    assert ci == "2026-03-10"
    assert note == "等 spec 確認"
