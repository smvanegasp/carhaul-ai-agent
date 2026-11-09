# AGENTS.md: Mia, the CarHaul voice agent

Read this first. It is the full context for continuing work in a new chat. The staged plan and
open work live in **[docs/BACKLOG.md](docs/BACKLOG.md)**; how Mia should talk lives in
**[docs/CONVERSATION_DESIGN.md](docs/CONVERSATION_DESIGN.md)**. Keep all three up to date.
**[README.md](README.md)** is the public explanation; update it in the same PR whenever the
architecture, CI/CD, AWS or testing story changes.

This app is a sibling of `C:\Users\smvan\repos\fit-mgmt-app` and
`C:\Users\smvan\repos\pantry-mgmt-app`. **When in doubt, do it the way fit does**: same stack
for the web/API side, same Terraform, CI/CD, SSM and safety conventions. Copy and adapt their
files rather than reinventing.

---

## 1. What this is

- **Mia** is a voice AI agent for **F&F** that gives **open car-shipping quotes** using the
  CarHauler247 public API (main site <https://carhauler247.com/>).
- People **call Mia from the browser** (desktop or phone). Later (stage 9) also from a real
  phone number, with transfer to Sergio's phone.
- While on a call, the caller sees a **live panel** (half the screen on desktop): transcript,
  tool calls with their JSON, latency per component.
- A **public dashboard** shows aggregate stats (averages and medians, no time series): outcomes,
  drop-off stage, human requests, talk share, interruptions, latency, tool success, and every
  call with its transcript and tool JSON.
- It is also **Sergio's portfolio**: monitoring, guardrails and testing are part of the story.
- **Owner:** Sergio (GitHub `smvanegasp`). Repo <https://github.com/smvanegasp/carhaul-ai-agent>
  (**public**). Develops on Windows 11 (Git Bash, VS Code, uv, Node 24, Docker Desktop).
- **Teammate** (non-technical): manual tester. From stage 4 she calls the deployed agent, acts
  out persona cards from `docs/TESTING_GUIDE.md` and leaves feedback per call.

## Status (2026-11-09)

Stages 0-2 merged (PRs #1, #3-#5). **Stage 3** (branch `stage-3-web-calling`): voice calls from
the browser work locally (`docker compose up`, then "Call Mia" on http://localhost:5190),
verified end to end with scripted voice calls (`python -m mia.smoke`), real quotes included
(CarHauler now has a payment method; calls are paid, so still budget them). Turn detector
chosen: `v1-mini` (BACKLOG has the 5+5 call table). Left: Sergio's own browser call (desktop
and phone). Stages 3 and 5 (live panel, call records, feedback) merged (PRs #7, #8).
**Stage 4** (branch `stage-4-aws`, PR #9): Terraform, deploy script and workflow, SSM secrets
script, TESTING_GUIDE; the worker is **on demand** (started by `/api/wake`, exits when idle) so
hosting stays around $1/month. Profile `carhaul` exists (account 816940506502). Next:
`terraform plan`, then Sergio's OK for the first `scripts/deploy.sh`. No custom domain yet
(the cloudfront.net address); later `carhaul.sergiovanegas.com`.

## 2. How we work

- **Small stages, one branch and one PR each** (`stage-N-name`). Sergio merges; merging deploys
  (from stage 4).
- Tests and lint pass before a PR. Behavior changes to Mia come with a scenario test.
- The agent may run `terraform plan`; **`terraform apply` needs Sergio's OK.** CI never applies
  Terraform.
- Check `git status` before committing; never `git add -A` blindly.
- Decide with data when it's cheap: e.g. the model choice was made from 5 runs x 3 scenarios per
  model (pass rate, invented calls, latency), not from assumptions. Sergio likes seeing the table.
- When the LLM misbehaves, prefer a guardrail in code (grounding.py / guardrails.py) plus a test
  over more prompt text; record what was observed in the module docstring.
- Windows: run ad-hoc Python edit scripts with `PYTHONUTF8=1` / explicit `encoding="utf-8"`
  (a cp1252 write once emptied a file); print with `PYTHONIOENCODING=utf-8`.
- LiveKit Agents is 1.8.x: check signatures in `agent/.venv` before using an API (it changes
  fast), e.g. `uv run python -c "import inspect, livekit.agents as a; ..."`.

## 3. Architecture

```
Browser (React/Vite) ──/api/token──► CloudFront ─► API GW ─► Lambda (FastAPI) ◄──► DynamoDB
   │ WebRTC audio + data
   ▼
LiveKit Cloud ◄──► Agent worker (ECS Fargate, livekit-agents)
                    STT Deepgram · LLM Groq openai/gpt-oss-20b · TTS ElevenLabs
                    tools → CarHauler247 API, Google Maps Geocoding
```

The agent worker keeps a WebSocket open to LiveKit for the whole call, so it runs on ECS
Fargate, not Lambda. Everything else follows the fit pattern.

### Agent modules (`agent/src/mia/`)

| Module | What |
| --- | --- |
| `agent.py` | `Mia` (LiveKit `Agent`): tools, the output guardrail in `llm_node`, `GroqLLM` (strict schemas off), `new_session()` |
| `prompt.py` | Instructions and greetings (from `docs/CONVERSATION_DESIGN.md`) |
| `state.py` | `QuoteSession`: what's on file, quote IDs, trash, stage reached, dropped calls |
| `tools.py` | Tool logic, LiveKit-free: every result has `on_file` and `next` (what Mia does now) |
| `grounding.py` | Was this detail actually said by the caller? Vehicle count, yes detection |
| `guardrails.py` | Drops invented/unconfirmed tool calls before they run; fallback lines; `tidy_speech` |
| `geo.py`, `carhauler.py`, `vehicles.py`, `pricing.py` | City → ZIP, CarHauler API, year/make/model → trim, quotes and the spoken summary |
| `chat.py` | `uv run python -m mia.chat`: talk to Mia by typing (real APIs) |
| `main.py` | The voice worker (`AgentServer`, agent name `mia`): STT/TTS/VAD/turn detector, filler and hang-up hooks, 6-min limit, events published to the room, call record saved at the end |
| `events.py` | `CallEvents`: turns with latency, tool calls with JSON, guardrail drops, state; the live panel's stream (`mia.events`) and the record's content |
| `records.py` | The call record and its DynamoDB write (keys documented there; shared table with the backend) |
| `idle.py` | On AWS the worker exits after 10 idle minutes (no call, no wake) or 2 hours, so it only costs money around calls |
| `catalog.py` | CarHauler catalog snapshot on disk (a week), so worker restarts don't spend API calls |
| `latency.py` | Per-turn latency from `ChatMessage.metrics` (end of turn, LLM TTFT, TTS TTFB, e2e) |
| `smoke.py` | `uv run python -m mia.smoke [--api http://localhost:5190]`: a scripted caller phones the running worker through LiveKit |

### Repo map

| Path | What |
| --- | --- |
| `agent/` | uv project `mia-agent`, package `src/mia/` (see below). `evals/scenarios/*.yaml`: reference conversations |
| `backend/` | uv project `carhaul-api`: FastAPI for Lambda (`app/`). `POST /api/token` (`livekit_token.py`, rate limited by `ratelimit.py`), `POST /api/calls/{room}/feedback` (`calls.py`), `POST /api/wake` (`worker.py`: starts the on-demand worker), DynamoDB in `db.py`. Later: call list and stats |
| `frontend/` | React 19 + Vite + Tailwind v4 + LiveKit components. `src/call/`: `CallPage.tsx` (call, state, timer, mute, transcript), `LivePanel.tsx` (from `lib/events.ts`), `FeedbackForm.tsx`. Later: dashboard |
| `notebooks/` | Exploration only; kernel is `agent/.venv` (`uv sync --group notebooks`) |
| `docs/` | BACKLOG, CONVERSATION_DESIGN, TESTING_GUIDE (stage 4) |
| `infra/` | Terraform (profile `carhaul`, everything `carhaul-*`): DynamoDB, Lambda + HTTP API, S3 + CloudFront (custom domain optional), on-demand ECS Fargate worker task (`agent.tf`), GitHub OIDC deploy role, alarms. `bootstrap/`: the state bucket |
| `scripts/` | `deploy.sh` (images, `terraform apply`, frontend, new worker), `set_aws_secrets.py` (.env → SSM), `upload_frontend.sh` |

## 4. Run and test

```sh
cd agent    && uv sync && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd backend  && uv sync && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd frontend && npm ci && npm test && npm run build
docker compose up        # api :8020, web :5190, DynamoDB Local :8030, agent worker (connects out to LiveKit)
```

- Voice without Docker: `cd agent && uv run python -m mia.main dev` (worker) plus the api and
  web. Run **either** the compose `agent` or a host worker: both register as `mia` and would
  split the calls. `uv run python -m mia.main console` talks to Mia with your own mic.
- `uv run python -m mia.smoke` (in `agent/`) phones the running worker with a scripted caller
  and prints the transcript and timings; `--api http://localhost:5190` goes through
  `/api/token` like the browser. Each run is ~1 min of paid APIs **and CarHauler calls**.
- Share with the teammate: `ngrok http 5190` (ngrok is installed and logged in on Sergio's
  machine); the https URL gives the browser mic access. The token endpoint's per-IP limit
  sees the viewer's IP through ngrok's `X-Forwarded-For`.
- **CarHauler allowance:** every catalog lookup and quote counts (free tier: 1,000 calls). The
  worker reuses the catalog snapshot on disk (`~/.cache/mia/catalog.json`, compose volume
  `agent_cache`); don't delete it casually. Live tests and smoke calls spend calls too.

- `uv run pytest -m live` (in `agent/`) runs tests that call **paid APIs** (Google Maps,
  CarHauler; Groq later). They are deselected by default and never run in CI except where a
  stage says so explicitly. `tests/test_geo_accuracy.py` is about 100 Google calls;
  `tests/test_vehicles_live.py` about 80 CarHauler lookups and 1 quote.
- `uv run python -m mia.chat` (in `agent/`) talks to Mia by typing, with the real Groq, Google
  and CarHauler APIs; it prints every tool call, its JSON and anything the guardrail dropped.
- `uv run pytest -m llm` replays `evals/scenarios/*.yaml` against the real LLM (fake CarHauler
  and geocoder, so prices are fixed). `MIA_LLM_MODEL` switches the model. CI runs it when the
  `GROQ_API_KEY` repository secret is set.
- Offline tests use `tests/fake_carhauler.py` (respx), which mimics the real API's quirks.
  **Never assert live prices**; they change weekly.
- CI (`.github/workflows/ci.yml`): agent, backend, frontend, docker build, gitleaks.

## 5. Secrets and safety

- Local secrets live in the repo-root `.env` (git-ignored); names are in `.env.example`. On AWS
  they go to SSM Parameter Store (`scripts/set_aws_secrets.py`): `/carhaul/api/` (LiveKit key,
  read by the Lambda) and `/carhaul/agent/` (every provider key, injected into the ECS task).
- **Never print, cat or echo secret values**; check only that a variable is set (or its length).
  Never ask Sergio to paste keys into chat. Never commit them; gitleaks runs in CI.
- Sergio's phone number (stage 9) goes only to SSM as `TRANSFER_PHONE_NUMBER`.
- The site is public and every call spends money (Groq, Deepgram, ElevenLabs, LiveKit): keep the
  token-endpoint rate limit, the daily call cap and the max call length.

## 6. Decisions log

- 2026-11-08: Browser calling first, phone (Twilio + LiveKit SIP) in stage 9. LiveKit **Cloud**,
  not self-hosted. Brand and persona: **Mia from F&F**. Teammate role: manual tester and
  feedback. Prices and the spoken quote summary are computed by code, never by the LLM.
- 2026-11-08 (stage 2): **gpt-oss invents tool calls** ("Yeah, sure" became
  save_origin_destination("Los Angeles") 6/6 times on 20b; 120b does it about as often once
  guarded). So guardrails live in code, not only in the prompt: tool calls on details the
  caller never said, duplicate saves and quotes without a "yes" are dropped before they run;
  spoken text is tidied (no repeats, one question at a time); the vehicle count and the yes
  are detected from the caller's words.
- 2026-11-09 (stage 3): Voice stack: Deepgram nova-3, ElevenLabs `eleven_flash_v2_5` (the
  plugin reads `ELEVEN_API_KEY`, so the key is passed explicitly), Silero VAD,
  `livekit.agents.inference.TurnDetector` (the `turn-detector` plugin is deprecated in 1.8),
  interruptions on with LiveKit defaults. Explicit dispatch: `/api/token` puts
  `RoomAgentDispatch("mia")` in the token; one room per call, max 2 participants. Hang-up runs
  in a done-callback on the `end_call` tool's speech handle (the 1.8 `EndCallTool` pattern),
  so the goodbye plays first. The token endpoint's rate limit uses fit's interface with
  in-memory counters until DynamoDB arrives in stage 4.
- 2026-11-09: **CarHauler free tier ran out** (1,000 calls, catalog lookups included). The
  worker had re-fetched the catalog (69 calls) on every process start; now it's cached on disk
  for a week (`catalog.py`).
- 2026-11-09 (stage 4): **Hosting must stay around $1-2/month** (Sergio: personal project). So
  the worker is an **on-demand ECS Fargate task**, not a service: opening the call page calls
  `/api/wake`, which starts it (~1 min cold start; at most 20 starts a day; a lock row prevents
  double starts) and the page waits until its health check (registered with LiveKit) passes.
  The worker exits after 10 minutes with no call and no wake, or after 2 hours (`idle.py`). An
  always-on 1 vCPU / 3 GB task would have been ~$39/month. It runs in the default VPC's public
  subnets with a public IP (outbound only, no load balancer, no NAT: NAT alone is ~$32/month),
  `v1-mini` turn detector, 2 warm processes. ECR keeps 2 images per repo (storage is billed).
  The CarHauler catalog snapshot is also kept in DynamoDB (gzipped, ~22 KB) because tasks have
  no lasting disk: otherwise each start would spend 69 paid calls. Rate-limit counters moved to
  DynamoDB (fit's `db.increment`). Secrets split by reader: the API only sees the LiveKit key.
- 2026-11-09 (stage 5): The worker writes the call record to DynamoDB itself (boto3, ECS task
  role later) instead of posting it to the API: no internal endpoint to protect, and the API
  stays the browser's. Live panel events travel as LiveKit text streams (topic `mia.events`,
  no size limit, unlike data packets). Feedback doesn't require the record to exist yet (the
  form shows as the call ends, before the worker has saved it).
- 2026-11-08: **Model: `openai/gpt-oss-20b`** (env `MIA_LLM_MODEL` to switch). 5 runs x 3
  scenarios with the guardrails: 20b 15/15, p50 412 ms per turn; 120b 14/15, 584 ms; Qwen
  3.8 27B 15/15 with zero invented calls but 958 ms. Llama is no longer offered on Sergio's
  Groq account. Re-check with the stage 7 persona simulations.
