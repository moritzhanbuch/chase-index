"""Chain-walk tests on tiny inline fixtures. No network, no bulk files."""
import json

from chase.sources.companies_house_bulk import (
    control_rank,
    iso2_guess,
    norm_company_number,
    norm_name,
    parse_psc_line,
    walk_chain,
)

CORP = "corporate-entity-person-with-significant-control"
LEGAL = "legal-person-person-with-significant-control"

NAMES = {
    "00000001": "ALPHA STORES LIMITED",
    "00000002": "ALPHA HOLDINGS LIMITED",
    "00000003": "ALPHA PLC",
    "00000004": "BETA UK LIMITED",
    "00000005": "LOOP A LIMITED",
    "00000006": "LOOP B LIMITED",
    "00000007": "GAMMA TRADING LIMITED",
    "00000008": "GAMMA HOLDCO LIMITED",
    "00000009": "GAMMA MINORITY LIMITED",
    "00000010": "DELTA SERVICES LIMITED",
    "00000011": "DELTA GROUP LIMITED",
    "00000012": "EPSILON LIMITED",
    "00012345": "UNRELATED BAKERY LIMITED",
    "00000013": "ZETA NEW NAME LIMITED",
    "00000014": "ZETA SUB LIMITED",
}
BY_NAME = {norm_name(v): k for k, v in NAMES.items()}
PREV = {"00000013": {norm_name("Zeta Old Name Limited")}}


def psc(name, num=None, country=None, place=None, natures="ownership-of-shares-75-to-100-percent",
        kind=CORP, notified="2016-04-06"):
    return {
        "psc_name": name, "psc_kind": kind, "psc_registration_number": num,
        "psc_registration_number_norm": norm_company_number(num),
        "psc_country_registered": country, "psc_place_registered": place,
        "natures_of_control": natures, "notified_on": notified,
    }


PSCS = {
    "00000001": [psc("Alpha Holdings Limited", "2", "England")],
    "00000002": [psc("Alpha Plc", "00000003", "United Kingdom")],
    "00000004": [psc("Beta Inc.", "12345", "United States", "Delaware")],
    "00000005": [psc("Loop B Limited", "6", "England and Wales")],
    "00000006": [psc("Loop A Limited", "5", "England and Wales")],
    "00000007": [
        psc("Gamma Minority Limited", "9", "England", natures="ownership-of-shares-25-to-50-percent"),
        psc("Gamma Holdco Limited", "8", "England"),
    ],
    "00000010": [psc("Delta Group Ltd", None, None)],
    "00000012": [psc("Secretary of State for Something", kind=LEGAL, natures="ownership-of-shares-75-to-100-percent")],
    "00000014": [psc("Zeta Old Name Limited", "13", "Germany")],
    "00000009": [psc("Omega Inc.", None, "Not Specified/Other")],
    "00000008": [psc("Vanished Holdings Limited", "99999", "England")],
}


def walk(n):
    r = walk_chain(n, PSCS, NAMES, BY_NAME, PREV)
    r["chain"] = json.loads(r["chain"])
    return r


def test_clean_two_hop_chain():
    r = walk("00000001")
    assert [h["company_number"] for h in r["chain"]] == ["00000002", "00000003"]
    assert r["stop_reason"] == "no_corporate_psc"
    assert r["ultimate_parent_company_number"] == "00000003"
    assert r["ultimate_parent_name"] == "ALPHA PLC"
    assert r["ultimate_parent_country_iso2"] == "GB"
    assert r["top_uk_company_number"] == "00000003"
    assert r["ambiguous"] is False and r["confidence"] == 0.9


def test_no_psc_entity_is_its_own_parent():
    r = walk("00000003")
    assert r["chain"] == [] and r["chain_length"] == 0
    assert r["stop_reason"] == "no_corporate_psc"
    assert r["ultimate_parent_company_number"] == "00000003"
    assert r["top_uk_company_name"] == "ALPHA PLC"


def test_foreign_parent_stops_even_if_number_collides_with_uk_company():
    # "12345" pads to 00012345, a live but unrelated UK company. Country says US, name differs: stop.
    r = walk("00000004")
    assert r["stop_reason"] == "foreign_parent"
    assert r["ultimate_parent_name"] == "Beta Inc."
    assert r["ultimate_parent_company_number"] is None
    assert r["ultimate_parent_country"] == "United States"
    assert r["ultimate_parent_country_iso2"] == "US"
    assert r["top_uk_company_number"] == "00000004"


def test_cycle():
    r = walk("00000005")
    assert r["stop_reason"] == "cycle"
    assert [h["company_number"] for h in r["chain"]] == ["00000006"]
    assert r["top_uk_company_number"] == "00000006"


