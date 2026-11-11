# Simulation run 2026-11-11T01:02:14+00:00 (partial-vehicle)

**65/72 calls passed (90%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `73ec381`, 7.5 min, about $0.20 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: ended 51, off_topic_end 5, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 88% | 100% | 5.1 | 0.5 | 961 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 5.2 | 0.62 | 1068 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 62% | 100% | 7 | 0.88 | 896 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 4.9 | 0.38 | 1080 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 100% | 100% | 6.9 | 1.0 | 1010 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 7 | 1.12 | 1000 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.4 | 0.38 | 763 |
| `AP_two` two off-topic questions, then a normal call | 8 | 100% | 100% | 7.5 | 0.5 | 977 |
| `AP_three` three off-topic questions in a row from the start | 8 | 62% | 38% | 4.9 | 0.75 | 857 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 89% | 89% | 6.9 | 1.0 | 1230 |
| `NG_P_V` | 9 | 100% | 78% | 6.4 | 0.89 | 1518 |
| `NG_C_NV` | 9 | 100% | 78% | 5.4 | 1.0 | 1041 |
| `NG_C_V` | 9 | 78% | 89% | 5.9 | 1.22 | 936 |
| `G_P_NV` | 9 | 89% | 78% | 5.4 | 0.33 | 924 |
| `G_P_V` | 9 | 78% | 89% | 6 | 0.67 | 887 |
| `G_C_NV` | 9 | 100% | 78% | 4.7 | 0.33 | 742 |
| `G_C_V` | 9 | 89% | 78% | 4.4 | 0.0 | 768 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | **FAIL** |
| `G_P_NV` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |
| `G_P_V` | **FAIL** | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | **FAIL** | pass | pass | pass | pass | pass | pass |

## Failed checks

| Check | Calls |
| --- | ---: |
| `no_quote` | 3 |
| `off_topic_end` | 3 |
| `faq_answered` | 3 |
| `vehicles` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
| `api_down_at_quote` | 2/2 |
| `change_route_after_quote` | 2/2 |
| `change_vehicle_after_quote` | 2/2 |
| `city_not_found` | 2/2 |
| `faq_during_read_back` | 2/2 |
| `faq_mid_call` | 2/2 |
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

- [NG_P_NV__AP_three](transcripts.md#ng_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_V__QHP](transcripts.md#ng_c_v__qhp): ended, failed `faq_answered`
- [NG_C_V__AP_three](transcripts.md#ng_c_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_P_NV__QHP](transcripts.md#g_p_nv__qhp): ended, failed `faq_answered`
- [G_P_V__SHP](transcripts.md#g_p_v__shp): ended, failed `vehicles`
- [G_P_V__AP_three](transcripts.md#g_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_C_V__QHP](transcripts.md#g_c_v__qhp): ended, failed `faq_answered`
