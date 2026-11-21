from dataclasses import dataclass


@dataclass(frozen=True)
class Contract:
    dataset_id: str
    fields: tuple[tuple[str, str], ...]
    minutes: int = 15
    unit: str = "MW"
    dimensions: tuple[str, ...] = ()
    caveat: str = "Historical publication; latest intervals may be absent or revised."


CONTRACTS = {
    "solar": Contract(
        "ods209",
        (("measured_upscaled", "generation_mw"),),
        dimensions=("region", "gridconnectiontype"),
        caveat="Measured and upscaled PV; available from 2026-10-26 only; never forecasts.",
    ),
    "wind": Contract(
        "ods031",
        (("measured", "generation_mw"),),
        dimensions=("offshoreonshore", "region", "gridconnectiontype"),
        caveat="Measured and upscaled wind; offshore discrepancies reported for 2018-2023.",
    ),
    "load": Contract(
        "ods001",
        (("totalload", "total_load_mw"),),
        caveat="Total load including estimated losses: computation, measurement and extrapolation.",
    ),
    "generation_mix": Contract(
        "ods201",
        (("generatedpower", "generation_mw"),),
        dimensions=("fueltypepublication", "fueltypeentsoe"),
        caveat="Belgian control area; preserve both fuel classifications; do not sum overlapping labels.",
    ),
    "system_imbalance": Contract(
        "ods126",
        (("systemimbalance", "system_imbalance_mw"),),
        minutes=1,
        caveat="Instantaneous informational, non-validated values; positive surplus, negative shortage.",
    ),
    "imbalance_prices": Contract(
        "ods134",
        (
            ("imbalanceprice", "settlement_price_eur_per_mwh"),
            ("marginalincrementalprice", "marginal_incremental_price_eur_per_mwh"),
            ("marginaldecrementalprice", "marginal_decremental_price_eur_per_mwh"),
        ),
        unit="EUR/MWh",
        caveat="Quarter-hour BRP settlement tariff; month M validated after 15th of M+1; inspect quality status.",
    ),
}

WIND_KEYS = {
    ("Offshore", "Federal", "Elia"),
    ("Onshore", "Flanders", "Dso"),
    ("Onshore", "Flanders", "Elia"),
    ("Onshore", "Wallonia", "Dso"),
    ("Onshore", "Wallonia", "Elia"),
}
