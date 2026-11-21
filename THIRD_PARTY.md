# Third-party software and data

The MIT software license does not license Elia data or grant endorsement.

| Component | Terms / official reference | Use |
|---|---|---|
| Elia Transmission Belgium SA Open Data | [Elia Open Data Licence](https://opendata.elia.be/pages/licence/) | Public read-only remote records; transformed normalized outputs; retain attribution and provenance |
| Official MCP Python SDK | [MIT license](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) | Server/client protocol implementation |
| httpx | [BSD-3-Clause license](https://github.com/encode/httpx/blob/master/LICENSE.md) | Provider HTTP client |
| Pydantic | [MIT license](https://github.com/pydantic/pydantic/blob/main/LICENSE) | Typed validation/serialization |
| tzdata (Windows) | [Apache-2.0 package and public-domain IANA data details](https://github.com/python/tzdata/blob/master/LICENSE) | Timezone support |

No bulk provider datasets are redistributed. A four-record, attributed live solar response is included in docs/examples/solar-response.json as a dated validation example; it retains Elia provenance and remains subject to the data licence. Fixtures use synthetic numbers with verified field names. Documentation records source contracts in original prose. Outputs identify Elia, the source dataset and URL, retrieval time, units and transformations. No warranty of completeness or suitability is implied. Consult the authoritative current Elia licence before redistributing derived data; no claim that these terms are equivalent to another data licence is made.

Development tools include pytest (MIT), pytest-asyncio (Apache-2.0), Ruff (MIT), mypy (MIT), build (MIT) and Hatchling (MIT). Dependencies retain their own notices in installed distributions; consult package metadata for transitives.

This notice is included in wheel license metadata as well as the source distribution.
