from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import PortfolioConfig
from .db import Trade, execute_trade
from .observability import increment_counter, log_event


@dataclass
class ExecutionResult:
    success: bool
    message: str
    executed_price: float
    broker_mode: str
    broker_name: str


class BrokerAdapter:
    broker_mode = "paper"
    broker_name = "paper"

    def execute(
        self,
        db_path: Path,
        user_id: int,
        trade: Trade,
        executed_price: float,
        config: PortfolioConfig,
    ) -> ExecutionResult:
        raise NotImplementedError


class PaperBrokerAdapter(BrokerAdapter):
    broker_mode = "paper"
    broker_name = "paper-sim"

    def execute(
        self,
        db_path: Path,
        user_id: int,
        trade: Trade,
        executed_price: float,
        config: PortfolioConfig,
    ) -> ExecutionResult:
        execute_trade(db_path, user_id, trade.id, executed_price=executed_price)
        increment_counter("broker_execute_paper", 1.0)
        log_event("broker_execute_paper", user_id=user_id, trade_id=trade.id, symbol=trade.symbol, price=executed_price)
        return ExecutionResult(
            success=True,
            message=f"Paper trade executed at {executed_price:.2f}.",
            executed_price=executed_price,
            broker_mode=self.broker_mode,
            broker_name=self.broker_name,
        )


class SimulatedLiveBrokerAdapter(BrokerAdapter):
    broker_mode = "live"

    def __init__(self, broker_name: str) -> None:
        self.broker_name = broker_name or "webull"

    def execute(
        self,
        db_path: Path,
        user_id: int,
        trade: Trade,
        executed_price: float,
        config: PortfolioConfig,
    ) -> ExecutionResult:
        if not config.allow_live_execution:
            increment_counter("broker_execute_live_blocked", 1.0)
            return ExecutionResult(
                success=False,
                message="Live execution is disabled. Enable allow_live_execution in config first.",
                executed_price=executed_price,
                broker_mode=self.broker_mode,
                broker_name=self.broker_name,
            )
        # Live broker wiring point: replace this simulation with real API order placement.
        execute_trade(db_path, user_id, trade.id, executed_price=executed_price)
        increment_counter("broker_execute_live_simulated", 1.0)
        log_event(
            "broker_execute_live_simulated",
            user_id=user_id,
            trade_id=trade.id,
            symbol=trade.symbol,
            broker=self.broker_name,
            price=executed_price,
        )
        return ExecutionResult(
            success=True,
            message=f"Simulated live order sent via {self.broker_name} at {executed_price:.2f}.",
            executed_price=executed_price,
            broker_mode=self.broker_mode,
            broker_name=self.broker_name,
        )


def get_broker_adapter(config: PortfolioConfig) -> BrokerAdapter:
    mode = (config.broker_mode or "paper").strip().lower()
    if mode == "live":
        return SimulatedLiveBrokerAdapter(config.live_broker_name)
    return PaperBrokerAdapter()


def execute_trade_with_adapter(
    db_path: Path,
    user_id: int,
    trade: Trade,
    executed_price: float,
    config: PortfolioConfig,
) -> ExecutionResult:
    adapter = get_broker_adapter(config)
    return adapter.execute(db_path=db_path, user_id=user_id, trade=trade, executed_price=executed_price, config=config)
