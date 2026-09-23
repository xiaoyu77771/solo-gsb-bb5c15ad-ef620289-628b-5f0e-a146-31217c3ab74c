import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.config import get_settings

BOX_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")


def _to_utc_naive(value: datetime) -> datetime:
    """统一为无时区的 UTC 时间后再入库。

    客户端可传带时区（如 +08:00 / Z）的 ISO 8601 时间；
    无时区的时间约定按 UTC 处理。
    """
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class EventIn(BaseModel):
    box_code: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="周转箱箱号（大小写字母、数字、-_），入库时统一大写并去除首尾空白",
        examples=["BOX-001"],
    )
    seq: int = Field(
        ..., ge=0, description="箱内递增序号（非负整数），同一箱号下唯一", examples=[1]
    )
    temperature: float = Field(
        ..., description="温度（摄氏度）", examples=[4.2]
    )
    event_time: datetime = Field(
        ...,
        description="事件时间（ISO 8601，推荐带时区），服务端统一转为 UTC 存储",
        examples=["2026-09-23T10:00:00+08:00"],
    )

    # 入参接受驼峰字段名：boxCode / eventTime
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        alias_generator=to_camel,
    )

    @field_validator("box_code")
    @classmethod
    def _normalize_box_code(cls, v: str) -> str:
        v = v.strip().upper()
        if not BOX_CODE_PATTERN.match(v):
            raise ValueError(
                "箱号仅允许字母、数字、中划线、下划线，且必须以字母或数字开头（1-64 字符）"
            )
        return v

    @field_validator("temperature")
    @classmethod
    def _check_temperature_range(cls, v: float) -> float:
        settings = get_settings()
        if not (settings.min_temperature <= v <= settings.max_temperature):
            raise ValueError(
                f"温度需在 {settings.min_temperature} ~ {settings.max_temperature} ℃ 之间"
            )
        return v

    @field_validator("event_time")
    @classmethod
    def _normalize_event_time(cls, v: datetime) -> datetime:
        return _to_utc_naive(v)


class EventOut(BaseModel):
    box_code: str
    seq: int
    temperature: float
    event_time: datetime
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("event_time", "received_at", mode="before")
    @classmethod
    def _ensure_utc_aware(cls, v: datetime) -> datetime:
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class EventAck(BaseModel):
    """POST 返回：事件内容 + 是否为重复上报 + 当前箱子最新状态。"""

    event: EventOut
    duplicate: bool
    state: EventOut


class BoxStateOut(BaseModel):
    box_code: str
    state: EventOut | None


class HealthOut(BaseModel):
    status: str = "ok"


class ErrorOut(BaseModel):
    detail: str
