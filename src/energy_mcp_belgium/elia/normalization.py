from collections import defaultdict
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from ..errors import EnergyError
from ..models import DataResult, Metadata, Record, Series, WindType, time_range
from .client import EliaClient
from .datasets import CONTRACTS, WIND_KEYS


def normalize(rows: list[dict[str, Any]], series: Series, wind_type: WindType) -> list[Record]:
    contract = CONTRACTS[series]
    result: list[Record] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        try:
            timestamp = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("naive timestamp")
            timestamp = timestamp.astimezone(UTC)
            if series != "solar" and row["resolutioncode"] != f"PT{contract.minutes}M":
                raise ValueError("unexpected resolution")
            dimensions = {key: row[key] for key in contract.dimensions}
            if any(not isinstance(v, str) for v in dimensions.values()):
                raise ValueError("invalid dimension")
            values = {}
            for raw, public in contract.fields:
                value = row[raw]
                if value is not None and (type(value) not in (int, float) or not isfinite(value)):
                    raise ValueError("invalid numeric value")
                values[public] = value
            quality = (
                row["qualitystatus"] if series in {"system_imbalance", "imbalance_prices"} else None
            )
            if quality is not None and not isinstance(quality, str):
                raise ValueError("invalid quality status")
            key = (timestamp, *dimensions.values())
            if key in seen:
                raise ValueError("duplicate logical key")
            seen.add(key)
            result.append(
                Record(
                    timestamp=timestamp,
                    values=values,
                    dimensions=dimensions,
                    quality_status=quality,
                )
            )
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise EnergyError("dataset_contract_error", f"{contract.dataset_id}: {exc}") from exc
    if series == "wind":
        expected = {k for k in WIND_KEYS if wind_type == "total" or k[0].lower() == wind_type}
        groups: dict[datetime, list[Record]] = defaultdict(list)
        for record in result:
            key = tuple(record.dimensions[d] for d in contract.dimensions)
            if key not in expected:
                raise EnergyError("dataset_contract_error", "Unexpected wind component.")
            groups[record.timestamp].append(record)
        result = []
        for timestamp, components in groups.items():
            vals = [r.values["generation_mw"] for r in components]
            complete = len(components) == len(expected) and all(v is not None for v in vals)
            value = sum(v for v in vals if v is not None) if complete else None
            result.append(
                Record(
                    timestamp=timestamp,
                    values={"generation_mw": value},
                    dimensions={"wind_type": wind_type},
                )
            )
    return sorted(result, key=lambda r: (r.timestamp, tuple(r.dimensions.values())))


async def fetch(
    client: EliaClient,
    series: Series,
    start: datetime,
    end: datetime,
    wind_type: WindType = "total",
) -> DataResult:
    start, end = time_range(start, end)
    if wind_type not in {"total", "onshore", "offshore"}:
        raise EnergyError("invalid_request", "wind_type must be total, onshore or offshore.")
    if series not in CONTRACTS:
        raise EnergyError("invalid_request", "Unsupported series.")
    if series != "wind" and wind_type != "total":
        raise EnergyError("invalid_request", "wind_type only applies to the wind series.")
    c = CONTRACTS[series]
    if series == "solar" and start < datetime(2026, 10, 25, 23, tzinfo=UTC):
        raise EnergyError(
            "invalid_request",
            "Solar v0.1 supports ods209 from 2026-10-26 Belgian local time; legacy ods032 is not stitched.",
        )
    where = f"datetime >= date'{start.isoformat()}' AND datetime < date'{end.isoformat()}'"
    if series == "solar":
        where += ' AND region = "Belgium" AND gridconnectiontype = "Total"'
    if series == "wind" and wind_type != "total":
        where += f' AND offshoreonshore = "{wind_type.capitalize()}"'
    records = normalize(await client.records(c.dataset_id, where), series, wind_type)
    for record in records:
        if not start <= record.timestamp < end:
            raise EnergyError(
                "dataset_contract_error", "Provider returned timestamp outside requested range."
            )
        if (
            record.timestamp.second
            or record.timestamp.microsecond
            or record.timestamp.minute % c.minutes
        ):
            raise EnergyError("dataset_contract_error", "Provider returned off-grid timestamp.")
        if series == "solar" and record.dimensions != {
            "region": "Belgium",
            "gridconnectiontype": "Total",
        }:
            raise EnergyError(
                "dataset_contract_error", "Provider returned unexpected solar dimensions."
            )
    return DataResult(
        metadata=Metadata(
            dataset_id=c.dataset_id,
            source_url=f"https://opendata.elia.be/explore/dataset/{c.dataset_id}/",
            retrieved_at=datetime.now(UTC),
            start=start,
            end=end,
            unit=c.unit,
            resolution_minutes=c.minutes,
            record_count=len(records),
            missing_value_count=sum(v is None for r in records for v in r.values.values()),
            status="ok" if records else "no_data",
            caveats=[c.caveat],
        ),
        records=records,
    )
