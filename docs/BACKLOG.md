# Backlog and staged plan

One branch and one PR per stage. ✅ done · 🔜 next · ⏳ later.

| # | Stage | Status |
| --- | --- | --- |
| 0 | Scaffold: agent/backend/frontend projects, `geo.py` moved into the agent, CI, Dependabot, docs | ✅ |
| 1 | CarHauler client (retries, 401/402, caching), vehicle resolution (fuzzy YMM → trim), pricing and spoken summary | ✅ |
| 2 | Agent core in text/console: prompt, `QuoteSession` state, tools, LiveKit `AgentSession` + Groq; 3 happy-path scenario tests | 🔜 |
| 3 | Web calling locally: `/api/token`, call page, Deepgram + ElevenLabs, turn detector, interruptions. Optional: share the local app through ngrok so the teammate can try it before AWS | ⏳ |
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

## Stage 2 checklist

- [ ] `QuoteSession` state (route, vehicles with quote IDs, trash, stage reached)
- [ ] Tools wrapping geo / vehicles / pricing, each returning `{ok, data | error_code, say_hint}`
- [ ] Prompt from CONVERSATION_DESIGN (per-turn logic, greeting, FAQs, never invent)
- [ ] LiveKit `AgentSession` with Groq `openai/gpt-oss-20b`; console mode
- [ ] Scenario tests for `happy_path_ngc_1v/2v/3v` (tool calls and args, not prices)
- [ ] Warm the vehicle model index at worker startup (`prewarm`)

## Accounts Sergio needs (before stages 2–4)

LiveKit Cloud project, Groq, Deepgram, ElevenLabs (pick a voice ID), AWS CLI profile `carhaul`,
Twilio (stage 9).

## Ideas / later

- Compare `openai/gpt-oss-20b` vs `openai/gpt-oss-120b` with the simulation report.
- Ambiguous-city detection from geocoding, so Mia only confirms the state when needed.
