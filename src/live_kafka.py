from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Dict

from kafka import KafkaConsumer


@dataclass
class LivePrice:
    symbol: str
    price: float
    timestamp: str
    source: str
    market_open: bool


def start_consumer(
    cache: Dict[str, LivePrice],
    lock: threading.Lock,
    bootstrap_servers: str,
    topic: str,
) -> threading.Thread:
    def _run() -> None:
        while True:
            consumer = None
            try:
                consumer = KafkaConsumer(
                    topic,
                    bootstrap_servers=bootstrap_servers,
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                )
                for message in consumer:
                    data = message.value or {}
                    symbol = str(data.get("symbol", "")).upper()
                    if not symbol:
                        continue
                    price = float(data.get("price", 0) or 0)
                    timestamp = str(data.get("timestamp") or "")
                    source = str(data.get("source") or "")
                    market_open = bool(data.get("market_open", True))
                    with lock:
                        cache[symbol] = LivePrice(
                            symbol=symbol,
                            price=price,
                            timestamp=timestamp,
                            source=source,
                            market_open=market_open,
                        )
            except Exception:
                time.sleep(3)
            finally:
                try:
                    if consumer is not None:
                        consumer.close()
                except Exception:
                    pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
