# Simulation run 2026-11-11T01:44:44+00:00 (mia-120b)

**64/72 calls passed (89%)**. Mia: `openai/gpt-oss-120b`, caller: `openai/gpt-oss-120b`, commit `a8192c2`, 6.2 min, about $0.40 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: ended 52, off_topic_end 2, too_long 1, transferred 17

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 5.6 | 1.0 | 603 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 4.8 | 0.5 | 650 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 100% | 100% | 8.1 | 0.88 | 496 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 5.1 | 0.62 | 549 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 88% | 88% | 7.2 | 0.75 | 526 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 6.2 | 1.75 | 709 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.6 | 0.0 | 574 |
| `AP_two` two off-topic questions, then a normal call | 8 | 88% | 88% | 7.5 | 1.12 | 596 |
| `AP_three` three off-topic questions in a row from the start | 8 | 25% | 62% | 8.6 | 1.62 | 514 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 89% | 89% | 7.7 | 2.11 | 644 |
| `NG_P_V` | 9 | 89% | 89% | 7.8 | 1.33 | 626 |
| `NG_C_NV` | 9 | 89% | 89% | 6.3 | 1.44 | 534 |
| `NG_C_V` | 9 | 89% | 78% | 7.6 | 1.33 | 584 |
| `G_P_NV` | 9 | 78% | 78% | 6 | 0.33 | 516 |
| `G_P_V` | 9 | 100% | 78% | 5.8 | 0.33 | 582 |
| `G_C_NV` | 9 | 78% | 78% | 4.4 | 0.11 | 471 |
| `G_C_V` | 9 | 100% | 78% | 4.1 | 0.33 | 496 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `G_P_NV` | pass | pass | pass | pass | **FAIL** | pass | pass | pass | **FAIL** |
| `G_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | **FAIL** | **FAIL** |
| `G_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `off_topic_end` | 6 |
| `no_quote` | 5 |
| `quoted` | 2 |
| `quote_matches` | 2 |
| `price_spoken` | 2 |
| `finished` | 1 |
| `no_transfer` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `off_topic_three_strikes` | 0/2 |
| `faq_mid_call` | 1/2 |
| `api_down_at_quote` | 2/2 |
| `change_route_after_quote` | 2/2 |
| `change_vehicle_after_quote` | 2/2 |
| `city_not_found` | 2/2 |
| `estimate_after_unsure` | 2/2 |
| `faq_during_read_back` | 2/2 |
| `faq_personal_items` | 2/2 |
| `faq_stt_closed_shipping` | 2/2 |
| `happy_path_ngc_1v` | 2/2 |
| `happy_path_ngc_2v` | 2/2 |
| `happy_path_ngc_3v` | 2/2 |
| `partial_vehicle_with_route` | 2/2 |
| `remove_vehicle_after_quote` | 2/2 |
| `self_correction_year` | 2/2 |
| `undo_vehicle_change` | 2/2 |

## Failures

- [NG_P_NV__AP_three](transcripts.md#ng_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_P_V__AP_three](transcripts.md#ng_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_NV__AP_three](transcripts.md#ng_c_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_V__AP_three](transcripts.md#ng_c_v__ap_three): too_long, failed `finished`, `off_topic_end`
- [G_P_NV__NHP_change_vehicle](transcripts.md#g_p_nv__nhp_change_vehicle): ended, failed `quoted`, `quote_matches`, `price_spoken`
- [G_P_NV__AP_three](transcripts.md#g_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_C_NV__AP_two](transcripts.md#g_c_nv__ap_two): transferred, failed `quoted`, `quote_matches`, `price_spoken`, `no_transfer`
- [G_C_NV__AP_three](transcripts.md#g_c_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
