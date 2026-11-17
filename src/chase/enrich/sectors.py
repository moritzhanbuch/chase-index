"""Map source-specific industry codes/labels to one coarse sector vocabulary.

Sectors: manufacturing, automotive, construction, retail, consumer_goods, energy, pharma,
logistics, utilities, telecom, technology, services, financials, other.

Sources of evidence, in order of trust: SEC SIC code > keyword match on Wikidata industry
labels > keyword match on the company name. The method used is returned so it can be stored.
"""
from __future__ import annotations

import re

SECTORS = ["manufacturing", "automotive", "construction", "retail", "consumer_goods", "energy",
           "pharma", "logistics", "utilities", "telecom", "technology", "services", "financials", "other"]


def sector_from_sic(sic: int | str | None) -> str | None:
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return None
    if 6000 <= s <= 6799:
        return "financials"
    if s in (5500, 5541):
        return "retail"      # fuel stations
    if s in (3711, 3713, 3714, 3715, 3716, 3751, 5511, 5521, 5531):
        return "automotive"
    if s in (2833, 2834, 2835, 2836, 3841, 3842, 3843, 3844, 3845, 3851, 8731, 5122):
        return "pharma"
    if 1000 <= s <= 1499 or s in (2911, 2990, 5171, 5172, 4922, 4923, 4924, 4925, 6792):
        return "energy"
    if 1500 <= s <= 1799:
        return "construction"
    if 2000 <= s <= 2199 or s in (2840, 2842, 2844, 3140, 3021) or 2300 <= s <= 2399 or 3630 <= s <= 3639:
        return "consumer_goods"
    if 4900 <= s <= 4991:
        return "utilities"
    if 4800 <= s <= 4899:
        return "telecom"
    if 4000 <= s <= 4799:
        return "logistics"
    if 5200 <= s <= 5999 or s in (5411, 5412):
        return "retail"
    if s in (3570, 3571, 3572, 3575, 3576, 3577, 3578, 3661, 3663, 3669, 3670, 3672, 3674, 3677, 3678, 3679) \
            or 7370 <= s <= 7379:
        return "technology"
    if 2000 <= s <= 3999:
        return "manufacturing"
    if 5000 <= s <= 5199:
        return "logistics"  # wholesale distribution: supplier-heavy, logistics-like
    if 7000 <= s <= 8999:
        return "services"
    if 100 <= s <= 999:
        return "consumer_goods"  # agriculture
    return "other"


# keyword -> sector, first match wins (ordered: most specific first)
_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(bank|banking|banco|insur|asegur|reinsur|asset management|financial services|investment|private equity|"
     r"real estate investment|stock exchange|credit|leasing|pension|fund management|holding company)", "financials"),
    (r"\b(automotive|automobile|car manufactur|motor vehicle|truck|vehicle|auto parts|tyre|tire)", "automotive"),
    (r"\b(pharma|biotech|medical device|medical technology|health ?care equipment|drug|life science)", "pharma"),
    (r"\b(construction|civil engineering|building material|cement|infrastructure|homebuild|house ?build)", "construction"),
    (r"\b(oil|gas|petrole|petroch|energy|mining|coal|refin|commodit)", "energy"),
    (r"\b(electric utility|utility|utilities|electricity|water supply|power generation|electric power)", "utilities"),
    (r"\b(telecom|mobile network|broadband|telephone)", "telecom"),
    (r"\b(retail|supermarket|grocery|department store|e-commerce|fashion retail|clothing retail|wholesale)", "retail"),
    (r"\b(food|beverage|brew|drink|tobacco|consumer goods|cosmetic|personal care|household|apparel|clothing|"
     r"luxury|textile|furniture|confectionery|dairy)", "consumer_goods"),
    (r"\b(logistic|shipping|freight|airline|aviation|railway|rail transport|transport|courier|postal|port)", "logistics"),
    (r"\b(software|semiconductor|internet|information technology|electronics|computer|cloud|video game)", "technology"),
    (r"\b(steel|chemical|aerospace|defen[cs]e|machinery|engineering|industrial|manufactur|conglomerate|metal|"
     r"paper|packaging|glass|plastics|electrical|electronics industry|shipbuilding|arms|aircraft|spaceflight|aviation industry|battery|pulp|tool|robot|elevator|optic)", "manufacturing"),
    (r"\b(consult|outsourc|staffing|media|publishing|broadcast|advertis|hotel|hospitality|restaurant|"
     r"entertainment|gambling|education|health ?care|hospital|facility management|security services|travel)", "services"),
]


def sector_from_text(text: str | None) -> str | None:
    if not text:
        return None
    # vote across the pipe-separated labels; ties go to the earlier (more specific) pattern
    votes: dict[str, int] = {}
    for label in str(text).lower().split("|"):
        for pat, sector in _KEYWORDS:
            if re.search(pat, label):
                votes[sector] = votes.get(sector, 0) + 1
                break
    if not votes:
        return None
    order = [sec for _, sec in _KEYWORDS]
    return sorted(votes, key=lambda k: (-votes[k], order.index(k)))[0]


def classify(sic=None, industry_labels: str | None = None, name: str | None = None) -> tuple[str, str]:
    """Return (sector, method)."""
    s = sector_from_sic(sic)
    if s:
        return s, "sic_code"
    s = sector_from_text(industry_labels)
    if s:
        return s, "wikidata_industry_keyword"
    s = sector_from_text(name)
    if s:
        return s, "name_keyword"
    return "other", "default"
