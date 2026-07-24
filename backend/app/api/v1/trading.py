from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.betfair_readonly import BetfairReadOnlyAdapter
from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.trading import TradingAccount
from app.models.user import User
from app.schemas.trading import (
    ExecutionCreateRequest,
    ExecutionResponse,
    TradingAccountCreateRequest,
    TradingAccountHealthResponse,
    TradingAccountResponse,
)
from app.services.trading_delivery import TradingDeliveryError, publish_trading_intent
from app.services.trading_execution import (
    cancel_execution,
    create_execution_intent,
    execute_paper_intent,
    load_execution,
)

router = APIRouter()


@router.get("/accounts", response_model=list[TradingAccountResponse])
async def list_trading_accounts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TradingAccount).where(TradingAccount.user_id == user.id).order_by(TradingAccount.created_at.desc())
    )
    return result.scalars().all()


@router.post("/accounts", response_model=TradingAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_trading_account(
    body: TradingAccountCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = get_settings()
    if not settings.trading_enabled or not settings.trading_paper_enabled:
        raise HTTPException(status_code=403, detail="Paper trading execution is disabled")
    account = TradingAccount(
        user_id=user.id,
        name=body.name.strip(),
        provider="paper-local",
        mode="paper",
        currency=body.currency.upper(),
        balance=Decimal(str(body.initial_balance)),
        enabled=True,
    )
    db.add(account)
    await db.flush()
    return account


@router.get("/accounts/{account_id}/health", response_model=TradingAccountHealthResponse)
async def trading_account_health(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = await db.get(TradingAccount, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Trading account not found")
    settings = get_settings()
    betfair_health = await BetfairReadOnlyAdapter(settings).health()
    healthy = (
        settings.trading_enabled
        and settings.trading_paper_enabled
        and account.enabled
        and account.mode == "paper"
        and account.provider == "paper-local"
    )
    return TradingAccountHealthResponse(
        account_id=account.id,
        status="healthy" if healthy else "disabled",
        mode=account.mode,
        provider=account.provider,
        enabled=account.enabled,
        paper_execution_enabled=settings.trading_enabled and settings.trading_paper_enabled,
        live_execution_enabled=False,
        betfair_read_only_status=betfair_health.status,
        message=(
            "Local paper execution is ready. No credentials are loaded and no external orders can be sent."
            if healthy
            else "This account cannot accept paper executions."
        ),
    )


@router.post("/executions", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_execution(
    body: ExecutionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        intent, _created = await create_execution_intent(
            db,
            user_id=user.id,
            trading_account_id=body.trading_account_id,
            ticket_id=body.ticket_id,
            idempotency_key=body.idempotency_key,
            side=body.side,
            order_type=body.order_type,
        )
        settings = get_settings()
        if settings.task_queue_backend == "inprocess":
            if intent.status == "queued" and intent.delivery_status != "completed":
                intent.transport = "inprocess"
                intent.delivery_attempts += 1
                await execute_paper_intent(db, intent.id)
        elif intent.status == "queued" and intent.delivery_status in {"pending", "failed", "publishing"}:
            # Persist before the worker consumes the identifier. Reusing the
            # same idempotency key republishes durable failed deliveries.
            await db.commit()
            await publish_trading_intent(db, intent)
        loaded = await load_execution(db, intent.id, user.id)
        if loaded is None:
            raise RuntimeError("Execution could not be reloaded")
        return loaded
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TradingDeliveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    execution = await load_execution(db, execution_id, user.id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_trading_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await cancel_execution(db, execution_id, user.id)
        execution = await load_execution(db, execution_id, user.id)
        if execution is None:
            raise LookupError("Execution not found")
        return execution
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
