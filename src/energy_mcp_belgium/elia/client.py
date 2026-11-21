import asyncio
import logging
from time import monotonic
from typing import Any

import httpx

from ..errors import EnergyError

BASE_URL = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets/"
log = logging.getLogger(__name__)


class EliaClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def records(self, dataset: str, where: str) -> list[dict[str, Any]]:
        from .datasets import CONTRACTS

        if dataset not in {c.dataset_id for c in CONTRACTS.values()}:
            raise EnergyError("invalid_request", "Unsupported dataset.")
        contract = next(c for c in CONTRACTS.values() if c.dataset_id == dataset)
        order = ", ".join(f"{field} ASC" for field in ("datetime", *contract.dimensions))
        fields = ["datetime", *contract.dimensions, *(raw for raw, _ in contract.fields)]
        if dataset != "ods209":
            fields.append("resolutioncode")
        if dataset in {"ods126", "ods134"}:
            fields.append("qualitystatus")
        rows: list[dict[str, Any]] = []
        total: int | None = None
        begun = monotonic()
        for offset in range(0, 5000, 100):
            params = {
                "where": where,
                "order_by": order,
                "select": ",".join(fields),
                "limit": "100",
                "offset": str(offset),
            }
            response = await self._request(dataset, params)
            try:
                body = response.json()
                count, page = body["total_count"], body["results"]
                if type(count) is not int or count < 0 or not isinstance(page, list):
                    raise ValueError
                if any(not isinstance(row, dict) for row in page):
                    raise ValueError
            except (ValueError, KeyError, TypeError) as exc:
                raise EnergyError(
                    "provider_response_error", "Invalid Elia records envelope."
                ) from exc
            if count > 5000:
                raise EnergyError(
                    "invalid_request", "Result exceeds 5000 provider rows; reduce time range."
                )
            if total is not None and count != total:
                raise EnergyError(
                    "provider_response_error", "Dataset changed during pagination; retry request."
                )
            total = count
            if len(page) > 100 or len(rows) + len(page) > count:
                raise EnergyError("provider_response_error", "Inconsistent Elia pagination.")
            rows.extend(page)
            if len(rows) == count:
                log.info(
                    "provider_result dataset=%s records=%d elapsed_s=%.3f",
                    dataset,
                    count,
                    monotonic() - begun,
                )
                return rows
            if len(page) != 100:
                raise EnergyError(
                    "provider_response_error", "Incomplete Elia page; no partial result returned."
                )
        raise EnergyError("provider_response_error", "Pagination limit reached.")

    async def _request(self, dataset: str, params: dict[str, str]) -> httpx.Response:
        for attempt in range(3):
            try:
                response = await self.http.get(BASE_URL + dataset + "/records", params=params)
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise EnergyError(
                        "provider_unavailable", "Elia request failed after 3 attempts."
                    ) from exc
            else:
                if response.status_code == 200:
                    return response
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise EnergyError(
                        "provider_response_error", f"Elia returned HTTP {response.status_code}."
                    )
                if attempt == 2:
                    raise EnergyError(
                        "provider_unavailable",
                        f"Elia returned HTTP {response.status_code} after 3 attempts.",
                    )
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        raise EnergyError(
                            "provider_unavailable", "Elia requests a later retry."
                        ) from None
                    if not 0 <= delay <= 5:
                        raise EnergyError("provider_unavailable", "Elia rate limited; retry later.")
                    await asyncio.sleep(delay)
                    continue
            await asyncio.sleep(0.25 * 2**attempt)
        raise AssertionError("unreachable")
