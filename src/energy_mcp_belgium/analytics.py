from collections import Counter
from math import fsum

from .errors import EnergyError
from .models import DataResult, EnergyResult, QualityResult


def _single_series(data: DataResult) -> None:
    if not data.records:
        return
    fields = set(data.records[0].values)
    dimensions = data.records[0].dimensions
    if not fields or any(
        set(record.values) != fields or record.dimensions != dimensions for record in data.records
    ):
        raise EnergyError(
            "invalid_request",
            "Analytics requires one series with stable value fields and dimensions.",
        )


def quality(data: DataResult) -> QualityResult:
    """Diagnose a single normalized fixed-resolution series without repairing it."""
    _single_series(data)
    m = data.metadata
    step = m.resolution_minutes * 60
    counts = Counter(r.timestamp for r in data.records)
    aligned = {
        r.timestamp
        for r in data.records
        if m.start <= r.timestamp < m.end and (r.timestamp - m.start).total_seconds() % step == 0
    }
    valid = {
        r.timestamp
        for r in data.records
        if r.timestamp in aligned
        and counts[r.timestamp] == 1
        and all(v is not None for v in r.values.values())
    }
    expected = int((m.end - m.start).total_seconds() / step)
    duplicate = sum(n - 1 for n in counts.values())
    off_grid = sum(r.timestamp not in aligned for r in data.records)
    missing = expected - len(aligned)
    nulls = sum(any(v is None for v in r.values.values()) for r in data.records)
    return QualityResult(
        metadata=m,
        record_count=len(data.records),
        expected_intervals=expected,
        missing_intervals=missing,
        null_intervals=nulls,
        duplicate_timestamps=duplicate,
        off_grid_records=off_grid,
        coverage_pct=100 * len(valid) / expected,
        first_timestamp=min(counts) if counts else None,
        last_timestamp=max(counts) if counts else None,
        status="invalid"
        if duplicate or off_grid
        else "incomplete"
        if missing or nulls
        else "complete",
    )


def energy(data: DataResult) -> EnergyResult:
    if (
        data.metadata.unit != "MW"
        or data.metadata.resolution_minutes != 15
        or data.metadata.dataset_id in {"ods126", "ods201"}
        or any(len(record.values) != 1 for record in data.records)
    ):
        raise EnergyError(
            "invalid_request",
            "Energy integration requires one interval-average 15-minute MW series.",
        )
    report = quality(data)
    if report.status == "invalid":
        raise EnergyError(
            "dataset_contract_error", "Cannot integrate duplicate or off-grid records."
        )
    vals = [v for r in data.records for v in r.values.values() if v is not None]
    hours = data.metadata.resolution_minutes / 60
    return EnergyResult(
        metadata=data.metadata,
        energy_mwh=fsum(vals) * hours if vals else None,
        covered_hours=len(vals) * hours,
        quality=report,
    )
