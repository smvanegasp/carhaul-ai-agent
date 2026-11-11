# Simulation run 2026-11-11T04:20:30+00:00 (call-feedback-nov11)

**70/72 calls passed (97%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `8bd2a6e`, 5.5 min, about $0.19 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: ended 50, off_topic_end 6, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 4.8 | 0.62 | 626 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 5 | 0.38 | 788 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 100% | 100% | 6.6 | 0.62 | 604 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 4.5 | 0.88 | 758 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 100% | 100% | 7 | 0.75 | 735 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 7.5 | 1.25 | 741 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.4 | 0.38 | 571 |
| `AP_two` two off-topic questions, then a normal call | 8 | 100% | 100% | 7.1 | 1.25 | 767 |
| `AP_three` three off-topic questions in a row from the start | 8 | 75% | 25% | 4.4 | 0.5 | 576 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 89% | 89% | 7.1 | 1.56 | 524 |
| `NG_P_V` | 9 | 89% | 89% | 8 | 1.67 | 682 |
| `NG_C_NV` | 9 | 100% | 78% | 5.7 | 1.33 | 634 |
| `NG_C_V` | 9 | 100% | 78% | 4.7 | 0.67 | 812 |
| `G_P_NV` | 9 | 100% | 78% | 5.4 | 0.56 | 768 |
| `G_P_V` | 9 | 100% | 78% | 4.7 | 0.11 | 894 |
| `G_C_NV` | 9 | 100% | 78% | 4.1 | 0.0 | 749 |
| `G_C_V` | 9 | 100% | 78% | 4.1 | 0.0 | 671 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `no_quote` | 2 |
| `off_topic_end` | 2 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `city_not_found` | 0/1 |
| `api_down_at_quote` | 1/1 |
| `change_route_after_quote` | 1/1 |
| `change_vehicle_after_quote` | 1/1 |
| `eliminate_vehicle` | 1/1 |
| `estimate_after_unsure` | 1/1 |
| `f150_spoken_hundred` | 1/1 |
| `faq_during_read_back` | 1/1 |
| `faq_mid_call` | 1/1 |
| `faq_personal_items` | 1/1 |
| `faq_stt_closed_shipping` | 1/1 |
| `happy_path_ngc_1v` | 1/1 |
| `happy_path_ngc_2v` | 1/1 |
| `happy_path_ngc_3v` | 1/1 |
| `make_only_and_yep` | 1/1 |
| `off_topic_three_strikes` | 1/1 |
| `partial_vehicle_with_route` | 1/1 |
| `remove_vehicle_after_quote` | 1/1 |
| `self_correction_year` | 1/1 |
| `spoken_model_number` | 1/1 |
| `state_as_city_and_model` | 1/1 |
| `undo_vehicle_change` | 1/1 |

## Failures

- [NG_P_NV__AP_three](transcripts.md#ng_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_P_V__AP_three](transcripts.md#ng_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
