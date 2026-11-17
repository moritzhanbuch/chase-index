"""Tests for the deterministic Spain PMP extractor (extractor A).

All fixtures are synthetic: made-up figures in the layouts found in real
ESEF notes (HTML tables, PDF-to-HTML running text, IR-page sentences).
"""
from __future__ import annotations

import pytest

from chase.sources import spain_pmp as sp

# --------------------------------------------------------------------------
# number parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw, lang, kind, expected", [
    ("1.234,5", "es", None, 1234.5),
    ("1,234.5", "en", None, 1234.5),
    ("1,234.5", "es", None, 1234.5),          # both separators: last one is the decimal
    ("37,07", "es", "days", 37.07),
    ("45.3", "es", "days", 45.3),              # dot + one digit can only be a decimal
    ("63 días", "es", "days", 63.0),
    ("44 days", "en", "days", 44.0),
    ("93,5 %", "es", "pct", 93.5),
    ("98%", "es", "pct", 98.0),
    ("1.616.333", "es", "money", 1616333.0),
    ("4.437.589.728", "es", "money", 4437589728.0),
    ("6.051", "es", "money", 6051.0),          # lone separator + 3 digits: thousands for money
    ("6.051", "es", None, 6051.0),             # Spanish convention
    ("6.051", "en", None, 6.051),              # English convention
    ("12,345", "en", None, 12345.0),
    ("12,345", "es", "days", 12.345),          # days are never in the thousands
    ("(1.234)", "es", "money", -1234.0),
    ("1 234 567", "es", "money", 1234567.0),   # space as thousands separator
    ("0", "es", "days", 0.0),
])
def test_parse_number(raw, lang, kind, expected):
    assert sp.parse_number(raw, lang, kind) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "-", "n/a", "Días", "1.23.4", "12,34,5", "2025 (*)x", None])
def test_parse_number_rejects(raw):
    assert sp.parse_number(raw, "es", None) is None


def test_separator_against_language_is_flagged():
    value, flags = sp.parse_number_ex("364,527", "es", "money")
    assert value == 364527.0
    assert "separator_against_language_convention" in flags
    value, flags = sp.parse_number_ex("307.737", "es", "money")
    assert value == 307737.0 and not flags


@pytest.mark.parametrize("raw, expected", [
    ("2 1 .0 91", "21.091"),        # letter-spacing artefact
    ("3 7 , 0 7", "37,07"),
    ("1 234", "1234"),              # space thousands separator
    ("37,07 37,51", "37,07 37,51"),  # two complete numbers: untouched
    ("37 38", "37 38"),             # could be two columns: untouched
    ("97,7 2", "97,7 2"),           # ambiguous: untouched
    ("Total 1 2", "Total 1 2"),     # not a purely numeric cell
])
def test_collapse_letter_spacing(raw, expected):
    assert sp.collapse_letter_spacing(raw) == expected


def test_letter_spaced_cell_parses_and_is_flagged():
    value, flags = sp.parse_number_ex("2 1 .0 91", "es", "money")
    assert value == 21091.0
    assert "letter_spacing_collapsed" in flags


