# Backlog and staged plan

One branch and one PR per stage. ✅ done · 🔜 next · ⏳ later.

| # | Stage | Status |
| --- | --- | --- |
| 0 | Scaffold: agent/backend/frontend projects, `geo.py` moved into the agent, CI, Dependabot, docs | ✅ |
| 1 | CarHauler client (retries, 401/402, caching), vehicle resolution (fuzzy YMM → trim), pricing and spoken summary | ✅ |
| 2 | Agent core in text: prompt, `QuoteSession` state, tools, guardrails, LiveKit `AgentSession` + Groq; 3 happy-path scenario tests | ✅ |
| 3 | Web calling locally: `/api/token`, call page, Deepgram + ElevenLabs, turn detector, interruptions. Optional: share the local app through ngrok so the teammate can try it before AWS | 🔜 PR open, blocked on CarHauler 402 |
| 4 | AWS deploy: Terraform (fit + ECS Fargate for the worker), Deploy workflow, SSM secrets, TESTING_GUIDE. **Teammate starts testing** | ⏳ |
| 5 | Live panel (`mia.events`), call record to DynamoDB, feedback form per call | ⏳ |
| 6 | Public dashboard: stats (averages/medians), call list and detail | ⏳ |
| 7 | AI-vs-AI simulation: 8 personas × fragments, report by persona and path, nightly workflow | ⏳ |
| 8 | Non-happy paths: changes + trash, error matrix, FAQs, off-topic guardrail | ⏳ |
| 9 | Phone line: Twilio number → LiveKit SIP, transfer to Sergio's phone | ⏳ |

## Stage 1 (done 2026-11-08)

- `mia/carhauler.py`: async client, 3 tries with exponential backoff for transient errors only,
  typed `ErrorCode`s, catalog cached for a day. Real API behavior is recorded in
  `docs/CONVERSATION_DESIGN.md` (CarHauler247 API section).
- `mia/vehicles.py`: year/make/model → trim with typos, spoken numbers, aliases, model-only input;
  `VehicleErrorCode` drives the next question.
- `mia/pricing.py`: sequential quotes (deduped), total, naming rules, multi-vehicle line, transit
  days.
- Live suite `tests/test_vehicles_live.py`: 40/40 plus one real quote.

## Stage 2 (done 2026-11-08)

- Agent (`agent.py`, `prompt.py`, `state.py`, `tools.py`) running on LiveKit `AgentSession` in
  text mode; `uv run python -m mia.chat` to talk to it.
- Guardrails in code (`grounding.py`, `guardrails.py`), after gpt-oss invented details in
  testing. See the decisions log in AGENTS.md.
- Scenario tests for `happy_path_ngc_1v/2v/3v` (`tests/test_scenarios.py`, `-m llm`), plus a CI
  job that runs them when the `GROQ_API_KEY` secret is set.
- Geocoding fix: a misspelled city without a state ("Bostin") now resolves to the main city
  (Boston, MA), not a small namesake (Boston, IN).

## Stage 3 (branch `stage-3-web-calling`, 2026-11-09)

- [x] Worker entry point (`mia.main`): LiveKit Cloud, Deepgram nova-3, ElevenLabs flash v2.5,
      Silero VAD, LiveKit turn detector, interruptions, greeting via `say()`, prewarm (VAD +
      catalog snapshot from disk, `catalog.py`)
- [x] `get_quote` filler line and `end_call` hang-up (after the goodbye plays; room deleted)
- [x] Backend `POST /api/token` (access token + `mia` dispatch, room per call), rate limited:
      `CALLS_PER_IP_PER_HOUR` (6) and `CALLS_PER_DAY` (60); in-memory counters until stage 4
- [x] Frontend call page: call button, mic permission errors, agent state, timer, mute, hang
      up, live transcript (`useTranscriptions`), transcript kept after the call
- [x] `docker compose up` runs api + web + agent; ngrok: `ngrok http 5190` (Vite allows
      ngrok hosts)
