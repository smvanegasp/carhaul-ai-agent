# Simulation run 2026-11-10T23:52:39+00:00 (baseline)

**42/72 calls passed (58%)**. Mia: `openai/gpt-oss-20b`, caller: `openai/gpt-oss-120b`, commit `b571b24`, 5.9 min, about $0.15 in Groq tokens. API errors: 19.

Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code against its ground truth (`evals/sim/run.py`, `score`). Transcripts: [transcripts.md](transcripts.md).

Outcomes: caller_done 1, ended 35, error 19, off_topic_end 3, transferred 14

## By path

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHP` strict happy path, declines the representative | 8 | 62% | 88% | 4.6 | 0.5 | 696 |
| `SHP_transfer` happy path, says yes to the representative | 8 | 75% | 88% | 4.8 | 0.5 | 668 |
| `QHP` an FAQ at the vehicle question and one after the quote | 8 | 50% | 100% | 7.2 | 1.0 | 588 |
| `NHP_correction` self-corrects the car's year | 8 | 75% | 100% | 4.5 | 0.5 | 726 |
| `NHP_change_vehicle` changes the car after the quote | 8 | 50% | 88% | 5 | 0.62 | 566 |
| `NHP_change_route` changes the destination after the quote | 8 | 50% | 50% | 4.9 | 1.12 | 746 |
| `NHP_person` asks for a person at the vehicle question | 8 | 88% | 12% | 2.6 | 0.75 | 576 |
| `AP_two` two off-topic questions, then a normal call | 8 | 38% | 50% | 5.6 | 1.12 | 721 |
| `AP_three` three off-topic questions in a row from the start | 8 | 38% | 38% | 5.4 | 0.75 | 728 |

## By persona

| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NG_P_NV` | 9 | 67% | 78% | 6.8 | 1.67 | 556 |
| `NG_P_V` | 9 | 78% | 78% | 5.9 | 0.89 | 612 |
| `NG_C_NV` | 9 | 89% | 78% | 5.3 | 0.78 | 588 |
| `NG_C_V` | 9 | 44% | 67% | 4.7 | 1.0 | 688 |
| `G_P_NV` | 9 | 22% | 44% | 4.7 | 0.89 | 898 |
| `G_P_V` | 9 | 56% | 56% | 4.3 | 0.44 | 773 |
| `G_C_NV` | 9 | 56% | 44% | 3 | 0.11 | 677 |
| `G_C_V` | 9 | 56% | 100% | 5 | 0.33 | 853 |

## Persona x path

