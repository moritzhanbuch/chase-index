PY := .venv/bin/python
# Reproduce from the local cache without fetching anything new:
#   make all ESEF_ARGS=--no-download CH_ARGS=--skip-download
ESEF_ARGS ?=
CH_ARGS ?=

.PHONY: dach features setup data uk sec esef wikidata chbulk spain universe score assets site docs evals test skill-demo mcp-demo triggers queue exports feedback weekly workspace all clean-build

setup:
	uv venv .venv --python 3.11 || python3 -m venv .venv
	uv pip install -p $(PY) -r requirements.txt || .venv/bin/pip install -r requirements.txt
	uv pip install -p $(PY) -e . || .venv/bin/pip install -e .
	$(PY) -m playwright install chromium

# --- data (all steps are cache-backed: reruns do not re-download) ---
uk:
	$(PY) -m chase.sources.uk_payment_practices
sec:
	$(PY) -m chase.sources.sec_xbrl
esef:
	$(PY) -m chase.sources.esef_xbrl $(ESEF_ARGS)
wikidata:
	$(PY) -m chase.sources.wikidata
chbulk:
	$(PY) -m chase.sources.companies_house_bulk $(CH_ARGS)
spain:
	$(PY) -m chase.sources.spain_pmp
	$(PY) -m chase.sources.spain_reconcile
	$(PY) -m chase.sources.spain_reconcile --final
universe: dach
	$(PY) -m chase.resolve.universe
	$(PY) -m chase.resolve.uk_rollup
	$(PY) -m chase.sources.dpo

data: uk sec esef wikidata chbulk spain universe

# DACH slice: computed DPO from annual reports (Bavarian DAX/MDAX + CH/AT industrials).
# Offline: rebuilds dach_dpo from the committed extractions and adjudication. The download and both
# extractors run with: python -m chase.sources.dach_slice members|targets|docs|extract-a (B and QA are agent steps)
dach:
	$(PY) -m chase.sources.dach_slice reconcile
	$(PY) -m chase.sources.dach_slice final

# Phase 12 features: UK filing fields and supplier finance (reconcile applies the QA adjudication)
features:
	$(PY) -m chase.enrich.uk_fields
	$(PY) -m chase.sources.supplier_finance_reconcile --final

score:
	$(PY) -m chase.score.build

assets:
	$(PY) -m chase.assets.build

site:
	$(PY) docs/build_data_dictionary.py
	$(PY) site/build.py

evals:
	$(PY) evals/calibrate.py "make evals"
	$(PY) evals/validate_copy.py
	$(PY) evals/findings.py > /dev/null
	$(PY) evals/skill_demo.py
	$(PY) mcp/demo_client.py
	$(PY) evals/external_validation.py > /dev/null

# --- weekly workflow (DEMO=1 uses the SYNTHETIC bring-your-own-data set) ---
DEMO_FLAG := $(if $(DEMO),--demo,)
triggers:
	$(PY) -m chase.gtm.triggers
queue:
	$(PY) -m chase.gtm.nba $(DEMO_FLAG)
exports:
	$(PY) -m chase.gtm.exports $(DEMO_FLAG)
feedback:
	$(PY) -m chase.gtm.feedback $(DEMO_FLAG)
weekly: queue exports

# internal GTM workspace (static, noindex, public data only): builds workspace/dist
workspace:
	$(PY) workspace/build.py

test:
	$(PY) -m pytest -q

skill-demo:
	$(PY) evals/skill_demo.py

mcp-demo:
	$(PY) mcp/demo_client.py

all: data features score triggers weekly assets site workspace evals test

clean-build:
	rm -rf site/dist build/*
