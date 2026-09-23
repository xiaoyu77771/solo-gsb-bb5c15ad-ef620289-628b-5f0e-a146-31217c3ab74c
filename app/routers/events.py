from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import EventAck, EventIn
from app.services import get_latest_state, ingest_event

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post(
    "",
    response_model=EventAck,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "相同序号但内容不同"}},
    summary="上报冷链周转箱事件",
)
def post_event(
    payload: EventIn,
    response: Response,
    db: Session = Depends(get_db),
) -> EventAck:
    """设备上报一个温度事件。

    - 首次收到（箱号 + 序号）：**201 Created**，事件入库
    - 相同序号、相同温度与事件时间（设备重试/重复投递）：**200 OK**，
      幂等返回，不改变任何状态（`duplicate=true`）
    - 相同序号但温度/事件时间不同：**409 Conflict**，事件被拒绝
    - 允许乱序上报；最新状态始终按最大序号计算
    """
    event, duplicate = ingest_event(db, payload)
    if duplicate:
        response.status_code = status.HTTP_200_OK

    state = get_latest_state(db, payload.box_code)
    # 当前写入路径下 state 必不为 None
    assert state is not None
    return EventAck(event=event, duplicate=duplicate, state=state)
