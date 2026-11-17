"""DACH slice: extractor A rules, the reconcile logic and the data contracts on the committed outputs."""
from pathlib import Path

import pandas as pd
import pytest

from chase.sources import dach_extract as X

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"


@pytest.mark.parametrize("tok,val", [("1,234", 1234), ("1.234", 1234), ("1'234", 1234), ("1’234", 1234), ("(1,234.5)", -1234.5),
                                     ("-2.345,6", -2345.6), ("12.5", 12.5), ("–987", -987)])
def test_number_formats(tok, val):
    assert X.parse_num(tok) == val


def test_note_reference_and_percent_columns_are_skipped():
    assert X.values_on_line(" 23 4,321 3,987") == [4321, 3987]
    assert X.values_on_line(" 12,345 11,234 -2.1 %") == [12345, 11234]


def test_combined_payables_line_is_never_trade_payables():
    rows = X.find_rows("Trade and other payables 5,000 4,000\nTrade payables (30) 4,321 3,987\n"
                       "Verbindlichkeiten aus Lieferungen und Leistungen und sonstige Verbindlichkeiten 9.999 8.888", "trade_payables")
    assert [r[2] for r in rows] == [[4321, 3987]]


def test_esef_cells_on_separate_lines():
    rows = X.find_rows("Contract liabilities\n(23)\n1,587,682\n1,539,731\nTrade payables\n(30)\n2,979,205\n2,790,820\nNon-financial liabilities", "trade_payables")
    assert rows[0][2] == [2979205, 2790820]


def test_consolidated_statement_wins_over_parent_only():
    group = "Consolidated balance sheet\nEquity and liabilities\nCurrent liabilities\nTrade payables 300 280\n"
    parent = "Balance sheet\nTotal assets 999\nCurrent liabilities\nTrade payables 50 40\nprepared under HGB\n"
    pages = [parent, "notes", group]
    assert X._pick_page(pages, X.BS_HEAD, X.BS_TOTAL, "trade_payables") == 2


def test_unit_and_column_order():
    assert X.unit_of("in € million") == ("EUR", 1e6) and X.unit_of("T€") == ("EUR", 1e3) and X.unit_of("CHF million")[0] == "CHF"
    assert X.column_order_desc("in € million 2025 2024") and not X.column_order_desc("in € million 2024 2025")


# ---------------------------------------------------------------- contracts on the committed outputs
needs = pytest.mark.skipif(not (INTERIM / "dach_dpo.csv").exists(), reason="DACH slice not built")


@needs
def test_dach_dpo_rows_carry_provenance_and_trade_basis():
    d = pd.read_csv(INTERIM / "dach_dpo.csv")
    ok = d[d.dpo.notna()]
    assert len(ok) > 0
    for c in ("source_url", "source_type", "period_end", "extraction_method", "confidence"):
        assert ok[c].notna().all(), c
    assert (ok.payables_basis == "trade").all()
    assert set(ok.cost_basis) <= {"cost_of_sales", "cost_of_materials"}
    assert (ok.loc[ok.cost_basis == "cost_of_materials", "confidence"] < 1.0).all()
    assert set(ok.extraction_method.str.split("+").explode()) <= {"dual_extractor_agreement", "qa_adjudication"}


@needs
def test_no_banks_or_insurers_in_the_slice():
    t = pd.read_csv(INTERIM / "dach_targets.csv")
    assert not t.name.str.contains("Allianz|Münchener Rück|Munich Re|Bank|Versicherung", case=False).any()


@needs
def test_dach_rows_reach_the_dpo_table_as_proxy():
    dpo = pd.read_parquet(ROOT / "data" / "processed" / "dpo.parquet")
    d = dpo[dpo.dpo_source == "dach_annual_report"]
    scored = d[d.dpo.notna()]
    assert len(scored) > 0 and (scored.payables_basis == "trade").all()
    # a materials-based proxy can never reach Tier 1 or a dinner hook on its own (DECISIONS 46)
    assert (scored.loc[scored.cost_basis == "cost_of_materials", "confidence"] < 1.0).all()
