from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BoxEvent(Base):
    """冷链周转箱上报事件。

    同一箱号下的序号唯一：
    - 相同序号 + 相同温度/事件时间 => 幂等重复
    - 相同序号 + 不同内容        => 冲突拒绝
    """

    __tablename__ = "box_events"
    __table_args__ = (
        UniqueConstraint(
            "box_code", "seq", name="uq_box_events_box_code_seq"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    box_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