# --------------------------------------------------------------------------
# label matching
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label, expected", [
    ("Periodo medio de pago a proveedores", "pmp"),
    ("Período medio de pago a proveedores (PMP) (1)", "pmp"),
    ("Periodo Medio de Pago a Proveedores (días)", "pmp"),
    ("Periodo medio de pagos a proveedores", "pmp"),
    ("Periodo medio de pago", "pmp"),
    ("(Días) Periodo medio de pago a proveedores", "pmp"),
    ("Average payment period to suppliers", "pmp"),
    ("Average supplier payment period (days)", "pmp"),
    ("Ratio de operaciones pagadas", "ratio_paid"),
    ("Ratio de las operaciones pagadas (días) (2)", "ratio_paid"),
    ("Ratio of transactions paid", "ratio_paid"),
    ("Ratio de operaciones pendientes de pago", "ratio_pending"),
    ("Ratio de las operaciones pendientes de pago", "ratio_pending"),
    ("Ratio of transactions pending payment", "ratio_pending"),
    ("Ratio of outstanding transactions", "ratio_pending"),
    ("Total pagos realizados", "total_paid"),
    ("Total de pagos realizados", "total_paid"),
    ("Total pagos (millones de euros)", "total_paid"),
    ("(millones de euros) Importe Importe Total pagos realizados", "total_paid"),
    ("Total payments made", "total_paid"),
    ("Total pagos pendientes", "total_pending"),
    ("Pagos pendientes", "total_pending"),
    ("Total payments pending", "total_pending"),
    ("Total payments outstanding", "total_pending"),
    ("Porcentaje sobre el total de pagos realizados", "pct_by_value"),
    ("Porcentaje que supone sobre el total monetario de pagos a los proveedores", "pct_by_value"),
    ("% Sobre total de las facturas sujetas (importe)", "pct_by_value"),
    ("% Volumen de pagos en período inferior al máximo", "pct_by_value"),
    ("Porcentaje sobre el total de facturas", "pct_by_number"),
    ("Porcentaje sobre el número total de facturas pagadas a proveedores", "pct_by_number"),
    ("% Sobre total de las facturas sujetas (número)", "pct_by_number"),
    ("% Facturas pagadas en período inferior al máximo", "pct_by_number"),
    # must NOT match
    ("Total pagos realizados dentro del plazo legal (4)", None),
    ("Información sobre el periodo medio de pago a proveedores. Disposición adicional tercera", None),
    ("Número de facturas pagadas", None),
    ("Volumen monetario (miles de euros)", None),
    ("Días", None),
    ("", None),
])
def test_classify_label(label, expected):
    assert sp.classify_label(label) == expected


def test_classify_uses_percent_cells():
    label = "Total pagos realizados dentro del plazo máximo legal sobre el total de pagos realizados"
    assert sp.classify_label(label, ["88,4 %", "86,7 %"]) == "pct_by_value"
    label = "Total facturas pagadas dentro del plazo máximo legal sobre el total de facturas pagadas"
    assert sp.classify_label(label, ["97,0 %", "95,7 %"]) == "pct_by_number"
    assert sp.classify_label("De las que: pagadas en el plazo legal (1)",
                             ["3.396", "93,5 %", "1.433.816", "96,0%"]) == "within_legal_mixed"


def test_flow_percentages_need_a_table_like_label():
    assert sp.classify_label("Porcentaje sobre el total de facturas", ["73 %"], flow=True) == "pct_by_number"
    prose = "importe total de pagos pendientes. Representa un"
    assert sp.classify_label(prose, ["97%"], flow=True) is None


def test_label_core_strips_footnotes():
    assert sp.label_core("Período medio de pago a proveedores (días) (1)") == \
        "periodo medio de pago a proveedores"


# --------------------------------------------------------------------------
# table parsing
# --------------------------------------------------------------------------

TABLE_ES = """
<p>Información sobre los aplazamientos de pago efectuados a proveedores de las sociedades
españolas del Grupo, según la Ley 15/2010, de 5 de julio.</p>
<table>
 <tr><td></td><td>2025</td><td>2024</td></tr>
 <tr><td></td><td>Días</td><td>Días</td></tr>
 <tr><td><span>Periodo medio de pago a proveedores</span></td><td><span>40,00</span></td><td>42,50</td></tr>
 <tr><td>Ratio de operaciones pagadas</td><td>41,00</td><td>43,00</td></tr>
 <tr><td>Ratio de operaciones pendientes de pago</td><td>31,00</td><td>38,00</td></tr>
 <tr><td></td><td>Importe (miles de euros)</td><td>Importe (miles de euros)</td></tr>
 <tr><td>Total pagos realizados</td><td>900.000</td><td>800.000</td></tr>
 <tr><td>Total pagos pendientes</td><td>100.000</td><td>90.000</td></tr>
 <tr><td>Volumen monetario de facturas pagadas en un periodo inferior al máximo</td><td>720.000</td><td>600.000</td></tr>
 <tr><td>Porcentaje sobre el total de pagos realizados</td><td>80,0 %</td><td>75,0 %</td></tr>
 <tr><td>Número de facturas pagadas en un periodo inferior al máximo</td><td>9.000</td><td>8.000</td></tr>
 <tr><td>Porcentaje sobre el total de facturas</td><td>85,5 %</td><td>81,0 %</td></tr>
</table>
"""


