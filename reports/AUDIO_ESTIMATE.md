# Audio Estimate Report

Generated after core reconciliation.

## Summary

| Metric | Value |
|---|---|
| Audio candidates | 789 |
| Resolved | 789 |
| Unresolved / broken | 0 / 0 |
| Known bytes | 10,325,670,104 (~9.62 GiB) |
| Unknown-size count | 1 |
| First batch files | 789 |
| First batch bytes | ~9.62 GiB |
| Batches | 1 (under 20 GiB cap) |
| Free disk (at estimate) | ~158.4 GiB |
| Reserve | ~142.9–153.4 GiB (max of 50 GiB / 15%) |
| Overhead | ~2.96 GiB |
| Projected free after download | ~145.7 GiB |
| Safe to acquire | **Yes** (narrow margin vs reserve) |
| Estimated local backup requirement | ~9.6 GiB additional (same-drive backup not durable) |

## Notes

- Video remains deferred (0 items).
- Prefer an **external** backup target after audio completes.
- Continue audio with: `.\bhava.ps1 acquire --profile audio`
