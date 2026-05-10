from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

from .news import NewsItem


@dataclass
class SentimentResult:
    score: float
    label: str


_POSITIVE_TERMS = {
    "beat": 1.0,
    "beats": 1.0,
    "growth": 0.8,
    "surge": 1.1,
    "rally": 1.0,
    "bullish": 1.1,
    "upgrade": 0.9,
    "upgrades": 0.9,
    "outperform": 1.0,
    "buy": 0.6,
    "strong": 0.6,
    "record": 0.8,
    "profit": 0.7,
    "profits": 0.7,
    "guidance": 0.5,
    "partnership": 0.6,
    "momentum": 0.7,
}

_NEGATIVE_TERMS = {
    "miss": 1.0,
    "misses": 1.0,
    "decline": 0.8,
    "drop": 0.8,
    "drops": 0.8,
    "selloff": 1.1,
    "bearish": 1.1,
    "downgrade": 0.9,
    "downgrades": 0.9,
    "underperform": 1.0,
    "sell": 0.6,
    "weak": 0.6,
    "loss": 0.8,
    "losses": 0.8,
    "probe": 0.9,
    "lawsuit": 1.0,
    "cuts": 0.7,
    "cut": 0.7,
    "warns": 0.9,
    "warning": 0.9,
}

_NEGATIONS = {"not", "no", "never", "without", "hardly"}
_TOKENIZER = re.compile(r"[a-zA-Z']+")


def _label_from_score(score: float) -> str:
    if score >= 0.2:
        return "Positive"
    if score <= -0.2:
        return "Negative"
    return "Neutral"


def _extract_json(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def analyze_sentiment_ollama(
    items: List[NewsItem],
    model: str,
    url: str,
    timeout: int = 20,
) -> Optional[SentimentResult]:
    if not items:
        return None

    headlines = "\n".join(f"- {item.title}" for item in items)
    prompt = (
        "You are a financial news sentiment analyst. "
        "Given the headlines, return ONLY valid JSON with keys 'score' and 'label'. "
        "Score must be between -1 and 1, label is Positive, Neutral, or Negative.\n\n"
        f"Headlines:\n{headlines}\n"
    )

    try:
        response = requests.post(
            f"{url.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    payload = response.json()
    text = (payload.get("response") or "").strip()
    raw_json = _extract_json(text)
    if not raw_json:
        return None

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None

    try:
        score = float(data.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0

    score = max(min(score, 1.0), -1.0)
    raw_label = str(data.get("label") or "").strip().lower()
    if raw_label.startswith("pos"):
        label = "Positive"
    elif raw_label.startswith("neg"):
        label = "Negative"
    elif raw_label.startswith("neu"):
        label = "Neutral"
    else:
        label = _label_from_score(score)

    return SentimentResult(score=score, label=label)


def _score_text_lexicon(text: str) -> float:
    if not text.strip():
        return 0.0
    tokens = _TOKENIZER.findall(text.lower())
    if not tokens:
        return 0.0

    score = 0.0
    for idx, token in enumerate(tokens):
        term_score = _POSITIVE_TERMS.get(token)
        if term_score is not None:
            polarity = 1.0
        else:
            term_score = _NEGATIVE_TERMS.get(token)
            if term_score is None:
                continue
            polarity = -1.0
        if idx > 0 and tokens[idx - 1] in _NEGATIONS:
            polarity *= -1.0
        score += polarity * term_score
    normalizer = max(3.0, len(tokens) ** 0.5)
    return max(-1.0, min(1.0, score / normalizer))


def analyze_sentiment_lexicon(items: List[NewsItem]) -> Optional[SentimentResult]:
    if not items:
        return None
    scores: List[float] = []
    for item in items:
        text = " ".join(part for part in (item.title, item.summary) if part)
        value = _score_text_lexicon(text)
        if value != 0.0:
            scores.append(value)
    if not scores:
        return SentimentResult(score=0.0, label="Neutral")
    score = max(-1.0, min(1.0, sum(scores) / len(scores)))
    return SentimentResult(score=score, label=_label_from_score(score))


def analyze_sentiment(
    items: List[NewsItem],
    provider: str = "auto",
    ollama_model: str = "llama3.1",
    ollama_url: str = "http://localhost:11434",
    llm_weight: float = 0.7,
) -> Optional[SentimentResult]:
    if not items:
        return None

    provider = (provider or "auto").strip().lower()
    llm_weight = max(0.0, min(1.0, llm_weight))
    lexicon_result = analyze_sentiment_lexicon(items)

    if provider in ("lexicon", "rule_based"):
        return lexicon_result

    llm_result = None
    if ollama_model:
        llm_result = analyze_sentiment_ollama(items, ollama_model, ollama_url)

    if provider in ("ollama", "llm"):
        return llm_result or lexicon_result

    if llm_result and lexicon_result:
        score = (llm_weight * llm_result.score) + ((1.0 - llm_weight) * lexicon_result.score)
        score = max(-1.0, min(1.0, score))
        return SentimentResult(score=score, label=_label_from_score(score))

    return llm_result or lexicon_result
