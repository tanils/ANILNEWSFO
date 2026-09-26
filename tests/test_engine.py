from src.signal_engine import contradiction, trade_status
from src.news_intelligence import _symbols
def test_symbol_mapping(): assert "RELIANCE" in _symbols("Reliance Industries wins order")
def test_contradiction_positive_down(): assert contradiction("positive",{"available":True,"change_pct":-2.1})
def test_no_trade_without_evidence(): assert trade_status(evidence_ok=False,market_data_ok=True,contradiction_flag=False)=="NO TRADE"
def test_wait_on_missing_market_data(): assert trade_status(evidence_ok=True,market_data_ok=False,contradiction_flag=False)=="WAIT"
