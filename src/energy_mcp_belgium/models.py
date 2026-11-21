from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .errors import EnergyError

Series = Literal["solar", "wind", "load", "generation_mix", "system_imbalance", "imbalance_prices"]
WindType = Literal["total", "onshore", "offshore"]


def explicit_datetime(value: object) -> object:
    if isinstance(value, datetime) or isinstance(value, str) and "t" in value.lower():
        return value
    raise ValueError(
        "Use an ISO 8601 datetime with Z or an explicit UTC offset, not a Unix timestamp."
    )


Timestamp = Annotated[AwareDatetime, BeforeValidator(explicit_datetime)]
StartTime = Annotated[
    Timestamp,
    Field(
        description="Inclusive interval start, ISO 8601 with Z or an explicit offset (for example 2026-11-17T10:00:00Z). Must align to a UTC quarter-hour; start < end; maximum 24 elapsed hours."
    ),
]
EndTime = Annotated[
    Timestamp,
    Field(
        description="Exclusive interval end, ISO 8601 with Z or an explicit offset. UTC quarter-hour aligned, after start and no more than 24 elapsed hours later. Split longer ranges, including 25-hour Belgian DST days."
    ),
]
WindSelection = Annotated[
    WindType,
    Field(
        description="total (default): Belgian onshore plus offshore; onshore: four regional/grid components; offshore: federal offshore component. Applies only to wind; leave total for other series. Incomplete component sets yield null, not partial totals."
    ),
]


def time_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise EnergyError("invalid_request", "Use ISO 8601 timestamps with Z or a UTC offset.")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if not timedelta(0) < end - start <= timedelta(hours=24):
        raise EnergyError(
            "invalid_request", "Require start < end and at most 24 hours; split larger ranges."
        )
    if any(t.second or t.microsecond or t.minute % 15 for t in (start, end)):
        raise EnergyError("invalid_request", "Use quarter-hour-aligned UTC boundaries.")
    return start, end


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Record(Model):
    timestamp: AwareDatetime
    values: dict[str, float | None] = Field(
        description="Normalized measurements as numbers; null means unavailable, never zero. Units and interval duration are in metadata."
    )
    dimensions: dict[str, str] = Field(default_factory=dict)
    quality_status: str | None = None

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class Metadata(Model):
    source: Literal["elia"] = "elia"
    dataset_id: str
    source_url: str
    retrieved_at: AwareDatetime
    start: AwareDatetime
    end: AwareDatetime
    timezone: Literal["UTC"] = "UTC"
    unit: str = Field(
        description="Unit of the source measurements. For analytics this remains the input unit; energy_mwh is explicitly MWh."
    )
    resolution_minutes: int = Field(gt=0, strict=True)
    record_count: int = Field(ge=0, strict=True)
    missing_value_count: int = Field(ge=0, strict=True)
    status: Literal["ok", "no_data"]
    caveats: list[str]

    @field_validator("start", "end", "retrieved_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def interval_grid(self) -> "Metadata":
        seconds = (self.end - self.start).total_seconds()
        if seconds <= 0 or seconds % (self.resolution_minutes * 60):
            raise ValueError("Metadata range must cover a positive whole number of intervals.")
        return self


class DataResult(Model):
    metadata: Metadata
    records: list[Record]


class QualityResult(Model):
    metadata: Metadata
    record_count: int
    expected_intervals: int
    missing_intervals: int
    null_intervals: int
    duplicate_timestamps: int
    off_grid_records: int
    coverage_pct: float
    first_timestamp: AwareDatetime | None
    last_timestamp: AwareDatetime | None
    status: Literal["complete", "incomplete", "invalid"]


class EnergyResult(Model):
    metadata: Metadata
    energy_mwh: float | None = Field(
        description="Observed energy in MWh over available intervals; null if no usable power values. No gap filling or full-period estimate."
    )
    covered_hours: float = Field(
        description="Elapsed hours with usable quarter-hour power measurements."
    )
    quality: QualityResult
    method: str = "Sum non-null interval-average MW times fixed interval hours; no gap filling."
