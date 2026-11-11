# Simulation run 2026-11-11T01:38:37+00:00 (mia-20b)

**71/72 calls passed (99%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `a8192c2`, 6.0 min, about $0.20 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: caller_done 1, ended 48, off_topic_end 7, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 5 | 0.62 | 536 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 5.4 | 0.88 | 678 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 100% | 100% | 7.9 | 1.0 | 544 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 4.6 | 0.62 | 657 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 100% | 100% | 6.8 | 0.25 | 604 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 6.9 | 0.88 | 594 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.6 | 0.62 | 441 |
| `AP_two` two off-topic questions, then a normal call | 8 | 100% | 100% | 7.9 | 0.88 | 626 |
| `AP_three` three off-topic questions in a row from the start | 8 | 88% | 12% | 3.8 | 0.62 | 540 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 100% | 78% | 6.3 | 1.0 | 938 |
| `NG_P_V` | 9 | 100% | 78% | 6.7 | 1.33 | 584 |
| `NG_C_NV` | 9 | 100% | 78% | 5.7 | 1.56 | 545 |
| `NG_C_V` | 9 | 100% | 78% | 5.4 | 0.89 | 589 |
| `G_P_NV` | 9 | 89% | 89% | 6.2 | 0.33 | 566 |
| `G_P_V` | 9 | 100% | 78% | 5.3 | 0.22 | 586 |
| `G_C_NV` | 9 | 100% | 78% | 4.8 | 0.22 | 525 |
| `G_C_V` | 9 | 100% | 78% | 4.7 | 0.11 | 603 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `G_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `no_quote` | 1 |
| `off_topic_end` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `api_down_at_quote` | 2/2 |
| `change_route_after_quote` | 2/2 |
| `change_vehicle_after_quote` | 2/2 |
| `city_not_found` | 2/2 |
| `estimate_after_unsure` | 2/2 |
| `faq_during_read_back` | 2/2 |
| `faq_mid_call` | 2/2 |
| `faq_personal_items` | 2/2 |
| `faq_stt_closed_shipping` | 2/2 |
| `happy_path_ngc_1v` | 2/2 |
| `happy_path_ngc_2v` | 2/2 |
| `happy_path_ngc_3v` | 2/2 |
| `off_topic_three_strikes` | 2/2 |
| `partial_vehicle_with_route` | 2/2 |
| `remove_vehicle_after_quote` | 2/2 |
| `self_correction_year` | 2/2 |
| `undo_vehicle_change` | 2/2 |

## Failures

- [G_P_NV__AP_three](transcripts.md#g_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
