from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import BoxStateOut, EventOut
from app.services import (
    get_latest_state,
    list_box_codes,
    list_events,
    list_latest_states,
)

router = APIRouter(prefix="/api/v1/boxes", tags=["boxes"])


@router.get(
    "",
    response_model=list[BoxStateOut],
    summary="获取所有箱子的最新状态（按序号计算）",
)
def get_boxes(db: Session = Depends(get_db)) -> list[BoxStateOut]:
    return [BoxStateOut(box_code=e.box_code, state=EventOut.model_validate(e))
            for e in list_latest_states(db)]


@router.get(
    "/{box_code}",
    response_model=BoxStateOut,
    summary="获取指定箱子的最新状态",
)
def get_box(box_code: str, db: Session = Depends(get_db)) -> BoxStateOut:
    box_code = box_code.strip().upper()
    state = get_latest_state(db, box_code)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"箱子 {box_code} 暂无事件",
        )
    return BoxStateOut(box_code=box_code, state=EventOut.model_validate(state))


@router.get(
    "/{box_code}/events",
    response_model=list[EventOut],
    summary="分页查询指定箱子的事件历史（按序号升序）",
)
def get_box_events(
    box_code: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    box_code = box_code.strip().upper()
    if box_code not in list_box_codes(db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"箱子 {box_code} 暂无事件",
        )
    rows, _ = list_events(db, box_code, limit, offset)
    return [EventOut.model_validate(r) for r in rows]