| | `SHP` | `SHP_transfer` | `QHP` | `NHP_correction` | `NHP_change_vehicle` | `NHP_change_route` | `NHP_person` | `AP_two` | `AP_three` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NG_P_NV` | pass | pass | **FAIL** | **FAIL** | pass | pass | pass | **FAIL** | pass |
| `NG_P_V` | pass | pass | pass | pass | pass | **FAIL** | pass | pass | **FAIL** |
| `NG_C_NV` | pass | **FAIL** | pass | pass | pass | pass | pass | pass | pass |
| `NG_C_V` | **FAIL** | pass | **FAIL** | pass | **FAIL** | pass | pass | **FAIL** | **FAIL** |
| `G_P_NV` | **FAIL** | **FAIL** | pass | **FAIL** | **FAIL** | **FAIL** | pass | **FAIL** | **FAIL** |
| `G_P_V` | pass | pass | pass | pass | **FAIL** | **FAIL** | pass | **FAIL** | **FAIL** |
| `G_C_NV` | pass | pass | **FAIL** | pass | **FAIL** | **FAIL** | pass | **FAIL** | pass |
| `G_C_V` | **FAIL** | pass | **FAIL** | pass | pass | pass | **FAIL** | pass | **FAIL** |

## Failed checks

| Check | Calls |
| --- | ---: |
| `no_error` | 19 |
| `finished` | 19 |
| `vehicles` | 12 |
| `price_spoken` | 12 |
| `quoted` | 11 |
| `quote_matches` | 11 |
| `fragments_fired` | 8 |
| `off_topic_end` | 5 |
| `no_quote` | 4 |
| `faq_answered` | 3 |
| `transferred` | 2 |
| `route` | 1 |

## Scenario suite (tests/test_scenarios.py)

| Scenario | Passed |
| --- | ---: |
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
| `off_topic_three_strikes` | 3/3 |
| `remove_vehicle_after_quote` | 3/3 |
| `self_correction_year` | 3/3 |
| `undo_vehicle_change` | 3/3 |

## Failures

- [NG_P_NV__QHP](transcripts.md#ng_p_nv__qhp): ended, failed `faq_answered`
- [NG_P_NV__NHP_correction](transcripts.md#ng_p_nv__nhp_correction): ended, failed `vehicles`
- [NG_P_NV__AP_two](transcripts.md#ng_p_nv__ap_two): ended, failed `vehicles`
- [NG_P_V__NHP_change_route](transcripts.md#ng_p_v__nhp_change_route): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: Connection error. (caused by APIError: Tool call validation failed: tool call validation failed: parameters for tool save_vehicle did not match schema: errors: [`/drivable`: expected boolean, but got null]))
- [NG_P_V__AP_three](transcripts.md#ng_p_v__ap_three): ended, failed `no_quote`, `off_topic_end`
- [NG_C_NV__SHP_transfer](transcripts.md#ng_c_nv__shp_transfer): transferred, failed `vehicles`
- [NG_C_V__SHP](transcripts.md#ng_c_v__shp): error, failed `no_error`, `finished` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248370, Requested 2892. Please try again in 302.88ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [NG_C_V__QHP](transcripts.md#ng_c_v__qhp): caller_done, failed `faq_answered`
- [NG_C_V__NHP_change_vehicle](transcripts.md#ng_c_v__nhp_change_vehicle): error, failed `no_error`, `finished`, `vehicles` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 247096, Requested 2984. Please try again in 19.2ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in or)
- [NG_C_V__AP_two](transcripts.md#ng_c_v__ap_two): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248274, Requested 2671. Please try again in 226.8ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [NG_C_V__AP_three](transcripts.md#ng_c_v__ap_three): error, failed `no_error`, `finished`, `off_topic_end` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248708, Requested 2973. Please try again in 403.44ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [G_P_NV__SHP](transcripts.md#g_p_nv__shp): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 249613, Requested 2527. Please try again in 513.599999ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b`)
- [G_P_NV__SHP_transfer](transcripts.md#g_p_nv__shp_transfer): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken`, `transferred` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 249398, Requested 2547. Please try again in 466.8ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [G_P_NV__NHP_correction](transcripts.md#g_p_nv__nhp_correction): ended, failed `vehicles`
- [G_P_NV__NHP_change_vehicle](transcripts.md#g_p_nv__nhp_change_vehicle): error, failed `no_error`, `finished` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248246, Requested 3085. Please try again in 319.44ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [G_P_NV__NHP_change_route](transcripts.md#g_p_nv__nhp_change_route): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 249168, Requested 2156. Please try again in 317.76ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [G_P_NV__AP_two](transcripts.md#g_p_nv__ap_two): error, failed `no_error`, `finished`, `quoted`, `vehicles`, `quote_matches`, `price_spoken` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248023, Requested 2914. Please try again in 224.88ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [G_P_NV__AP_three](transcripts.md#g_p_nv__ap_three): ended, failed `no_quote`, `off_topic_end`
- [G_P_V__NHP_change_vehicle](transcripts.md#g_p_v__nhp_change_vehicle): error, failed `no_error`, `finished`, `price_spoken`, `fragments_fired` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248446, Requested 2539. Please try again in 236.4ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [G_P_V__NHP_change_route](transcripts.md#g_p_v__nhp_change_route): error, failed `no_error`, `finished`, `quoted`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 249135, Requested 2820. Please try again in 469.2ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [G_P_V__AP_two](transcripts.md#g_p_v__ap_two): error, failed `no_error`, `finished`, `quoted`, `quote_matches`, `price_spoken` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 247619, Requested 2525. Please try again in 34.56ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [G_P_V__AP_three](transcripts.md#g_p_v__ap_three): error, failed `no_error`, `finished`, `off_topic_end` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 247452, Requested 2725. Please try again in 42.48ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [G_C_NV__QHP](transcripts.md#g_c_nv__qhp): error, failed `no_error`, `finished` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248698, Requested 2768. Please try again in 351.84ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [G_C_NV__NHP_change_vehicle](transcripts.md#g_c_nv__nhp_change_vehicle): error, failed `no_error`, `finished`, `quoted`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIError: Failed to parse tool call arguments as JSON))
- [G_C_NV__NHP_change_route](transcripts.md#g_c_nv__nhp_change_route): error, failed `no_error`, `finished`, `quoted`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 249738, Requested 2556. Please try again in 550.56ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in )
- [G_C_NV__AP_two](transcripts.md#g_c_nv__ap_two): error, failed `no_error`, `finished`, `quoted`, `route`, `vehicles`, `quote_matches`, `price_spoken`, `fragments_fired` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 248712, Requested 2107. Please try again in 196.559999ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b`)
- [G_C_V__SHP](transcripts.md#g_c_v__shp): error, failed `no_error`, `finished` (APIConnectionError: failed to generate LLM completion after 4 attempts (caused by APIStatusError: message='Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` in organization `org_…` service tier `on_demand` on tokens per minute (TPM): Limit 250000, Used 247646, Requested 3069. Please try again in 171.6ms. ', status_code=429, retryable=True, request_id=req_…, body={'message': 'Rate limit reached for model `openai/gpt-oss-20b` in o)
- [G_C_V__QHP](transcripts.md#g_c_v__qhp): ended, failed `faq_answered`
- [G_C_V__NHP_person](transcripts.md#g_c_v__nhp_person): ended, failed `no_quote`, `transferred`, `fragments_fired`
- [G_C_V__AP_three](transcripts.md#g_c_v__ap_three): ended, failed `no_quote`, `off_topic_end`