def _best(html, fy=2025):
    rows = sp.linearize(html)
    cands = sp.build_candidates(rows, fy, fact_id="f-1", concept="x:Test")
    best, distinct = sp.select(cands)
    return best, distinct


def test_table_full_extraction():
    best, distinct = _best(TABLE_ES)
    assert len(distinct) == 1
    v = best.values
    assert best.mode == "table" and best.lang == "es"
    assert v["fiscal_year"] == 2025 and v["prior_fiscal_year"] == 2024
    assert v["pmp_days"] == 40.0 and v["prior_year_pmp_days"] == 42.5
    assert v["ratio_paid_days"] == 41.0 and v["ratio_pending_days"] == 31.0
    assert v["total_payments_made"] == 900000.0 and v["total_payments_pending"] == 100000.0
    assert v["pct_invoices_paid_within_legal_max_by_value"] == 80.0
    assert v["pct_invoices_paid_within_legal_max_by_number"] == 85.5
    assert best.unit == "thousands EUR"
    assert best.scope == "consolidated_spanish_entities"
    assert best.scope_basis.startswith("explicit")
    assert "Periodo medio de pago a proveedores | 40,00 | 42,50" in best.snippet
    checks = sp.sanity_checks(v)
    assert checks["check_pmp_in_range"] and checks["check_pmp_between_ratios"]
    assert checks["pmp_recomputed"] == 40.0
    assert checks["check_recomputed_within_1_day"] is True
    assert sp.score_confidence(best, checks, len(distinct)) == 0.95


def test_table_prior_year_first_column():
    html = """<table>
      <tr><td>Days</td><td>2024</td><td>2025</td></tr>
      <tr><td>Average payment period to suppliers</td><td>52</td><td>48</td></tr>
      <tr><td>Ratio of transactions paid</td><td>55</td><td>50</td></tr>
      <tr><td>Ratio of transactions pending payment</td><td>30</td><td>28</td></tr>
      <tr><td>Thousands of euros</td><td>2024</td><td>2025</td></tr>
      <tr><td>Total payments made</td><td>1,000</td><td>1,100</td></tr>
      <tr><td>Total payments outstanding</td><td>100</td><td>110</td></tr>
    </table>"""
    best, _ = _best(html)
    v = best.values
    assert best.lang == "en"
    assert (v["fiscal_year"], v["pmp_days"]) == (2025, 48.0)
    assert (v["prior_fiscal_year"], v["prior_year_pmp_days"]) == (2024, 52.0)
    assert v["ratio_paid_days"] == 50.0 and v["ratio_pending_days"] == 28.0
    assert v["total_payments_made"] == 1100.0 and v["total_payments_pending"] == 110.0
    assert best.unit == "thousands EUR"


def test_totals_in_following_table_and_date_headers():
    html = """<table>
      <tr><td>Días</td></tr>
      <tr><td>31/12/2025</td><td>31/12/2024</td></tr>
      <tr><td>Periodo medio de pago a proveedores</td><td>78</td><td>71</td></tr>
      <tr><td>Ratio de las operaciones pagadas</td><td>81</td><td>72</td></tr>
      <tr><td>Ratio de las operaciones pendientes de pago</td><td>56</td><td>60</td></tr>
    </table>
    <table>
      <tr><td>Millones de euros</td></tr>
      <tr><td>31/12/2025</td><td>31/12/2024</td></tr>
      <tr><td>Total pagos realizados</td><td>750</td><td>800</td></tr>
      <tr><td>Pagos pendientes</td><td>100</td><td>90</td></tr>
    </table>"""
    best, _ = _best(html)
    v = best.values
    assert best.year_basis == "header" and v["fiscal_year"] == 2025
    assert v["total_payments_made"] == 750.0 and v["total_payments_pending"] == 100.0
    assert best.unit == "millions EUR"
    assert best.same_block["ratio_paid_days"] is True
    assert best.same_block["total_payments_made"] is False


