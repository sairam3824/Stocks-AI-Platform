from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass
class SymbolMatch:
    symbol: str
    name: str
    exchange: str
    exchange_disp: str
    market: str


def _infer_market(symbol: str, exchange: str, exchange_disp: str) -> str:
    sym = (symbol or "").upper()
    exch = (exchange or "").upper()
    exch_disp = (exchange_disp or "").upper()

    if sym.endswith(".NS") or sym.endswith(".BO"):
        return "India"
    if exch in {"NSI", "BSE", "NSE"} or "NSE" in exch_disp or "BSE" in exch_disp:
        return "India"
    if exch in {"NMS", "NYQ", "NAS", "NYSE", "NASDAQ", "ASE"}:
        return "US"
    if sym.endswith(".US"):
        return "US"
    if exch_disp:
        return exch_disp.title()
    if exch:
        return exch
    return "Other"


def _looks_like_symbol(value: str) -> bool:
    if not value:
        return False
    value = value.strip().upper()
    if len(value) > 10:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
    return all(ch in allowed for ch in value)


def search_symbols(
    query: str, source: str = "yahoo", limit: int = 5, timeout: int = 10
) -> List[SymbolMatch]:
    text = (query or "").strip()
    if not text:
        return []

    if source != "yahoo":
        return []

    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": text, "quotesCount": max(limit, 5), "newsCount": 0}
    headers = {"User-Agent": "stocks-ai/1.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []

    payload = response.json()
    results: List[SymbolMatch] = []
    for quote in payload.get("quotes", []):
        quote_type = quote.get("quoteType")
        if quote_type not in ("EQUITY", "ETF"):
            continue
        symbol = quote.get("symbol")
        name = quote.get("shortname") or quote.get("longname") or symbol
        exchange = quote.get("exchange", "")
        exchange_disp = quote.get("exchDisp", "") or quote.get("exchangeDisplay", "")
        if symbol:
            market = _infer_market(symbol, exchange, exchange_disp)
            results.append(
                SymbolMatch(
                    symbol=symbol,
                    name=name or symbol,
                    exchange=exchange,
                    exchange_disp=exchange_disp,
                    market=market,
                )
            )
        if len(results) >= limit:
            break

    return results


def resolve_symbol(query: str, source: str = "yahoo", timeout: int = 10) -> Optional[SymbolMatch]:
    text = (query or "").strip()
    if not text:
        return None

    if _looks_like_symbol(text):
        return SymbolMatch(
            symbol=text.upper(),
            name=text.upper(),
            exchange="",
            exchange_disp="",
            market="Other",
        )

    matches = search_symbols(text, source=source, limit=1, timeout=timeout)
    return matches[0] if matches else None
