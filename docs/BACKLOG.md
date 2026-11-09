# Backlog and staged plan

One branch and one PR per stage. ✅ done · 🔜 next · ⏳ later.

| # | Stage | Status |
| --- | --- | --- |
| 0 | Scaffold: agent/backend/frontend projects, `geo.py` moved into the agent, CI, Dependabot, docs | ✅ |
| 1 | CarHauler client (retries, 401/402, caching), vehicle resolution (fuzzy YMM → trim), pricing and spoken summary | ✅ |
| 2 | Agent core in text: prompt, `QuoteSession` state, tools, guardrails, LiveKit `AgentSession` + Groq; 3 happy-path scenario tests | ✅ |
| 3 | Web calling locally: `/api/token`, call page, Deepgram + ElevenLabs, turn detector, interruptions. Optional: share the local app through ngrok so the teammate can try it before AWS | 🔜 |
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

## Stage 3 checklist

- [ ] Worker entry point (`mia.main`): LiveKit Cloud, Deepgram STT, ElevenLabs TTS, Silero VAD,
      turn detector, interruptions, greeting via `say()`, `prewarm` the vehicle index
- [ ] `get_quote` filler line and `end_call` hook wired to the session
- [ ] Backend `/api/token` (LiveKit access token + agent dispatch), rate limited
- [ ] Frontend call page (LiveKit components): call button, mic permission, transcript
- [ ] `docker compose up` runs api + web + agent; optional ngrok for the teammate
- [ ] Max call length (6 min)

## Accounts Sergio needs (before stages 2–4)

LiveKit Cloud project, Groq, Deepgram, ElevenLabs (pick a voice ID), AWS CLI profile `carhaul`,
Twilio (stage 9).

## Ideas / later

- Compare `openai/gpt-oss-20b` vs `openai/gpt-oss-120b` with the simulation report.
- Ambiguous-city detection from geocoding, so Mia only confirms the state when needed.
