"""Bring your own data: optional local files that re-rank the queue.

Slots (all optional, formats in config/byod/README.md): network_suppliers.csv, crm_accounts.csv,
dinner_attendees.csv, investor_links.csv, plus the status file config/status/accounts_status.csv.
With demo=True the clearly labelled SYNTHETIC set in config/byod/demo/ is used instead.
Nothing is sent anywhere. Unmatched names are reported, never guessed.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from chase import query as q

ROOT = q.ROOT
BYOD = ROOT / "config" / "byod"
STATUS = ROOT / "config" / "status"
SLOTS = ["network_suppliers", "crm_accounts", "dinner_attendees", "investor_links"]
FINAL_STATUSES = {"won", "lost", "not_a_fit"}
VALID_STATUSES = {"contacted", "meeting"} | FINAL_STATUSES
CONTACT_HOLD_DAYS = 21


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, comment="#", dtype=str).fillna("")


def load(demo: bool = False) -> dict:
    """Return {'mode', 'slots': {name: DataFrame|None}, 'status': DataFrame|None, 'paths': {...}}."""
    base = BYOD / "demo" if demo else BYOD
    slots = {s: _read(base / f"{s}.csv") for s in SLOTS}
    status_path = STATUS / ("demo_accounts_status.csv" if demo else "accounts_status.csv")
    return {"mode": "SYNTHETIC demo data" if demo else "your local files", "slots": slots, "status": _read(status_path),
            "paths": {**{s: str((base / f"{s}.csv").relative_to(ROOT)) for s in SLOTS}, "status": str(status_path.relative_to(ROOT))}}


def status_summary(demo: bool = False) -> dict:
    d = load(demo)
    out = {"mode": d["mode"], "slots": {}}
    for s, df in d["slots"].items():
        out["slots"][s] = {"present": df is not None, "rows": 0 if df is None else int(len(df)), "path": d["paths"][s]}
    st = d["status"]
    out["status_file"] = {"present": st is not None, "rows": 0 if st is None else int(len(st)), "path": d["paths"]["status"],
                          "by_status": {} if st is None else st.status.str.lower().value_counts().to_dict()}
    out["formats"] = "config/byod/README.md and config/status/README.md"
    return out


def apply(demo: bool = False) -> tuple[dict[str, dict], list[dict]]:
    """Flags per company_id, plus the list of names that could not be matched."""
    d = load(demo)
    flags: dict[str, dict] = {}
    unmatched: list[dict] = []

    def f(cid: str) -> dict:
        return flags.setdefault(cid, {})

    def res(name: str, slot: str) -> str | None:
        cid = q.resolve(name) if name else None
        if not cid and name:
            unmatched.append({"slot": slot, "name": name})
        return cid

    net = d["slots"]["network_suppliers"]
    if net is not None:
        comp = q.companies().set_index("company_id")
        buyers = net[net.account_type.str.lower() == "buyer"]
        for r in buyers.itertuples():
            cid = q.resolve(r.name)          # a network buyer need not be in the index: no unmatched entry
            if cid:
                f(cid)["already_customer"] = True
        for r in net[net.account_type.str.lower() == "supplier"].itertuples():
            for cust in [c.strip() for c in str(getattr(r, "known_customers", "")).split("|") if c.strip()]:
                cid = res(cust, "network_suppliers.known_customers")
                if cid:
                    f(cid).setdefault("warm_via_supplier", []).append(r.name)
        peers = {(str(r.sector).lower(), str(r.country).upper()) for r in buyers.itertuples() if r.sector and r.country}
        if peers:
            for cid, row in comp.iterrows():
                if (row.sector, row.country) in peers and not flags.get(cid, {}).get("already_customer"):
                    f(cid)["peer_on_network"] = True

    crm = d["slots"]["crm_accounts"]
    if crm is not None:
        for r in crm.itertuples():
            cid = res(r.account_name, "crm_accounts")
            if not cid:
                continue
            stage = str(r.stage).strip().lower()
            if stage in ("closed_lost", "disqualified"):
                f(cid)["crm_closed"] = stage
            else:
                f(cid)["in_pipeline"] = {"stage": r.stage, "owner": getattr(r, "owner", ""), "last_touch": getattr(r, "last_touch", "")}

    din = d["slots"]["dinner_attendees"]
    if din is not None:
        for r in din.itertuples():
            cid = res(r.account_name, "dinner_attendees")
            if cid:
                f(cid).setdefault("dinners", []).append({"city": str(r.city).lower(), "date": r.date if isinstance(r.date, str) and r.date.strip() else None, "status": str(r.status).lower()})

    inv = d["slots"]["investor_links"]
    if inv is not None:
        for r in inv.itertuples():
            cid = res(r.account_name, "investor_links")
            if cid:
                f(cid).setdefault("investor_links", []).append({"investor": r.investor, "relationship": getattr(r, "relationship", "")})

    st = d["status"]
    if st is not None and len(st):
        st = st.copy()
        st["status"] = st.status.str.strip().str.lower()
        st = st[st.status.isin(VALID_STATUSES)].sort_values("date")
        for r in st.itertuples():
            cid = r.company_id if getattr(r, "company_id", "") in set(q.companies().company_id) else res(getattr(r, "company", ""), "accounts_status")
            if cid:
                f(cid)["status"] = {"status": r.status, "reason": getattr(r, "reason", ""), "date": r.date, "play": getattr(r, "play", "")}
    return flags, unmatched
