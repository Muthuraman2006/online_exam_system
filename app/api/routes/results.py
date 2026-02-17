from typing import Annotated, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import ResultResponse
from app.services.result_service import ResultService
from app.api.deps.auth import StudentOnly, AnyAuthenticated

router = APIRouter(prefix="/results", tags=["Results"])


@router.get("", response_model=List[ResultResponse])
async def get_my_results(
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get all results for current student."""
    service = ResultService(db)
    return await service.get_student_results(current_user.id)


@router.get("/{result_id}", response_model=ResultResponse)
async def get_result(
    result_id: int,
    current_user: AnyAuthenticated,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get specific result (with access control)."""
    service = ResultService(db)
    return await service.get_result_by_id(result_id, current_user)
