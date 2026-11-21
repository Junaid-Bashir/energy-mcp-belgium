# Elia source contracts

Provider: Elia Transmission Belgium SA, public Explore API v2.1, no API key. Each dataset link provides information and API access. The corresponding machine-readable field selection is in `elia/datasets.py`; synthetic fixtures use those field names. No bulk Elia datasets are redistributed; docs/examples/solar-response.json contains a small attributed four-record live example.

## Shared contract

- Time field: `datetime`, interval start, timezone-aware API timestamp converted to UTC; portal timezone Europe/Brussels.
- Geographic scope: Belgium / Belgian control area, with qualifications below.
- Missing: JSON null remains null; absent required fields cause contract errors. Zero stays numeric zero. Absent records remain absent.
- Historical refresh: daily according to DCAT metadata; exact publication times are not promised. Future forecast-bearing records may have null actuals. Current-day freshness is not guaranteed.
- All numeric fields remain numbers, not formatted strings. No forecast field is selected.
- Non-solar records carry `resolutioncode`, checked against expected resolution. Balancing records retain `qualitystatus`.
- API: `https://opendata.elia.be/api/explore/v2.1/catalog/datasets/{dataset_id}/records`; `where`, deterministic ordering, `limit=100`, offset pagination. Maximum 5000 raw rows. Requests use sequential pages, a small connection pool and bounded retries; these are client safeguards, not a published Elia quota.

## Contracts by tool

| Tool | Dataset / official identity | Values → normalized keys | Unit | Resolution | Geographic selection |
|---|---|---|---|---|---|
| get_solar_generation | [ods209](https://opendata.elia.be/explore/dataset/ods209/) PV estimation/forecast historical from 26/10/2026 | measured_upscaled → generation_mw | MW | 15min | region=Belgium AND gridconnectiontype=Total |
| get_wind_generation | [ods031](https://opendata.elia.be/explore/dataset/ods031/) wind estimation/forecast historical | measured → generation_mw | MW | 15min | sum verified disjoint components below |
| get_load | [ods001](https://opendata.elia.be/explore/dataset/ods001/) measured/forecast total load historical | totalload → total_load_mw | MW | 15min | Belgian total load, transmission and connected distribution |
| get_generation_mix | [ods201](https://opendata.elia.be/explore/dataset/ods201/) total generation by fuel | generatedpower → generation_mw | MW | 15min | Belgian control area; both fuel labels retained |
| get_system_imbalance | [ods126](https://opendata.elia.be/explore/dataset/ods126/) current system imbalance historical since 22/05/2024 | systemimbalance → system_imbalance_mw | MW | 1min | Elia control area |
| get_imbalance_prices | [ods134](https://opendata.elia.be/explore/dataset/ods134/) imbalance prices per quarter-hour historical since 22/05/2024 | imbalanceprice → settlement_price_eur_per_mwh; marginalincrementalprice → marginal_incremental_price_eur_per_mwh; marginaldecrementalprice → marginal_decremental_price_eur_per_mwh | EUR/MWh | 15min | Belgian BRP settlement |

### Solar caveats

Elia replaced ods032 with ods209 on 26 October 2026 and added grid connection dimensions. v0.1 rejects earlier queries rather than silently mixing schemas. National total includes DSO and TSO through the provider's Total selection; provinces and connection types must not be summed with that total. Measured/upscaled is an estimation from measurements, not a census of metered PV. Its field unit annotation is blank, but the official dataset description states MW. Update frequency is daily.

### Wind caveats and aggregation rule

Verified full dimension tuples (`offshoreonshore`, `region`, `gridconnectiontype`):

| Type | Region | Grid |
|---|---|---|
| Offshore | Federal | Elia |
| Onshore | Flanders | Dso |
| Onshore | Flanders | Elia |
| Onshore | Wallonia | Dso |
| Onshore | Wallonia | Elia |

There is no national total row in the verified source. Total requires all five, onshore all four onshore tuples, offshore the single federal tuple. One missing/null component makes the corresponding timestamp's total null. All components absent produces an absent interval. Unknown tuples or duplicate logical keys fail. This deliberately conservative mapping needs review if Elia adds regions or categories. The provider warns of offshore discrepancies, often 100–300 MW per quarter-hour, for parts of 2018–2023; these are not corrected here. Refresh: daily DCAT.

### Load caveats

Official `totalload` covers transmission and connected distribution electrical loads and estimated losses, using computations, measurements and extrapolations. Missing inputs can produce blanks. It is neither Elia-grid-only load nor a pure direct measurement. The ods001 `totalload` metadata currently has the erroneous unit annotation `0`; normalization uses MW corroborated by [Elia's corresponding near-real-time total-load publication](https://opendata.elia.be/explore/dataset/ods002/table/?flg=nl-nl) and [Elia's total-load methodology](https://www.elia.be/-/media/project/elia/shared/documents/press-releases/2019/280619/20190628_elia_adequacy_and_flexibility_study_nl.pdf). This is an explicit metadata exception, not unit inference from magnitudes. Refresh: daily DCAT. Elia advises using total load instead of [ods003 grid load](https://opendata.elia.be/explore/dataset/ods003/information/) because of a publication issue.

### Mix caveats

`generatedpower` is interval-average generated power. Preserve `fueltypepublication` and `fueltypeentsoe` in dimensions. A publication category can contain several ENTSO-E subtypes: the logical key is timestamp plus both labels. No invented technology or inferred category total. Water/storage classifications can be surprising; retain source distinctions and nulls. Refresh: daily DCAT.

### Imbalance caveats and sign

Minute `systemimbalance` is instantaneous, not quarter-hour average power. Positive means surplus; negative means shortage. The official schema associates negative imbalance with imported IGCC upward volume and positive imbalance with exported downward volume. See also [Elia's accompanying note, footnote 6](https://www.elia.be/-/media/project/elia/elia-site/public-consultations/2023/20230720accompanying-note-providing-elias-answers-to-cregs-comments-expressed-in-decision-b2554final.pdf) for imbalance-area sign semantics. Preserve signed MW without inversion; do not confuse SI with ACE. All ods126 values are described as non-validated and informational. Refresh: daily.

### Price caveats

`imbalanceprice` is the BRP settlement tariff; marginal incremental/decremental prices describe upward/downward activation economics and remain separate. They are not separate positive/negative BRP settlement tariffs. Negative prices remain negative. The source is 15-minute settlement data, not minute indicative prices. Month M records are validated after the 15th of M+1; initial publications are indicative and revisions possible. Retain qualitystatus; provisional records are not final settlement data. Refresh: daily. Simulated consultation datasets ods211/ods212 are deliberately excluded.

## Contract maintenance

Re-fetch metadata and one tiny records window from official endpoints; inspect dimensions and notices, unit annotations, interval meaning and field types. Update mappings, docs and synthetic tests together. Run the opt-in six-dataset suite and offline checks. Never resolve contract drift by filling zeros, dropping duplicate keys or substituting forecasts. Empty historical periods are valid no-data responses; v0.1 does not stitch legacy solar or legacy balancing datasets.
