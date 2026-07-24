from app.services.trading_runner import run_trading_execution
from app.tasks.trading_broker import trading_broker


@trading_broker.task(task_name="app.tasks.trading:execute_trading_intent_task")
async def execute_trading_intent_task(execution_id: int) -> None:
    await run_trading_execution(execution_id)