def test_totals_table_before_pmp_table_with_mixed_row():
    html = """<table>
      <tr><td>(Millones de euros) / Número de facturas</td></tr>
      <tr><td>2025</td><td>2024</td></tr>
      <tr><td>Importe</td><td>%</td><td>Número facturas</td><td>%</td><td>Importe</td><td>%</td><td>Número facturas</td><td>%</td></tr>
      <tr><td>Total pagos realizados</td><td>3.000</td><td>1.000.000</td><td>2.800</td><td>900.000</td></tr>
      <tr><td>De las que: pagadas en el plazo legal (1)</td><td>2.700</td><td>90,0 %</td><td>950.000</td><td>95,0%</td><td>2.500</td><td>89,3 %</td><td>850.000</td><td>94,4%</td></tr>
      <tr><td>Total pagos pendientes</td><td>100</td><td>10.000</td><td>60</td><td>9.000</td></tr>
    </table>
    <table>
      <tr><td>(Días)</td></tr>
      <tr><td>2025</td><td>2024</td></tr>
      <tr><td>Periodo medio de pago a proveedores</td><td>12,7</td><td>12,6</td></tr>
      <tr><td>Ratio de operaciones pagadas</td><td>12,5</td><td>12,4</td></tr>
      <tr><td>Ratio de operaciones pendientes de pago</td><td>23,5</td><td>18,6</td></tr>
    </table>"""
    best, _ = _best(html)
    v = best.values
    assert v["pmp_days"] == 12.7
    assert v["total_payments_made"] == 3000.0 and v["total_payments_pending"] == 100.0
    assert v["pct_invoices_paid_within_legal_max_by_value"] == 90.0
    assert v["pct_invoices_paid_within_legal_max_by_number"] == 95.0
    assert best.unit == "millions EUR"


def test_pmp_outside_ratios_lowers_confidence():
    html = TABLE_ES.replace("40,00", "55,00")
    best, distinct = _best(html)
    checks = sp.sanity_checks(best.values)
    assert checks["check_pmp_between_ratios"] is False
    assert checks["check_recomputed_within_1_day"] is False
    assert sp.score_confidence(best, checks, len(distinct)) == 0.5


def test_pmp_only_table():
    html = """<table><tr><td>Días</td><td>2025</td><td>2024</td></tr>
      <tr><td>Periodo medio de pago a proveedores</td><td>23</td><td>20</td></tr></table>"""
    best, distinct = _best(html)
    v = best.values
    assert v["pmp_days"] == 23.0 and v["ratio_paid_days"] is None
    checks = sp.sanity_checks(v)
    assert checks["check_pmp_between_ratios"] is None and checks["pmp_recomputed"] is None
    assert sp.score_confidence(best, checks, len(distinct)) == 0.7


def test_nil_cell_keeps_column_positions():
    html = TABLE_ES.replace("<td>100.000</td><td>90.000</td>", "<td>-</td><td>90.000</td>")
    best, _ = _best(html)
    assert best.values["total_payments_pending"] is None   # not the prior-year 90.000


def test_formula_row_and_heading_are_not_candidates():
    html = """<table><tr><td>Información sobre el periodo medio de pago a proveedores</td></tr></table>
    <table><tr><td>Periodo medio de pagos a proveedores</td><td>=</td>
      <td>Ratio de operaciones pagadas * importe de pagos realizados</td></tr></table>"""
    best, distinct = _best(html)
    assert best is None and distinct == []


def test_out_of_range_pmp_is_not_a_candidate():
    html = """<table><tr><td>2025</td><td>2024</td></tr>
      <tr><td>Periodo medio de pago a proveedores</td><td>2.025</td><td>2.024</td></tr></table>"""
    # "2.025" parsed as days = 2.025 would pass; a true out-of-range value must not
    html2 = html.replace("2.025", "450").replace("2.024", "460")
    best, _ = _best(html2)
    assert best is None


def test_two_tables_first_full_table_wins_and_subset_is_recorded():
    second = TABLE_ES.replace("<td></td><td>2025</td>", "<td>Solo nacionales</td><td>2025</td>") \
                     .replace("40,00", "38,00")
    best, distinct = _best(TABLE_ES + second)
    assert len(distinct) == 2
    assert best.values["pmp_days"] == 40.0
    best2, _ = _best(second + TABLE_ES)       # subset first in the document: still loses
    assert best2.values["pmp_days"] == 40.0


def test_duplicate_tables_are_deduplicated():
    best, distinct = _best(TABLE_ES + TABLE_ES)
    assert len(distinct) == 1


