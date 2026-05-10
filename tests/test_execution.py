from pathlib import Path

from src.config import PortfolioConfig
from src.db import (
    approve_trade,
    create_run,
    create_trade_intent,
    create_user,
    get_trade_by_id,
    get_user_workspace_id,
    init_db,
    list_trades,
)
from src.execution import execute_trade_with_adapter


def _make_approved_trade(db_path: Path):
    user = create_user(db_path, "trade@example.com", "hash")
    workspace_id = get_user_workspace_id(db_path, user.id)
    run = create_run(db_path, user.id, workspace_id)
    create_trade_intent(
        db_path,
        user_id=user.id,
        workspace_id=workspace_id,
        run_id=run.id,
        symbol="AAPL",
        side="BUY",
        reference_price=100.0,
        expected_return_pct=3.0,
        confidence_pct=80.0,
        reasoning="unit test",
        quantity=1.0,
        mode="PAPER",
    )
    trades = list_trades(db_path, user.id, workspace_id=workspace_id, limit=10)
    trade = trades[0]
    approve_trade(db_path, user.id, trade.id)
    approved = get_trade_by_id(db_path, user.id, trade.id)
    assert approved is not None
    return user, workspace_id, approved


def test_paper_broker_adapter_executes_trade(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user, _, trade = _make_approved_trade(db_path)
    config = PortfolioConfig(portfolio_name="p", tickers=[])
    config.broker_mode = "paper"

    result = execute_trade_with_adapter(db_path, user.id, trade, executed_price=101.25, config=config)
    assert result.success is True
    updated = get_trade_by_id(db_path, user.id, trade.id)
    assert updated is not None
    assert updated.status == "EXECUTED"


def test_live_broker_adapter_blocks_when_disabled(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user, _, trade = _make_approved_trade(db_path)
    config = PortfolioConfig(portfolio_name="p", tickers=[])
    config.broker_mode = "live"
    config.allow_live_execution = False
    config.live_broker_name = "webull"

    result = execute_trade_with_adapter(db_path, user.id, trade, executed_price=101.25, config=config)
    assert result.success is False
    updated = get_trade_by_id(db_path, user.id, trade.id)
    assert updated is not None
    assert updated.status == "APPROVED"
