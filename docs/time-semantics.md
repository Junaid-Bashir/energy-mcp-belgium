# Time semantics

Use ISO 8601 timestamps with `Z` or an explicit offset. Naive timestamps, numeric Unix timestamps and numeric epoch strings are rejected at the MCP boundary. Inputs are converted to UTC before bounds and alignment checks. Provider timestamps and outputs are UTC. `datetime` is an interval-start timestamp; ranges are `[start,end)`.

The portal displays Europe/Brussels local time, while API data uses UTC. Belgium observes DST: local calendar days can have 92, 96 or 100 quarter-hour intervals. Derive local midnight boundaries with an IANA timezone, then convert each boundary to UTC. Never add 24 UTC hours to represent every Belgian day.

Queries are limited to 24 elapsed hours. A 25-hour autumn day must be split (for example at 24 elapsed hours) and results combined by the host. Tests verify integration over synthetic complete 23/24/25-hour days. Analytics uses actual elapsed seconds; repeated local clock times remain distinct UTC instants.

UTC boundaries must align to quarter-hours, including for minute-level imbalance. Minute observations retain minute resolution. Bounds do not imply every provider interval exists. Solar's cutover is 2026-10-26 00:00 Europe/Brussels (2026-10-25 23:00Z).
