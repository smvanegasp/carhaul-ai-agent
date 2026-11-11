# Simulation run 2026-11-11T05:09:44+00:00 (direct-mia-live-tests)

**71/72 calls passed (99%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `100b9f1`, 2.7 min, about $0.17 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: ended 48, off_topic_end 8, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 4.1 | 0.0 | 611 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 4.4 | 0.12 | 636 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 88% | 100% | 6 | 0.38 | 536 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 3.5 | 0.0 | 522 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 100% | 100% | 6.2 | 0.12 | 648 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 6.2 | 0.12 | 650 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2 | 0.0 | 618 |
| `AP_two` two off-topic questions, then a normal call | 8 | 100% | 100% | 6.6 | 0.12 | 653 |
| `AP_three` three off-topic questions in a row from the start | 8 | 100% | 0% | 3 | 0.0 | 532 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 100% | 78% | 5.7 | 0.33 | 538 |
| `NG_P_V` | 9 | 89% | 78% | 5.3 | 0.11 | 612 |
| `NG_C_NV` | 9 | 100% | 78% | 4.3 | 0.0 | 569 |
| `NG_C_V` | 9 | 100% | 78% | 4.1 | 0.0 | 580 |
| `G_P_NV` | 9 | 100% | 78% | 5.2 | 0.22 | 660 |
| `G_P_V` | 9 | 100% | 78% | 4.8 | 0.0 | 687 |
| `G_C_NV` | 9 | 100% | 78% | 4 | 0.11 | 670 |
| `G_C_V` | 9 | 100% | 78% | 4 | 0.0 | 627 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_P_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `vehicles` | 1 |

## Failures

- [NG_P_V__QHP](transcripts.md#ng_p_v__qhp): ended, failed `vehicles`
