import math
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import EventConflictError
from app.models import BoxEvent
from app.schemas import EventIn

# 温度相等的容差：JSON 浮点往返后通常位级一致，这里只兜底
_TEMPERATURE_ABS_TOL = 1e-9


def _same_content(existing: BoxEvent, data: EventIn) -> bool:
    return (
        math.isclose(
            existing.temperature, data.temperature, abs_tol=_TEMPERATURE_ABS_TOL
        )
        and existing.event_time == data.event_time
    )


def ingest_event(db: Session, data: EventIn) -> tuple[BoxEvent, bool]:
    """接收一个事件。

    返回 (事件记录, 是否重复)：
    - 序号不存在               -> 入库，duplicate=False
    - 序号存在且内容完全一致   -> 幂等返回，不改变任何状态，duplicate=True
    - 序号存在但内容不一致     -> 抛出 EventConflictError（HTTP 409）
    """
    existing = db.scalar(
        select(BoxEvent).where(
            BoxEvent.box_code == data.box_code, BoxEvent.seq == data.seq
        )
    )

    if existing is not None:
        if _same_content(existing, data):
            # 重复上报：原样返回，不更新 received_at，也不改变最新状态
            return existing, True
        raise EventConflictError(data.box_code, data.seq)

    event = BoxEvent(
        box_code=data.box_code,
        seq=data.seq,
        temperature=data.temperature,
        event_time=data.event_time,
        received_at=datetime.utcnow(),
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # 并发重试：两个相同 (箱号, 序号) 的请求同时通过了上面的 SELECT，
        # 唯一约束保证只有一个 INSERT 成功；回滚后重查按幂等/冲突规则处理。
        db.rollback()
        existing = db.scalar(
            select(BoxEvent).where(
                BoxEvent.box_code == data.box_code, BoxEvent.seq == data.seq
            )
        )
        if existing is not None:
            if _same_content(existing, data):
                return existing, True
            raise EventConflictError(data.box_code, data.seq)
        raise  # 非唯一约束导致的完整性错误，原样抛出
    db.refresh(event)
    return event, False


def get_latest_state(db: Session, box_code: str) -> BoxEvent | None:
    """按序号（而非入库顺序）返回该箱子最新的一条事件。

    乱序上报的事件入库后，序号最大者即为最新状态。
    """
    return db.scalar(
        select(BoxEvent)
        .where(BoxEvent.box_code == box_code)
        .order_by(BoxEvent.seq.desc())
        .limit(1)
    )


def list_latest_states(db: Session) -> list[BoxEvent]:
    """返回所有箱子按序号计算出的最新状态。"""
    # 每个箱号对应的最大序号
    latest_seq_subq = (
        select(BoxEvent.box_code, func.max(BoxEvent.seq).label("max_seq"))
        .group_by(BoxEvent.box_code)
        .subquery()
    )
    rows = db.scalars(
        select(BoxEvent)
        .join(
            latest_seq_subq,
            (BoxEvent.box_code == latest_seq_subq.c.box_code)
            & (BoxEvent.seq == latest_seq_subq.c.max_seq),
        )
        .order_by(BoxEvent.box_code.asc())
    ).all()
    return list(rows)


def list_box_codes(db: Session) -> list[str]:
    rows = db.scalars(
        select(BoxEvent.box_code)
        .distinct()
        .order_by(BoxEvent.box_code.asc())
    ).all()
    return list(rows)


def list_events(
    db: Session, box_code: str, limit: int, offset: int
) -> tuple[list[BoxEvent], int]:
    """分页返回某箱子的事件历史，按序号升序。"""
    total = db.scalar(
        select(func.count())
        .select_from(BoxEvent)
        .where(BoxEvent.box_code == box_code)
    ) or 0
    rows = db.scalars(
        select(BoxEvent)
        .where(BoxEvent.box_code == box_code)
        .order_by(BoxEvent.seq.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total
