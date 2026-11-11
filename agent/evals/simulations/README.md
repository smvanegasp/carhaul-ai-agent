# Simulation runs

AI-vs-AI simulations of Mia (stage 7): a model plays one of 8 caller personas through one of 9
paths (happy, questions, changes, a person, off-topic), against fake CarHauler and geocoding
APIs, and code scores every call against its ground truth. A nightly GitHub workflow
(`.github/workflows/simulations.yml`) adds a run here; `uv run python -m evals.sim.run` (in
`agent/`) runs one locally. How it works: [`agent/evals/sim/`](../sim/).

Every run keeps its full transcripts. Newest first:

| Run (UTC) | Label | Mia | Caller | Calls | Passed | Weakest scenario | Cost | |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | --- |
| 2026-11-11T01:44:44+00:00 | mia-120b | `openai/gpt-oss-120b` | `openai/gpt-oss-120b` | 72 | 64 (89%) | `off_topic_three_strikes` 0/2 | $0.40 | [report](runs/20261111T0144Z_mia-120b/report.md) |
| 2026-11-11T01:38:37+00:00 | mia-20b | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 71 (99%) | `api_down_at_quote` 2/2 | $0.20 | [report](runs/20261111T0138Z_mia-20b/report.md) |
| 2026-11-11T01:28:20+00:00 | faq-estimates-counts | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 66 (92%) | `api_down_at_quote` 2/2 | $0.20 | [report](runs/20261111T0128Z_faq-estimates-counts/report.md) |
| 2026-11-11T01:20:01+00:00 | faq-estimates | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 65 (90%) | `api_down_at_quote` 1/2 | $0.19 | [report](runs/20261111T0120Z_faq-estimates/report.md) |
| 2026-11-11T01:02:14+00:00 | partial-vehicle | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 65 (90%) | `api_down_at_quote` 2/2 | $0.20 | [report](runs/20261111T0102Z_partial-vehicle/report.md) |
| 2026-11-11T00:26:07+00:00 | final | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 68 (94%) | `change_vehicle_after_quote` 2/3 | $0.19 | [report](runs/20261111T0026Z_final/report.md) |
| 2026-11-11T00:13:51+00:00 | stage7 | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 60 (83%) | `off_topic_three_strikes` 2/3 | $0.19 | [report](runs/20261111T0013Z_stage7/report.md) |
| 2026-11-11T00:01:17+00:00 | fixes | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 60 (83%) | `remove_vehicle_after_quote` 0/3 | $0.19 | [report](runs/20261111T0001Z_fixes/report.md) |
| 2026-11-10T23:52:39+00:00 | baseline | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` | 72 | 42 (58%) | `api_down_at_quote` 3/3 | $0.15 | [report](runs/20261110T2352Z_baseline/report.md) |
