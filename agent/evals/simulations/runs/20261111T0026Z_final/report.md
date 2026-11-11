# Simulation run 2026-11-11T00:26:07+00:00 (final)

**68/72 calls passed (94%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `b571b24`, 9.9 min, about $0.19 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: ended 48, off_topic_end 7, transferred 17

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 4.8 | 0.38 | 722 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 88% | 100% | 5.1 | 0.62 | 695 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 75% | 88% | 7 | 1.12 | 571 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 4.4 | 0.5 | 749 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 100% | 100% | 8 | 1.0 | 710 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 7.1 | 0.88 | 703 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.4 | 0.25 | 536 |
| `AP_two` two off-topic questions, then a normal call | 8 | 100% | 100% | 7.1 | 0.62 | 689 |
| `AP_three` three off-topic questions in a row from the start | 8 | 88% | 12% | 3.9 | 0.62 | 579 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 100% | 78% | 6.8 | 1.78 | 843 |
| `NG_P_V` | 9 | 100% | 78% | 6.1 | 0.89 | 762 |
| `NG_C_NV` | 9 | 89% | 89% | 6.2 | 1.56 | 566 |
| `NG_C_V` | 9 | 100% | 78% | 5.2 | 0.78 | 528 |
| `G_P_NV` | 9 | 89% | 78% | 5.4 | 0.11 | 649 |
| `G_P_V` | 9 | 89% | 78% | 5 | 0.11 | 695 |
| `G_C_NV` | 9 | 100% | 78% | 4.8 | 0.11 | 723 |
| `G_C_V` | 9 | 89% | 67% | 4.7 | 0.0 | 736 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |
| `G_P_V` | pass | **FAIL** | pass | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `faq_answered` | 2 |
| `no_quote` | 1 |
| `off_topic_end` | 1 |
| `vehicles` | 1 |
| `quoted` | 1 |
| `quote_matches` | 1 |
| `price_spoken` | 1 |
| `no_transfer` | 1 |
| `fragments_fired` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `change_vehicle_after_quote` | 2/3 |
| `api_down_at_quote` | 3/3 |
| `change_route_after_quote` | 3/3 |
| `city_not_found` | 3/3 |
| `faq_during_read_back` | 3/3 |
| `faq_mid_call` | 3/3 |
| `faq_stt_closed_shipping` | 3/3 |
| `happy_path_ngc_1v` | 3/3 |
| `happy_path_ngc_2v` | 3/3 |
| `happy_path_ngc_3v` | 3/3 |
| `off_topic_three_strikes` | 3/3 |
| `remove_vehicle_after_quote` | 3/3 |
| `self_correction_year` | 3/3 |
| `undo_vehicle_change` | 3/3 |

## Failures

- [NG_C_NV__AP_three](transcripts.md#ng_c_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_P_NV__QHP](transcripts.md#g_p_nv__qhp): ended, failed `faq_answered`
- [G_P_V__SHP_transfer](transcripts.md#g_p_v__shp_transfer): transferred, failed `vehicles`
- [G_C_V__QHP](transcripts.md#g_c_v__qhp): transferred, failed `quoted`, `quote_matches`, `price_spoken`, `no_transfer`, `fragments_fired`, `faq_answered`
