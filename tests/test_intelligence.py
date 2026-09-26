from src.news_intelligence import _materiality, _symbols, build_ai_payload

def test_materiality_is_bounded():
    assert 1 <= _materiality("major order announced", "new contract", ["ABC"]) <= 10

def test_known_symbol_detection():
    assert "RELIANCE" in _symbols("Reliance Industries announces capex")

def test_payload_shape():
    payload = build_ai_payload([], "pre_market")
    assert payload["phase"] == "pre_market"
    assert payload["items"] == []
