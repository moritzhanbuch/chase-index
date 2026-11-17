import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("monitor", Path(__file__).resolve().parents[1] / "aeo" / "monitor.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def test_find_vendors_basic():
    text = "Popular options include Esker, Tipalti, SAP Taulia and Coupa. Newer: Acme Pay."
    assert monitor.find_vendors(text) == ["Esker", "Tipalti", "Coupa", "SAP Taulia"]
    assert monitor.find_vendors(text, brand="Acme Pay") == ["Acme Pay", "Esker", "Tipalti", "Coupa", "SAP Taulia"]
    assert monitor.find_vendors("Try AcmePay.", brand="Acme Pay") == ["Acme Pay"]


def test_bill_is_not_the_common_noun():
    assert "BILL" not in monitor.find_vendors("Pay every bill on time and send the bill early.")
    assert "BILL" in monitor.find_vendors("Smaller firms often use BILL, formerly Bill.com.")


def test_share_of_voice():
    rows = [
        {"provider": "a", "vendors": ["Esker", "Coupa"]},
        {"provider": "a", "vendors": ["Esker"]},
        {"provider": "b", "vendors": ["Acme Pay"]},
        {"provider": "b", "vendors": []},
    ]
    s = monitor.share_of_voice(rows, brand="Acme Pay")
    assert s["overall"]["Esker"] == 0.5
    assert s["overall"]["Acme Pay"] == 0.25
    assert s["by_provider"]["b"]["Acme Pay"] == 0.5
    assert s["n_answers"] == 4


def test_cost_estimate_is_small():
    assert monitor.estimate_cost(list(monitor.PROVIDERS), runs=1) < 1.0
