from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests


@dataclass
class PriceHistoryRequest:
    symbol: str
    years: int = 5
    source: str = "stooq"
    alpha_vantage_api_key: Optional[str] = None
    symbol_override: Optional[str] = None


def _normalize_stooq_symbol(symbol: str) -> str:
    sym = symbol.strip().lower()
    if "." not in sym:
        sym = f"{sym}.us"
    return sym


def fetch_stooq_daily(symbol: str, symbol_override: Optional[str] = None) -> pd.DataFrame:
    stooq_symbol = _normalize_stooq_symbol(symbol_override or symbol)
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    df = pd.read_csv(url)
    if df.empty:
        return df
    df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        },
        inplace=True,
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    return df


def fetch_alpha_vantage_daily(symbol: str, api_key: str) -> pd.DataFrame:
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": "full",
        "apikey": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    series = payload.get("Time Series (Daily)", {})
    if not series:
        return pd.DataFrame()

    rows = []
    for date_str, values in series.items():
        rows.append(
            {
                "date": pd.to_datetime(date_str),
                "open": float(values.get("1. open", 0) or 0),
                "high": float(values.get("2. high", 0) or 0),
                "low": float(values.get("3. low", 0) or 0),
                "close": float(values.get("4. close", 0) or 0),
                "volume": float(values.get("6. volume", 0) or 0),
            }
        )
    df = pd.DataFrame(rows).sort_values("date")
    return df


def fetch_twelve_data_intraday(
    symbol: str,
    api_key: str,
    interval_minutes: int = 5,
    outputsize: int = 500,
) -> pd.DataFrame:
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": f"{interval_minutes}min",
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    values = payload.get("values", [])
    if not values:
        return pd.DataFrame()

    rows = []
    for row in values:
        rows.append(
            {
                "date": pd.to_datetime(row.get("datetime")),
                "open": float(row.get("open", 0) or 0),
                "high": float(row.get("high", 0) or 0),
                "low": float(row.get("low", 0) or 0),
                "close": float(row.get("close", 0) or 0),
                "volume": float(row.get("volume", 0) or 0),
            }
        )
    df = pd.DataFrame(rows).sort_values("date")
    return df


def fetch_twelve_data_quote(symbol: str, api_key: str) -> dict:
    url = "https://api.twelvedata.com/quote"
    params = {
        "symbol": symbol,
        "apikey": api_key,
        "format": "JSON",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_alpha_vantage_quote(symbol: str, api_key: str) -> dict:
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("Global Quote", {})


def fetch_yahoo_quote(symbol: str) -> dict:
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": symbol}
    headers = {"User-Agent": "stocks-ai/1.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("quoteResponse", {}).get("result", [])
    return results[0] if results else {}


def fetch_alpha_vantage_intraday(
    symbol: str,
    api_key: str,
    interval_minutes: int = 5,
    outputsize: str = "compact",
) -> pd.DataFrame:
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": f"{interval_minutes}min",
        "outputsize": outputsize,
        "apikey": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    key = f"Time Series ({interval_minutes}min)"
    series = payload.get(key, {})
    if not series:
        return pd.DataFrame()

    rows = []
    for date_str, values in series.items():
        rows.append(
            {
                "date": pd.to_datetime(date_str),
                "open": float(values.get("1. open", 0) or 0),
                "high": float(values.get("2. high", 0) or 0),
                "low": float(values.get("3. low", 0) or 0),
                "close": float(values.get("4. close", 0) or 0),
                "volume": float(values.get("5. volume", 0) or 0),
            }
        )
    df = pd.DataFrame(rows).sort_values("date")
    return df


def get_price_history(request: PriceHistoryRequest) -> pd.DataFrame:
    source = (request.source or "stooq").strip().lower()
    if source == "alpha_vantage":
        if not request.alpha_vantage_api_key:
            df = fetch_stooq_daily(request.symbol, request.symbol_override)
        else:
            df = fetch_alpha_vantage_daily(request.symbol, request.alpha_vantage_api_key)
    else:
        df = fetch_stooq_daily(request.symbol, request.symbol_override)

    if df.empty:
        return df

    cutoff = pd.Timestamp(dt.date.today()) - pd.DateOffset(years=request.years)
    df = df[df["date"] >= cutoff]
    return df.reset_index(drop=True)
