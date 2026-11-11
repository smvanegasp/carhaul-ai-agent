# Simulation run 2026-11-11T00:01:17+00:00 (fixes)

**60/72 calls passed (83%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `b571b24`, 9.0 min, about $0.19 in Groq tokens. API errors: 1.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: ended 49, error 1, off_topic_end 7, transferred 15

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 5.2 | 0.62 | 658 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 5.4 | 0.5 | 776 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 50% | 100% | 7.8 | 1.12 | 666 |
| `NHP_correction` self-corrects the car's year | 8 | 62% | 100% | 4.5 | 0.75 | 768 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 88% | 88% | 6 | 0.38 | 806 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 6.8 | 1.12 | 882 |
| `NHP_person` asks for a person at the vehicle question | 8 | 88% | 12% | 2.6 | 0.5 | 656 |
| `AP_two` two off-topic questions, then a normal call | 8 | 75% | 100% | 7.2 | 1.12 | 846 |
| `AP_three` three off-topic questions in a row from the start | 8 | 88% | 12% | 3.8 | 0.5 | 777 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 67% | 78% | 6.4 | 1.11 | 609 |
| `NG_P_V` | 9 | 67% | 78% | 6.7 | 1.33 | 734 |
| `NG_C_NV` | 9 | 100% | 78% | 5.8 | 1.33 | 604 |
| `NG_C_V` | 9 | 78% | 89% | 5.3 | 0.67 | 868 |
| `G_P_NV` | 9 | 89% | 78% | 5.3 | 0.56 | 852 |
| `G_P_V` | 9 | 78% | 78% | 4.9 | 0.33 | 832 |
| `G_C_NV` | 9 | 100% | 78% | 4.7 | 0.44 | 1030 |
| `G_C_V` | 9 | 89% | 78% | 4.7 | 0.11 | 995 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | **FAIL** | **FAIL** | pass | pass | pass | **FAIL** | pass |
| `NG_P_V` | pass | pass | **FAIL** | pass | **FAIL** | pass | pass | pass | **FAIL** |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | pass | pass | pass | **FAIL** | pass | pass | **FAIL** | pass | pass |
| `G_P_NV` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |
| `G_P_V` | pass | pass | pass | **FAIL** | pass | pass | pass | **FAIL** | pass |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `fragments_fired` | 5 |
| `vehicles` | 4 |
| `faq_answered` | 3 |
| `no_quote` | 2 |
| `no_error` | 1 |
| `finished` | 1 |
| `quoted` | 1 |
| `quote_matches` | 1 |
| `price_spoken` | 1 |
| `off_topic_end` | 1 |
| `transferred` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `remove_vehicle_after_quote` | 0/3 |
| `off_topic_three_strikes` | 1/3 |
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
| `self_correction_year` | 3/3 |
| `undo_vehicle_change` | 3/3 |

## Failures

- [NG_P_NV__QHP](transcripts.md#ng_p_nv__qhp): ended, failed `faq_answered`
- [NG_P_NV__NHP_correction](transcripts.md#ng_p_nv__nhp_correction): ended, failed `vehicles`
- [NG_P_NV__AP_two](transcripts.md#ng_p_nv__ap_two): ended, failed `vehicles`
- [NG_P_V__QHP](transcripts.md#ng_p_v__qhp): ended, failed `vehicles`
- [NG_P_V__NHP_change_vehicle](transcripts.md#ng_p_v__nhp_change_vehicle): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: Connection error. (caused by APIError: Tool call validation failed: tool call validation failed: attempted to call tool 'note_off_topic<|channel|>commentary' which was not in request.tools))
- [NG_P_V__AP_three](transcripts.md#ng_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_V__NHP_correction](transcripts.md#ng_c_v__nhp_correction): ended, failed `fragments_fired`
- [NG_C_V__NHP_person](transcripts.md#ng_c_v__nhp_person): ended, failed `no_quote`, `transferred`, `fragments_fired`
- [G_P_NV__QHP](transcripts.md#g_p_nv__qhp): ended, failed `faq_answered`
- [G_P_V__NHP_correction](transcripts.md#g_p_v__nhp_correction): ended, failed `fragments_fired`
- [G_P_V__AP_two](transcripts.md#g_p_v__ap_two): ended, failed `fragments_fired`
- [G_C_V__QHP](transcripts.md#g_c_v__qhp): ended, failed `faq_answered`
