# kg model selection (2026-11-18)

sample: 4 pairs (response-bearing first)

| model | endpoint | wall/pair | request ok | response ok | field fill | noul avg/max | failed |
|---|---|---|---|---|---|---|---|
| olc:default | olc | 6.7s | 3 | 0 | 0.0 | None/None | 1 |
| granite4.2:8b | ollama | 105.6s | 4 | 0 | 0.0 | None/None | 0 |
| qwen3.5:4b | ollama | 170.2s | 4 | 0 | 0.0 | None/None | 0 |
| mistral:latest | ollama | 75.2s | 4 | 0 | 1.0 | None/None | 0 |

**Recommendation:** `mistral:latest` (best field fill 1.0 at 75.2s/pair)
