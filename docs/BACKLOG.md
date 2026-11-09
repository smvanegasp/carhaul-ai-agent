# Backlog and staged plan

One branch and one PR per stage. ✅ done · 🔜 next · ⏳ later.

| # | Stage | Status |
| --- | --- | --- |
| 0 | Scaffold: agent/backend/frontend projects, `geo.py` moved into the agent, CI, Dependabot, docs | ✅ |
| 1 | CarHauler client (retries, 401/402, caching), vehicle resolution (fuzzy YMM → trim), pricing and spoken summary | 🔜 |
| 2 | Agent core in text/console: prompt, `QuoteSession` state, tools, LiveKit `AgentSession` + Groq; 3 happy-path scenario tests | ⏳ |
| 3 | Web calling locally: `/api/token`, call page, Deepgram + ElevenLabs, turn detector, interruptions | ⏳ |
| 4 | AWS deploy: Terraform (fit + ECS Fargate for the worker), Deploy workflow, SSM secrets, TESTING_GUIDE. **Teammate starts testing** | ⏳ |
| 5 | Live panel (`mia.events`), call record to DynamoDB, feedback form per call | ⏳ |
| 6 | Public dashboard: stats (averages/medians), call list and detail | ⏳ |
| 7 | AI-vs-AI simulation: 8 personas × fragments, report by persona and path, nightly workflow | ⏳ |
| 8 | Non-happy paths: changes + trash, error matrix, FAQs, off-topic guardrail | ⏳ |
| 9 | Phone line: Twilio number → LiveKit SIP, transfer to Sergio's phone | ⏳ |

## Stage 1 checklist

- [ ] Verify the years endpoint (`/car/years?modelId=` vs the notes' `/car/models?modelId=`)
- [ ] Confirm which env var name to use for the CarHauler key (`CARHAULER_API_KEY_QA` today)
- [ ] `carhauler.py`: httpx + 3 tries with exponential backoff, typed errors (401, 402, 5xx, timeout)
- [ ] Cache makes/models/years/trims to save the free call allowance
- [ ] `vehicles.py`: parse partial YMM, fuzzy-match make and model, pick a trim, `MISSING_*` codes
- [ ] `pricing.py`: total + per-car naming rules + multi-vehicle line
- [ ] Unit tests (respx) and a `live` accuracy suite like `test_geo_accuracy.py`

## Accounts Sergio needs (before stages 2–4)

LiveKit Cloud project, Groq, Deepgram, ElevenLabs (pick a voice ID), AWS CLI profile `carhaul`,
Twilio (stage 9).

## Ideas / later

- Compare `openai/gpt-oss-20b` vs `openai/gpt-oss-120b` with the simulation report.
- Ambiguous-city detection from geocoding, so Mia only confirms the state when needed.
