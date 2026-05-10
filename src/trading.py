from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .recommendations import Recommendation


@dataclass
class TradeCandidate:
    symbol: str
    side: str
    reference_price: float
    expected_return_pct: float
    confidence_pct: float
    reasoning: str


def side_from_signal(signal: str) -> str:
    signal_norm = (signal or "").strip().lower()
    if signal_norm == "upside":
        return "BUY"
    if signal_norm == "downside":
        return "SELL"
    return "HOLD"


def build_trade_candidates(
    recommendations: Iterable[Recommendation],
    top_n: int,
    min_confidence_pct: float = 55.0,
) -> List[TradeCandidate]:
    ranked = sorted(recommendations, key=lambda r: r.score, reverse=True)
    candidates: List[TradeCandidate] = []
    for rec in ranked:
        side = side_from_signal(rec.signal)
        if side == "HOLD":
            continue
        if rec.confidence_pct < min_confidence_pct:
            continue
        candidates.append(
            TradeCandidate(
                symbol=rec.symbol,
                side=side,
                reference_price=rec.last_close,
                expected_return_pct=rec.expected_return_pct,
                confidence_pct=rec.confidence_pct,
                reasoning=rec.reasoning,
            )
        )
        if len(candidates) >= max(1, top_n):
            break
    return candidates