# --------------------------------------------------------------------------
# flow (no <table>) and prose
# --------------------------------------------------------------------------

FLOW_ES = """<div><div>Dicha información se refiere al ámbito nacional al que exclusivamente
aplica esta normativa, Ley 31/2014, de 3 de diciembre:</div>
<div>Período medio de pago y pagos realizados y pendientes de pago en España</div>
<div>2025 </div><div>2024 </div><div>Días </div><div>Días </div>
<div>Período medio de pago a proveedores</div><div>27 </div><div>25 </div>
<div>Ratio de operaciones pagadas </div><div>24 </div><div>22 </div>
<div>Ratio de operaciones pendientes de pago </div><div>41 </div><div>42 </div>
<div>(millones de euros) </div><div>Importe </div><div>Importe </div>
<div>Total pagos realizados</div><div>4.000 </div><div>3.800 </div>
<div>Total pagos pendientes</div><div>1.000 </div><div>700 </div>
<div>Porcentaje sobre el total monetario de pagos a proveedores</div><div>95,48% </div><div>95,18% </div>
<div>Porcentaje sobre el número total de facturas pagadas a proveedores</div><div>95,90% </div><div>93,89% </div>
</div>"""


def test_flow_text_extraction():
    best, distinct = _best(FLOW_ES)
    v = best.values
    assert best.mode == "flow" and len(distinct) == 1
    assert (v["fiscal_year"], v["pmp_days"], v["prior_year_pmp_days"]) == (2025, 27.0, 25.0)
    assert v["ratio_paid_days"] == 24.0 and v["ratio_pending_days"] == 41.0
    assert v["total_payments_made"] == 4000.0 and v["total_payments_pending"] == 1000.0
    assert v["pct_invoices_paid_within_legal_max_by_value"] == 95.48
    assert v["pct_invoices_paid_within_legal_max_by_number"] == 95.9
    assert best.unit == "millions EUR"
    assert best.scope == "consolidated_spanish_entities"
    checks = sp.sanity_checks(v)
    assert checks["pmp_recomputed"] == 27.4 and checks["check_recomputed_within_1_day"]


def test_flow_law_references_are_not_values():
    rows = sp.flow_rows("según la Ley 15/2010, de 5 de julio. Periodo medio de pago a proveedores 35 28")
    pmp = [r for r in rows if sp.classify_label(r.label, r.cells, flow=True) == "pmp"]
    assert len(pmp) == 1 and pmp[0].cells == ["35", "28"]


def test_flow_unreadable_year_header_is_flagged():
    html = "<div>La información es la 025 2024 (Días) Periodo medio de pago a proveedores 35 28 " \
           "Ratio de operaciones pagadas 36 29 Ratio de operaciones pendientes de pago 26 26</div>"
    best, distinct = _best(html)
    assert best.year_basis == "assumed_current_year_first"
    assert best.values["fiscal_year"] == 2025 and best.values["pmp_days"] == 35.0
    checks = sp.sanity_checks(best.values)
    assert sp.score_confidence(best, checks, len(distinct)) == pytest.approx(0.8)


def test_prose_parent_only_sentence():
    text = ("Periodo medio de pago a proveedores. El periodo medio de pago a proveedores de "
            "Banco Ejemplo, S.A. durante el ejercicio 2025 es de 10 días. Asimismo, en el año 2025 "
            "ha pagado facturas que suponen un 99,94% sobre el volumen total de facturas pagadas y "
            "un 99,92% sobre el importe total de pagos a proveedores.")
    cands = sp.prose_candidates(text, 2025)
    assert len(cands) == 1
    c = cands[0]
    assert c.values["pmp_days"] == 10.0 and c.values["fiscal_year"] == 2025
    assert c.values["prior_year_pmp_days"] is None
    assert c.scope == "parent_only"
    assert c.values["pct_invoices_paid_within_legal_max_by_number"] == 99.94
    assert c.values["pct_invoices_paid_within_legal_max_by_value"] == 99.92
    assert c.snippet.startswith("periodo medio de pago a proveedores de Banco Ejemplo, S.A.")
    checks = sp.sanity_checks(c.values)
    assert sp.score_confidence(c, checks, 1) == 0.6