- [x] Max call length (6 min, `MIA_MAX_CALL_SECONDS`): Mia says a closing line and hangs up
- [x] Voice smoke test `python -m mia.smoke` (scripted caller through LiveKit), per-turn
      latency in the call log (`latency.py`)
- [ ] **Blocked: CarHauler 402** (free 1,000 calls used up). Sergio: add a payment method at
      carhauler247.com/apiClient/payment-method or ask for more calls. Until then quotes fail
      and Mia offers Sergio instead (the designed error path).
- [ ] Finish the turn-detector measurement once CarHauler works (below), then set
      `MIA_TURN_DETECTOR` explicitly for ECS
- [ ] Sergio: a real call from the browser (desktop and phone) to check echo, barge-in and
      how the turn taking feels; then share via ngrok with the teammate

### Measurements (2026-11-09, `mia.smoke`, 5 caller lines, real APIs)

Per call, median ms (e2e = caller's last word to Mia starting to answer, server side):

| Worker | Turn detector | e2e p50 | end of turn p50 / p90 | LLM TTFT p50 | TTS TTFB p50 | Heard by caller p50 |
| --- | --- | --- | --- | --- | --- | --- |
| host `dev` | v1 (cloud, auto) | 734\* | 578 / 579 | 279 | 177 | 1391 |
| Docker `start` | v1-mini (local, auto) | 2305 | 577 / 2501 | 324 | 171 | 1531 |
| Docker | v1-mini | 1629 | 577 / 577 | 334 | 165 | 1110 |
| Docker | v1-mini | 1535 | 577 / 2502 | 317 | 182 | 1765 |
| Docker | v1-mini | 1134 | 577 / 578 | 273 | 170 | 1281 |
| Docker | v1 | 994 | 577 / 577 | 187 | 179 | 1203 |
| Docker | v1 | 952 | 577 / 579 | 269 | 161 | 1140 |

\* older measure (VAD end of speech to Mia speaking). Not a fair comparison yet: the CarHauler
402 started mid-run, so most of these calls took the escalation path instead of the quote, and
the 2.5 s end-of-turn outliers are the turn detector waiting out a pause (the caller's line
arrived as two transcripts). Re-run 5 per setting with quotes working before choosing. The
4 s outlier in one v1 call was a 3 s Groq response.

## Accounts and keys (checked 2026-11-08, read-only calls, values never printed)

| Service | Status |
| --- | --- |
| Groq | ✅ `.env` + GitHub secret `GROQ_API_KEY` (CI runs the `-m llm` scenarios: 3/3 on main) |
| CarHauler247 (QA key) | ❌ 402 since 2026-11-09: free tier (1,000 calls, catalog lookups included) used up. Needs a payment method or more calls |
| Google Maps Geocoding | ✅ |
| LiveKit Cloud | ✅ `LIVEKIT_URL` (wss://…livekit.cloud), key and secret work (`list_rooms`) |
| Deepgram | ✅ (1 project) |
| ElevenLabs | ✅ Default (premade) voice in `ELEVENLABS_VOICE_ID`; re-checked 2026-11-09 with a 2-character synthesis (200, `eleven_flash_v2_5`) and in real calls. The key is restricted (no `voices_read`), fine for speaking. Free accounts can't use *library* voices over the API (`402 paid_plan_required`). |
| AWS CLI profile `carhaul` | ⏳ needed in stage 4 |
| Twilio | ⏳ stage 9 |

## Ideas / later

- Agent image is 1.57 GB (onnxruntime, local turn model); slim it for ECS if pulls are slow.
- Silent caller: LiveKit marks the user "away" after 15 s; Mia could ask "are you still there?" (stage 8).
- Frontend bundle is 811 kB (LiveKit client); code-split when the dashboard arrives.

- Compare `openai/gpt-oss-20b` vs `openai/gpt-oss-120b` with the simulation report.
- Ambiguous-city detection from geocoding, so Mia only confirms the state when needed.
