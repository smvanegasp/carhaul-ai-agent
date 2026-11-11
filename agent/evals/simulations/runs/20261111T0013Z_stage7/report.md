# Simulation run 2026-11-11T00:13:51+00:00 (stage7)

**60/72 calls passed (83%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `b571b24`, 9.7 min, about $0.19 in Groq tokens. API errors: 3.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: caller_done 1, ended 45, error 3, off_topic_end 7, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 5.1 | 0.5 | 680 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 62% | 88% | 4.6 | 0.38 | 648 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 62% | 88% | 7 | 0.88 | 742 |
| `NHP_correction` self-corrects the car's year | 8 | 75% | 88% | 4.1 | 0.62 | 668 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 88% | 100% | 7.1 | 0.38 | 815 |
| `NHP_change_route` changes the destination after the quote | 8 | 88% | 88% | 6.9 | 0.88 | 824 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.5 | 0.62 | 536 |
| `AP_two` two off-topic questions, then a normal call | 8 | 88% | 100% | 7.6 | 1.25 | 824 |
| `AP_three` three off-topic questions in a row from the start | 8 | 88% | 12% | 3.6 | 0.5 | 662 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 78% | 78% | 6 | 0.89 | 462 |
| `NG_P_V` | 9 | 78% | 67% | 6.3 | 1.22 | 812 |
| `NG_C_NV` | 9 | 67% | 78% | 6.4 | 1.67 | 810 |
| `NG_C_V` | 9 | 78% | 78% | 5.4 | 0.89 | 800 |
| `G_P_NV` | 9 | 100% | 78% | 5.8 | 0.56 | 684 |
| `G_P_V` | 9 | 89% | 67% | 4.8 | 0.11 | 627 |
| `G_C_NV` | 9 | 100% | 78% | 4.3 | 0.0 | 954 |
| `G_C_V` | 9 | 78% | 67% | 4.1 | 0.0 | 1014 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | **FAIL** | pass | pass | pass | **FAIL** | pass |
| `NG_P_V` | pass | **FAIL** | **FAIL** | pass | pass | pass | pass | pass | pass |
| `NG_C_NV` | pass | **FAIL** | pass | pass | pass | **FAIL** | pass | pass | **FAIL** |
| `NG_C_V` | pass | pass | **FAIL** | pass | **FAIL** | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_P_V` | pass | **FAIL** | pass | pass | pass | pass | pass | pass | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | **FAIL** | **FAIL** | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `vehicles` | 6 |
| `quoted` | 4 |
| `quote_matches` | 4 |
| `price_spoken` | 4 |
| `no_error` | 3 |
| `finished` | 3 |
| `faq_answered` | 2 |
| `fragments_fired` | 1 |
| `no_transfer` | 1 |
| `no_quote` | 1 |
| `off_topic_end` | 1 |
| `transferred` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `off_topic_three_strikes` | 2/3 |
| `api_down_at_quote` | 3/3 |
| `change_route_after_quote` | 3/3 |
| `change_vehicle_after_quote` | 3/3 |
| `city_not_found` | 3/3 |
| `faq_during_read_back` | 3/3 |
| `faq_mid_call` | 3/3 |
| `faq_stt_closed_shipping` | 3/3 |
| `happy_path_ngc_1v` | 3/3 |
| `happy_path_ngc_2v` | 3/3 |
| `happy_path_ngc_3v` | 3/3 |
| `remove_vehicle_after_quote` | 3/3 |
| `self_correction_year` | 3/3 |
| `undo_vehicle_change` | 3/3 |

## Failures

- [NG_P_NV__NHP_correction](transcripts.md#ng_p_nv__nhp_correction): ended, failed `vehicles`
- [NG_P_NV__AP_two](transcripts.md#ng_p_nv__ap_two): ended, failed `vehicles`
- [NG_P_V__SHP_transfer](transcripts.md#ng_p_v__shp_transfer): transferred, failed `vehicles`
- [NG_P_V__QHP](transcripts.md#ng_p_v__qhp): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: Connection error. (caused by APIError: Failed to parse tool call arguments as JSON))
- [NG_C_NV__SHP_transfer](transcripts.md#ng_c_nv__shp_transfer): transferred, failed `vehicles`
- [NG_C_NV__NHP_change_route](transcripts.md#ng_c_nv__nhp_change_route): transferred, failed `quoted`, `quote_matches`, `price_spoken`, `no_transfer`
- [NG_C_NV__AP_three](transcripts.md#ng_c_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_V__QHP](transcripts.md#ng_c_v__qhp): ended, failed `faq_answered`
- [NG_C_V__NHP_change_vehicle](transcripts.md#ng_c_v__nhp_change_vehicle): ended, failed `vehicles`
- [G_P_V__SHP_transfer](transcripts.md#g_p_v__shp_transfer): error, failed `no_error`, `finished`, `quoted`, `quote_matches`, `price_spoken`, `transferred` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIError: Failed to parse tool call arguments as JSON))
- [G_C_V__QHP](transcripts.md#g_c_v__qhp): ended, failed `faq_answered`
- [G_C_V__NHP_correction](transcripts.md#g_c_v__nhp_correction): error, failed `no_error`, `finished`, `quoted`, `quote_matches`, `price_spoken` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIError: Failed to parse tool call arguments as JSON))
