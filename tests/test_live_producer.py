from src.live_producer import _extract_twelve_data_price


def test_extract_twelve_data_price_prefers_close_when_price_missing() -> None:
    quote = {"close": "187.42", "previous_close": "186.99"}
    assert _extract_twelve_data_price(quote) == 187.42


def test_extract_twelve_data_price_uses_price_when_available() -> None:
    quote = {"price": "188.15", "close": "187.42"}
    assert _extract_twelve_data_price(quote) == 188.15