def test_prose_two_years_with_ratios_and_year_guard():
    text = ("el periodo medio de pago a proveedores del Grupo durante los ejercicios 2025 y 2024 es de "
            "8,85 días y 9,70 días, respectivamente, mientras que el ratio de operaciones pagadas para "
            "dichos ejercicios asciende a 8,90 días y a 9,70 días, respectivamente, y el ratio de "
            "operaciones pendientes de pago a 7,59 días y a 16,98 días, respectivamente. "
            "El Grupo pagó durante 2024 un total de 100 facturas, de las que 90 facturas fueron pagadas "
            "en un plazo inferior al máximo legal (90,00% del total). "
            "El Grupo ha pagado durante 2025 un total de 200 facturas, de las que 196 facturas han sido "
            "pagadas en un plazo inferior al máximo legal ( 98,00% del total).")
    c = sp.prose_candidates(text, 2025)[0]
    v = c.values
    assert (v["pmp_days"], v["prior_year_pmp_days"], v["prior_fiscal_year"]) == (8.85, 9.7, 2024)
    assert v["ratio_paid_days"] == 8.9 and v["ratio_pending_days"] == 7.59
    assert v["pct_invoices_paid_within_legal_max_by_number"] == 98.0   # 2024 sentence skipped
    assert c.scope == "consolidated_spanish_entities"
    assert sp.score_confidence(c, sp.sanity_checks(v), 1) == 0.75


# --------------------------------------------------------------------------
# helpers and end-to-end on a tiny xBRL-JSON
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text, unit", [
    ("Importe (miles de euros)", "thousands EUR"),
    ("Millones de Euros", "millions EUR"),
    ("Thousands of euros", "thousands EUR"),
    ("IMPORTE (EUROS)", "EUR"),
    ("Importe m €", "thousands EUR"),
    ("Importe M€", "millions EUR"),
    ("Importe", None),
])
def test_find_unit(text, unit):
    assert sp.find_unit(text)[0] == unit


def test_find_years_ignores_law_numbers():
    assert sp.find_years("Ley 15/2010, Ley 18/2022; 31/12/2025 y 31.12.2024; ejercicio 2023") == \
        [2025, 2024, 2023]


def test_scope_ignores_unrelated_spain_mentions():
    ctx = ("activos situados en España ascienden a 382.243 miles de euros. "
           "31.3 Información sobre el periodo medio de pago a proveedores. Ley 15/2010")
    assert sp.detect_scope(ctx)[0] == "unknown"
    ctx2 = "Información sobre los aplazamientos de pago efectuados a proveedores en España"
    assert sp.detect_scope(ctx2)[0] == "consolidated_spanish_entities"


def test_extract_company_end_to_end(tmp_path, monkeypatch):
    import json
    doc = {"facts": {
        "f-1": {"value": "<p>Nothing here</p>" + "x" * 200, "dimensions": {"concept": "x:Other"}},
        "f-2": {"value": TABLE_ES, "dimensions": {"concept": "x:Payables"}},
        "f-3": {"value": 123, "dimensions": {"concept": "x:Number"}},
    }}
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(sp, "ROOT", tmp_path)
    src = {"ticker": "TST", "company_name": "Fixture SA", "fiscal_year": "2025",
           "source_url": "https://example.invalid/doc.json", "local_path": "doc.json",
           "pmp_pages": json.dumps([{"fact_id": "f-1"}]), "status": "ok", "scope": "consolidated"}
    rec = sp.extract_company(src)
    assert set(sp.OUTPUT_FIELDS) <= set(rec)
    assert rec["pmp_days"] == 40 and rec["prior_year_pmp_days"] == 42.5
    assert rec["money_unit"] == "thousands EUR"
    assert rec["extraction_method"] == "regex_table_parse"
    assert rec["confidence"] == 0.95
    assert "fact_id=f-2" in rec["location"]            # found by the all-facts fallback
    assert "scanning all text facts" in rec["notes"]
    assert len(rec["quoted_snippet"]) <= 200

    src_missing = dict(src, ticker="NOP", pmp_pages="[]", local_path="missing.json", status="not_found")
    rec2 = sp.extract_company(src_missing)
    assert rec2["pmp_days"] is None and rec2["confidence"] == 0.0 and rec2["notes"]