def test_multiple_pscs_prefers_75_to_100_and_flags_ambiguous():
    r = walk("00000007")
    assert r["chain"][0]["company_number"] == "00000008"
    assert r["ambiguous"] is True
    assert r["confidence"] == 0.7


def test_name_only_hop_lowers_confidence():
    r = walk("00000010")
    assert r["chain"][0]["company_number"] == "00000011"
    assert r["chain"][0]["match"] == "name_only"
    assert r["confidence"] == 0.7 and r["ambiguous"] is False


def test_legal_person_psc_is_terminal():
    r = walk("00000012")
    assert r["stop_reason"] == "legal_person_psc"
    assert r["ultimate_parent_company_number"] is None
    assert r["top_uk_company_number"] == "00000012"


def test_previous_name_plus_number_beats_wrong_country_text():
    r = walk("00000014")
    assert r["chain"][0]["company_number"] == "00000013"
    assert r["chain"][0]["match"] == "number_and_name"


def test_max_hops():
    names = {f"{i:08d}": f"CO {i} LIMITED" for i in range(1, 20)}
    pscs = {f"{i:08d}": [psc(f"Co {i+1} Limited", str(i + 1), "England")] for i in range(1, 19)}
    r = walk_chain("00000001", pscs, names, {}, {})
    assert r["stop_reason"] == "max_hops" and r["chain_length"] == 10


def test_norm_company_number():
    assert norm_company_number("2065") == "00002065"
    assert norm_company_number(" 04366849 ") == "04366849"
    assert norm_company_number("sc 12345") == "SC012345"
    assert norm_company_number("OC301234") == "OC301234"
    assert norm_company_number("HRB 6684") is None
    assert norm_company_number("123456789") is None
    assert norm_company_number("0") is None
    assert norm_company_number(None) is None


def test_norm_name_and_iso():
    assert norm_name("Tesco Public Limited Company") == norm_name("TESCO PLC")
    assert norm_name("Marks & Spencer Group P.L.C.") == norm_name("MARKS AND SPENCER GROUP PLC")
    assert norm_name("The Boots Company Limited") == "BOOTS CO LTD"
    assert iso2_guess("England & Wales") == "GB"
    assert iso2_guess(None, "Delaware") == "US"
    assert iso2_guess("Atlantis") is None
    assert control_rank("voting-rights-25-to-50-percent") > control_rank("ownership-of-shares-75-to-100-percent")


def test_parse_psc_line_drops_individuals_and_ceased():
    ind = json.dumps({"company_number": "00000001", "data": {
        "kind": "individual-person-with-significant-control", "name": "Mr A Person",
        "name_elements": {"surname": "Person"}}}).encode()
    assert parse_psc_line(ind) is None
    # an individual whose free text happens to contain the corporate kind string is still dropped
    tricky = json.dumps({"company_number": "00000001", "data": {
        "kind": "individual-person-with-significant-control",
        "name": "corporate-entity-person-with-significant-control"}}).encode()
    assert parse_psc_line(tricky) is None
    ceased = json.dumps({"company_number": "1", "data": {
        "kind": CORP, "name": "Old Parent Ltd", "ceased_on": "2020-01-01"}}).encode()
    assert parse_psc_line(ceased) is None
    live = json.dumps({"company_number": "1", "data": {
        "kind": CORP, "name": "Parent Ltd", "notified_on": "2016-04-06",
        "identification": {"registration_number": "2", "country_registered": "England", "legal_form": "Ltd"},
        "natures_of_control": ["ownership-of-shares-75-to-100-percent", "voting-rights-75-to-100-percent"]}}).encode()
    row = parse_psc_line(live)
    assert row["company_number"] == "00000001"
    assert row["psc_registration_number_norm"] == "00000002"
    assert row["natures_of_control"].count("|") == 1


def test_unresolved_stops_are_not_called_foreign():
    r = walk("00000009")  # no country text, no UK match: unknown, not foreign
    assert r["stop_reason"] == "unresolved_psc" and r["ultimate_parent_country_iso2"] is None
    r = walk("00000008")  # reads as UK, number not in live data (dissolved or typo)
    assert r["stop_reason"] == "unresolved_uk_psc" and r["ultimate_parent_country_iso2"] == "GB"
    assert r["ultimate_parent_company_number"] is None and r["top_uk_company_number"] == "00000008"


def test_iso_guess_inside_longer_text():
    assert iso2_guess("Pennsylvania, United States Of America") == "US"
    assert iso2_guess("Northern Ireland, UK") == "GB"
    assert iso2_guess("Channel Islands") is None
    assert norm_name("SHELL PETROLEUM COMPANY LIMITED(THE)") == norm_name("The Shell Petroleum Company Limited")
