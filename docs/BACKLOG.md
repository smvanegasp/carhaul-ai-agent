# Backlog and staged plan

One branch and one PR per stage. ✅ done · 🔜 next · ⏳ later.

| # | Stage | Status |
| --- | --- | --- |
| 0 | Scaffold: agent/backend/frontend projects, `geo.py` moved into the agent, CI, Dependabot, docs | ✅ |
| 1 | CarHauler client (retries, 401/402, caching), vehicle resolution (fuzzy YMM → trim), pricing and spoken summary | ✅ |
| 2 | Agent core in text: prompt, `QuoteSession` state, tools, guardrails, LiveKit `AgentSession` + Groq; 3 happy-path scenario tests | ✅ |
| 3 | Web calling locally: `/api/token`, call page, Deepgram + ElevenLabs, turn detector, interruptions. Optional: share the local app through ngrok so the teammate can try it before AWS | 🔜 PR #7 open |
| 4 | AWS deploy: Terraform (fit + ECS Fargate for the worker), Deploy workflow, SSM secrets, TESTING_GUIDE. **Teammate starts testing** | 🔜 PR open (on top of #8), needs the `carhaul` profile |
| 5 | Live panel (`mia.events`), call record to DynamoDB, feedback form per call | 🔜 PR open (on top of #7) |
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
- [x] CarHauler 402 resolved (Sergio added a payment method, 2026-11-09); quotes work again
- [x] Turn-detector measurement with quotes working (below): no latency difference, so
      **`v1-mini`** (local) for ECS. Set `MIA_TURN_DETECTOR=v1-mini` in the stage 4 task
      definition
- [ ] Sergio: a real call from the browser (desktop and phone) to check echo, barge-in and
      how the turn taking feels; then share via ngrok with the teammate

### Turn detector, re-run with quotes working (2026-11-09, Docker worker, `mia.smoke`)

5 calls per setting, every one reached the real $724 quote and Mia hung up. Per call, ms
(e2e = server side, caller's end of speech to Mia's first audio; heard = as the scripted caller
hears it):

| Turn detector | e2e p50 | e2e p90 | end of turn p50 / p90 | STT p50 | LLM TTFT p50 | TTS TTFB p50 | Heard p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | 1959 | 3196 | 577 / 577 | 309 | 414 | 183 | 1812 |
| v1 | 1428 | 3110 | 577 / 578 | 276 | 268 | 168 | 1250 |
| v1 | 2288 | 3351 | 577 / 2502 | 277 | 492 | 164 | 2297 |
| v1 | 1351 | 3090 | 577 / 577 | 204 | 321 | 178 | 1047 |
| v1 | 1388 | 4032 | 577 / 2501 | 205 | 270 | 172 | 1359 |
| v1-mini | 1267 | 3141 | 577 / 577 | 233 | 227 | 173 | 1297 |
| v1-mini | 1605 | 3530 | 577 / 577 | 312 | 332 | 193 | 1265 |
| v1-mini | 1320 | 3127 | 577 / 2501 | 261 | 302 | 176 | 1422 |
| v1-mini | 2678 | 3106 | 578 / 2502 | 281 | 287 | 169 | 1984 |
| v1-mini | 1488 | 3271 | 577 / 578 | 305 | 374 | 182 | 1281 |
| **median v1** | **1428** | | | | | | **1359** |
| **median v1-mini** | **1488** | | | | | | **1297** |

The two models are within noise of each other. The slow calls on both sides are the same
2.5 s end-of-turn wait (the caller's line arrived as two transcripts), not the model. The
~3.1 s e2e p90 in every call is the quote turn (tool call + CarHauler + filler line).
Choice: **v1-mini**. Same latency, it is LiveKit's default for `start` (production), and it
doesn't add a per-turn call to LiveKit Inference. The cost is image size and memory on Fargate
(see the 1.57 GB note below).

### Earlier measurements (2026-11-09, partly on the CarHauler error path)

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

## Stage 4 (branch `stage-4-aws`, 2026-11-09)

- [x] Terraform in `infra/` (fit's, adapted): DynamoDB (PITR, TTL, deletion protection),
      Lambda + HTTP API, S3 + CloudFront with `mia.sergiovanegas.com`, GitHub OIDC deploy role,
      email alarms (API errors, Lambda crashes, worker down, worker errors, record not saved)
- [x] `infra/agent.tf`: ECR, ECS cluster, Fargate task (secrets from SSM, health check on the
      worker's :8081, `MIA_TURN_DETECTOR=v1-mini`), service in the default VPC (public IP,
      outbound only), deployment circuit breaker
- [x] Rate-limit counters in DynamoDB (`db.increment`, TTL); catalog snapshot shared through
      DynamoDB so new tasks don't re-fetch it
- [x] `scripts/deploy.sh`, `scripts/set_aws_secrets.py`, `.github/workflows/deploy.yml` (off
      until `DEPLOY_ENABLED`), CI `terraform` job, Dependabot for the agent image and Terraform
- [x] `docs/TESTING_GUIDE.md`: how to call, 8 persona cards + 4 extra, what to write in the
      feedback
- [ ] Sergio: AWS profile `carhaul` (same account as `gym`; if it's another account, change
      the state bucket and role ARNs that end in 816940506502)
- [ ] `terraform -chdir=infra/bootstrap apply` (state bucket), then `terraform plan`
- [ ] Sergio's OK → `cd backend && uv run python ../scripts/set_aws_secrets.py`, then
      `scripts/deploy.sh`; add the 2 DNS records at Hostinger; confirm the SNS email
- [ ] GitHub variables `DEPLOY_ENABLED`, `DISTRIBUTION_ID`, `SITE_URL`; one scripted call
      against the deployed site (`mia.smoke --api https://mia.sergiovanegas.com`)
- [ ] Share the link and TESTING_GUIDE with the teammate

Cost at rest: the Fargate worker (1 vCPU / 3 GB, always on) is ~$39/month; Lambda, DynamoDB,
CloudFront and S3 are cents at this traffic. `agent_count = 0` in tfvars stops the worker.

## Stage 5 (branch `stage-5-live-panel`, 2026-11-09)

- [x] `mia/events.py`: `CallEvents` (config, turn, tool, dropped, state, end). The worker
      publishes each event as a text stream on topic `mia.events` (`RoomPublisher` in
      `main.py`: in order, queued until the room is connected)
- [x] Tool calls wrapped in `agent._run_tool` (args, result JSON, ok, ms, then the state);
      guardrail drops, the greeting, the filler line and the time-limit line are events too
- [x] `mia/records.py`: call record (state, transcript, events, latency summary, talk time,
      interruptions, tool calls/errors) to DynamoDB at the end of the call: `CALL#<room>` /
      `RECORD`, plus a summary under `CALLS` / `<started_at>#<room>` for the stage 6 list.
      Written by the worker itself (boto3; ECS task role in stage 4). Not configured → only
      logged
- [x] Backend `app/db.py` (fit's pattern) and `POST /api/calls/{room}/feedback` (rating 1-5,
      comment, persona card; rate limited; works before the record exists)
- [x] Frontend: `LivePanel` (pipeline, stage, tool calls, drops, quote, latency medians and
      last, on file, timeline with expandable tool JSON) next to the call, kept after it;
      `FeedbackForm` after the call
- [x] `docker compose` adds DynamoDB Local (host port 8030); `mia.smoke` also checks the
      event stream (22 events, none missing, in a real call)
- [ ] Sergio: look at the panel in a real browser call (desktop and phone)

Known: when Mia hangs up she deletes the room, so the `end` event usually doesn't reach the
browser (it's in the record). The page shows "Call ended" from the disconnect anyway.

## Accounts and keys (checked 2026-11-08, read-only calls, values never printed)

| Service | Status |
| --- | --- |
| Groq | ✅ `.env` + GitHub secret `GROQ_API_KEY` (CI runs the `-m llm` scenarios: 3/3 on main) |
| CarHauler247 (QA key) | ✅ Payment method added 2026-11-09 after the free tier (1,000 calls, catalog lookups included) ran out; calls are now paid, so budget live runs |
| Google Maps Geocoding | ✅ |
| LiveKit Cloud | ✅ `LIVEKIT_URL` (wss://…livekit.cloud), key and secret work (`list_rooms`) |
| Deepgram | ✅ (1 project) |
| ElevenLabs | ✅ Default (premade) voice in `ELEVENLABS_VOICE_ID`; re-checked 2026-11-09 with a 2-character synthesis (200, `eleven_flash_v2_5`) and in real calls. The key is restricted (no `voices_read`), fine for speaking. Free accounts can't use *library* voices over the API (`402 paid_plan_required`). |
| AWS CLI profile `carhaul` | ⏳ Sergio creates it (IAM user `carhaul-deployer`, like `gym-deployer`) |
| Twilio | ⏳ stage 9 |

## Ideas / later

- `happy_path_ngc_3v` is flaky in CI (seen once on 2026-11-09: the 3rd vehicle not saved on turn 5); 10/10 locally on the branch and on main's prompt. Track its pass rate in the stage 7 simulations.

- Agent image is 1.57 GB (onnxruntime, local turn model); slim it for ECS if pulls are slow.
- Silent caller: LiveKit marks the user "away" after 15 s; Mia could ask "are you still there?" (stage 8).
- Frontend bundle is 811 kB (LiveKit client); code-split when the dashboard arrives.

- Compare `openai/gpt-oss-20b` vs `openai/gpt-oss-120b` with the simulation report.
- Ambiguous-city detection from geocoding, so Mia only confirms the state when needed.
