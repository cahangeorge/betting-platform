from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.model_governance import (
    CertificationCreateRequest,
    ModelCertificationListResponse,
    ModelCertificationResponse,
    ModelEvaluationCreateRequest,
    ModelEvaluationDetailResponse,
    ModelEvaluationListResponse,
    ModelEvaluationResponse,
    ModelGovernanceEvidenceResponse,
    ModelMonitoringListResponse,
    ModelMonitoringSnapshotResponse,
    ModelVersionResponse,
    MonitoringSnapshotCreateRequest,
)
from app.services.model_governance import (
    create_certification,
    create_evaluation,
    create_monitoring_snapshot,
    get_evaluation_detail,
    governance_evidence,
    list_certifications,
    list_evaluations,
    list_monitoring_snapshots,
)

router = APIRouter()


def _evaluation_detail_response(evaluation, model_version, folds) -> ModelEvaluationDetailResponse:
    return ModelEvaluationDetailResponse(
        **ModelEvaluationResponse.model_validate(evaluation).model_dump(),
        model_version=ModelVersionResponse.model_validate(model_version),
        folds=folds,
    )


@router.post(
    "/evaluations",
    response_model=ModelEvaluationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model_evaluation(
    payload: ModelEvaluationCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelEvaluationDetailResponse:
    try:
        evaluation, model_version, folds = await create_evaluation(db, user_id=user.id, request=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _evaluation_detail_response(evaluation, model_version, folds)


@router.get("/evaluations", response_model=ModelEvaluationListResponse)
async def get_model_evaluations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelEvaluationListResponse:
    items, total = await list_evaluations(db, user_id=user.id, limit=limit, offset=offset)
    return ModelEvaluationListResponse(
        items=[ModelEvaluationResponse.model_validate(item) for item in items],
        total=total,
    )


@router.get("/evaluations/{evaluation_id}", response_model=ModelEvaluationDetailResponse)
async def get_model_evaluation(
    evaluation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelEvaluationDetailResponse:
    detail = await get_evaluation_detail(db, evaluation_id=evaluation_id, user_id=user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model evaluation not found")
    return _evaluation_detail_response(*detail)


@router.post(
    "/certifications",
    response_model=ModelCertificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model_certification(
    payload: CertificationCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelCertificationResponse:
    try:
        certification = await create_certification(
            db,
            user_id=user.id,
            evaluation_id=payload.evaluation_id,
            validity_days=payload.validity_days,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ModelCertificationResponse.model_validate(certification)


@router.get("/certifications", response_model=ModelCertificationListResponse)
async def get_model_certifications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelCertificationListResponse:
    items, total = await list_certifications(db, user_id=user.id, limit=limit, offset=offset)
    return ModelCertificationListResponse(
        items=[ModelCertificationResponse.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/monitoring",
    response_model=ModelMonitoringSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model_monitoring_snapshot(
    payload: MonitoringSnapshotCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelMonitoringSnapshotResponse:
    try:
        snapshot = await create_monitoring_snapshot(db, user_id=user.id, request=payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ModelMonitoringSnapshotResponse.model_validate(snapshot)


@router.get("/monitoring", response_model=ModelMonitoringListResponse)
async def get_model_monitoring_snapshots(
    model_version_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelMonitoringListResponse:
    items, total = await list_monitoring_snapshots(
        db,
        user_id=user.id,
        model_version_id=model_version_id,
        limit=limit,
        offset=offset,
    )
    return ModelMonitoringListResponse(
        items=[ModelMonitoringSnapshotResponse.model_validate(item) for item in items],
        total=total,
    )


@router.get("/evidence/{model_version_id}", response_model=ModelGovernanceEvidenceResponse)
async def get_model_governance_evidence(
    model_version_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelGovernanceEvidenceResponse:
    evidence = await governance_evidence(db, user_id=user.id, model_version_id=model_version_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found")
    model_version, evaluation, certification, monitoring, gate = evidence
    return ModelGovernanceEvidenceResponse(
        model_version=ModelVersionResponse.model_validate(model_version),
        latest_evaluation=ModelEvaluationResponse.model_validate(evaluation) if evaluation is not None else None,
        latest_certification=(
            ModelCertificationResponse.model_validate(certification) if certification is not None else None
        ),
        latest_monitoring=(
            ModelMonitoringSnapshotResponse.model_validate(monitoring) if monitoring is not None else None
        ),
        gate=gate,
    )
