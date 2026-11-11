# Simulation run 2026-11-11T01:20:01+00:00 (faq-estimates)

**65/72 calls passed (90%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `a8192c2`, 6.2 min, about $0.19 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: caller_done 3, ended 47, off_topic_end 6, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 5 | 0.62 | 574 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 5.2 | 0.5 | 560 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 75% | 100% | 6.9 | 0.5 | 529 |
| `NHP_correction` self-corrects the car's year | 8 | 88% | 100% | 4.6 | 0.62 | 724 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 100% | 100% | 7.2 | 1.12 | 540 |
| `NHP_change_route` changes the destination after the quote | 8 | 88% | 100% | 7.1 | 1.38 | 544 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.5 | 0.62 | 394 |
| `AP_two` two off-topic questions, then a normal call | 8 | 88% | 100% | 7.2 | 0.12 | 620 |
| `AP_three` three off-topic questions in a row from the start | 8 | 75% | 25% | 4.8 | 1.0 | 642 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 78% | 78% | 6.3 | 1.33 | 551 |
| `NG_P_V` | 9 | 89% | 89% | 7.8 | 1.67 | 621 |
| `NG_C_NV` | 9 | 78% | 89% | 5.9 | 0.78 | 558 |
| `NG_C_V` | 9 | 100% | 78% | 5.7 | 1.0 | 538 |
| `G_P_NV` | 9 | 100% | 78% | 5.2 | 0.44 | 543 |
| `G_P_V` | 9 | 89% | 78% | 4.9 | 0.44 | 517 |
| `G_C_NV` | 9 | 100% | 78% | 4.6 | 0.11 | 535 |
| `G_C_V` | 9 | 89% | 78% | 4.7 | 0.0 | 612 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | **FAIL** | pass | pass | pass | **FAIL** | pass |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_C_NV` | pass | pass | pass | pass | pass | **FAIL** | pass | pass | **FAIL** |
| `NG_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `vehicles` | 4 |
| `no_quote` | 2 |
| `off_topic_end` | 2 |
| `faq_answered` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `api_down_at_quote` | 1/2 |
| `change_vehicle_after_quote` | 1/2 |
| `change_route_after_quote` | 2/2 |
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

- [NG_P_NV__NHP_correction](transcripts.md#ng_p_nv__nhp_correction): ended, failed `vehicles`
- [NG_P_NV__AP_two](transcripts.md#ng_p_nv__ap_two): ended, failed `vehicles`
- [NG_P_V__AP_three](transcripts.md#ng_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_NV__NHP_change_route](transcripts.md#ng_c_nv__nhp_change_route): ended, failed `vehicles`
- [NG_C_NV__AP_three](transcripts.md#ng_c_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_P_V__QHP](transcripts.md#g_p_v__qhp): caller_done, failed `vehicles`
- [G_C_V__QHP](transcripts.md#g_c_v__qhp): ended, failed `faq_answered`
