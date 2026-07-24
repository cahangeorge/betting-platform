from app.database import async_session_factory
from app.services.trading_execution import execute_paper_intent


async def run_trading_execution(execution_id: int) -> None:
    """Dedicated runner boundary used by both local and queued execution."""
    async with async_session_factory() as db:
        await execute_paper_intent(db, execution_id)
        await db.commit()
