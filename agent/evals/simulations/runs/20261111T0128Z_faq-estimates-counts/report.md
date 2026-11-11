# Simulation run 2026-11-11T01:28:20+00:00 (faq-estimates-counts)

**66/72 calls passed (92%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `a8192c2`, 7.3 min, about $0.20 in Groq tokens. API errors: 0.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: caller_done 1, ended 51, off_topic_end 4, transferred 16

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 100% | 100% | 5 | 0.62 | 786 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 100% | 100% | 5.2 | 0.75 | 766 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 100% | 100% | 7.9 | 0.75 | 732 |
| `NHP_correction` self-corrects the car's year | 8 | 100% | 100% | 4.6 | 0.62 | 818 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 88% | 100% | 7 | 0.88 | 697 |
| `NHP_change_route` changes the destination after the quote | 8 | 100% | 100% | 7 | 1.25 | 867 |
| `NHP_person` asks for a person at the vehicle question | 8 | 100% | 0% | 2.5 | 0.38 | 685 |
| `AP_two` two off-topic questions, then a normal call | 8 | 88% | 100% | 7 | 0.25 | 818 |
| `AP_three` three off-topic questions in a row from the start | 8 | 50% | 50% | 5.8 | 1.12 | 777 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 78% | 89% | 7.3 | 1.44 | 761 |
| `NG_P_V` | 9 | 100% | 78% | 6.4 | 1.11 | 711 |
| `NG_C_NV` | 9 | 100% | 78% | 5.2 | 0.78 | 608 |
| `NG_C_V` | 9 | 89% | 78% | 5.4 | 1.11 | 715 |
| `G_P_NV` | 9 | 89% | 89% | 6.2 | 0.67 | 1002 |
| `G_P_V` | 9 | 89% | 89% | 5.8 | 0.44 | 920 |
| `G_C_NV` | 9 | 100% | 78% | 4.8 | 0.0 | 777 |
| `G_C_V` | 9 | 89% | 89% | 5 | 0.33 | 646 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | pass | pass | pass | pass | pass | **FAIL** | **FAIL** |
| `NG_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | pass | pass | pass | pass | **FAIL** | pass | pass | pass | pass |
| `G_P_NV` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `G_P_V` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |
| `G_C_NV` | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| `G_C_V` | pass | pass | pass | pass | pass | pass | pass | pass | **FAIL** |

## Failed checks

| Check | Calls |
| --- | ---: |
| `no_quote` | 4 |
| `off_topic_end` | 4 |
| `vehicles` | 2 |

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

- [NG_P_NV__AP_two](transcripts.md#ng_p_nv__ap_two): ended, failed `vehicles`
- [NG_P_NV__AP_three](transcripts.md#ng_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_V__NHP_change_vehicle](transcripts.md#ng_c_v__nhp_change_vehicle): ended, failed `vehicles`
- [G_P_NV__AP_three](transcripts.md#g_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_P_V__AP_three](transcripts.md#g_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_C_V__AP_three](transcripts.md#g_c_v__ap_three): ended, failed `no_quote`, `off_topic_end`
