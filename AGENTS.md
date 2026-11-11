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

## Status (2026-11-11)

Live on AWS at https://dj7jlcxkdszj1.cloudfront.net (profile `carhaul`, account 816940506502).
All stages are done and deployed through PR #27: 0-6, 7 (AI-vs-AI simulations), 8 and 9
(transfer to Sergio's phone through Twilio), plus Copy JSON on every conversation, Mia keeping
the year and make the caller already said, and FAQ facts and body-type estimates checked in
code. Mia stays on gpt-oss-20b (simulations: 20b 71/72, 120b 64/72). The worker is on demand
(`/api/wake` starts it, ~1 min; it exits after 10 idle minutes), so hosting is about $1/month.
**Keep it cheap**: simulations run only after big changes, by hand.

**Group project for now:** the custom domain (`carhaul.sergiovanegas.com`, `infra/domain.tf`,
plan checked: 2 to add, 1 to change, 0 to destroy) waits until grading ends; keep using the
cloudfront.net address until then. A phone number to call Mia is optional and not started.
Open items: BACKLOG, stage 7 "Still open". Deploys are manual (`scripts/deploy.sh` in Git Bash,
Sergio types `yes`); the GitHub deploy workflow is off until `DEPLOY_ENABLED` is set.

The project is by Sergio Vanegas (https://www.linkedin.com/in/sergio-vanegas/) and Belinda Hu
(https://www.linkedin.com/in/belinda-hu/): academic, non-commercial, prices from the
CarHauler247 public API. Transfers ring Sergio's phone (`TRANSFER_PHONE_NUMBER`), showing a
verified caller ID that is not his own number (`TRANSFER_CALLER_ID`; his own went to
voicemail). Both live only in `.env` and SSM, never in the repo.

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
| `tools.py` | Tool logic, LiveKit-free: every result has `on_file` and `next` (what Mia does now). Changes: `update_vehicle`, `remove_vehicle`, `undo_last_change`; `note_off_topic`; repeated failures escalate (`STILL_NOT_FOUND`) |
| `grounding.py` | Was this detail actually said by the caller? Vehicle count, yes detection |
| `guardrails.py` | Drops invented/unconfirmed tool calls before they run; fallback lines; `tidy_speech` |
| `geo.py`, `carhauler.py`, `vehicles.py`, `pricing.py` | City → ZIP, CarHauler API, year/make/model → trim, quotes and the spoken summary |
| `chat.py` | `uv run python -m mia.chat`: talk to Mia by typing (real APIs) |
| `main.py` | The voice worker (`AgentServer`, agent name `mia`): STT/TTS/VAD/turn detector, filler and hang-up hooks, 6-min limit, events published to the room, call record saved at the end |
| `events.py` | `CallEvents`: turns with latency, tool calls with JSON, guardrail drops, state; the live panel's stream (`mia.events`) and the record's content |
| `records.py` | The call record and its DynamoDB write (keys documented there; shared table with the backend) |
| `idle.py` | On AWS the worker exits after 10 idle minutes (no call, no wake) or 2 hours, so it only costs money around calls |
| `transfer.py` | Transfer to a licensed representative: Mia dials Sergio's phone into the call through the Twilio SIP trunk, **screens the line (press 1; a voicemail never does)** with caller and line unable to hear each other until then, introduces the caller and leaves; daily cap, ring/talk limits |
| `silence.py` | What Mia does when the caller goes quiet: "are you still there?", or a goodbye and hang-up |
| `voices.py` | The 6 American voices callers can pick (2 each: Cartesia, ElevenLabs, Deepgram; Cartesia Skylar first and default), each with a description; keys and descriptions match `backend/app/voices.py` |
| `speech.py` | Numbers written out as words before any voice reads them (`Mia.tts_node`) |
| `faq.py` | FAQ facts checked in code: if Mia's answer to an FAQ lacks its key fact (100 lb, cash on delivery...), the canonical answer is spoken first |
| `catalog.py` | CarHauler catalog snapshot on disk (a week), so worker restarts don't spend API calls |
| `latency.py` | Per-turn latency from `ChatMessage.metrics` (end of turn, LLM TTFT, TTS TTFB, e2e) |
| `smoke.py` | `uv run python -m mia.smoke [--api http://localhost:5190] [--lines ...] [--wait 45]`: a scripted caller phones the running worker through LiveKit (`--wait`: stay silent, to test silence handling) |

### Repo map

| Path | What |
| --- | --- |
| `agent/` | uv project `mia-agent`, package `src/mia/` (see below). `evals/scenarios/*.yaml`: reference conversations. `evals/sim/`: the stage 7 simulator (`catalog` personas/cases/paths, `caller` the simulated caller, `run` conversation + scoring + CLI, `report`). `evals/simulations/`: **every simulation run, committed** (README index, per run report + transcripts; public on purpose) |
| `backend/` | uv project `carhaul-api`: FastAPI for Lambda (`app/`). `POST /api/token` (`livekit_token.py`, rate limited by `ratelimit.py`), `POST /api/calls/{room}/feedback` (`calls.py`), `POST /api/wake` (`worker.py`: starts the on-demand worker), `GET /api/calls` and `GET /api/calls/{room}` (public, rate limited), `GET /api/stats` (`stats.py`: per-call milestones and Mia's time, backfilled once from records), DynamoDB in `db.py` |
| `frontend/` | React 19 + Vite + Tailwind v4 + LiveKit components. `App.tsx`: the shell (collapsible sidebar on desktop, tabs on a phone; views in the URL hash, `lib/route.ts`; the call view stays mounted so switching views never drops a call). `src/history/PastCalls.tsx`: past calls (list + the same conversation/stats views from the saved record). `src/stats/StatsPage.tsx` + `lib/stats.ts`: KPIs, funnel, trends. `IntroDialog.tsx`: what this is + the disclosure, once a session. `src/call/`: `CallPage.tsx` (layout, call controls, wake), `Conversation.tsx` (chat + inline tool calls and latency behind "Show details", built by `lib/conversation.ts`; **Copy JSON** puts the whole call record on the clipboard for feedback notes, `lib/copy.ts`), `Insights.tsx` (stage, stats, latency, on file), `FeedbackForm.tsx`, `useWake.ts` (+ `lib/wake.ts`: the wake progress bar), `ThemeToggle.tsx`. Colors are theme tokens in `src/index.css` (light by default, dark on request). Later: dashboard |
| `notebooks/` | Exploration only; kernel is `agent/.venv` (`uv sync --group notebooks`) |
| `docs/` | BACKLOG, CONVERSATION_DESIGN, TESTING_GUIDE (stage 4), `evaluation/Mia_evaluation.xlsx` (29 test calls for the team: result, rating, feedback, call ID; when it comes back filled in, read each call's record from `GET /api/calls/{call ID}` (records never expire) and turn the feedback into fixes) |
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
  web. Run **either** the compose `agent` or a host worker: both register as `mia-local` and would
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
  `GROQ_API_KEY` repository secret is set, retrying a failed scenario twice (flakes).
- `uv run python -m evals.sim.run` (in `agent/`): **AI-vs-AI simulations**, 8 personas x 9
  paths (72 calls, ~10 min, cents of Groq; no CarHauler or Google calls). `--personas`,
  `--paths`, `--repeat`, `--limit`, `--scenario-runs N` (the scenario suite N times, for pass
  rates). Each run is saved to `evals/simulations/runs/` and listed in
  `evals/simulations/README.md`: commit it, the transcripts are the project's record.
  **Run it only after big changes to Mia** (Sergio wants it cheap; no schedule). The
  `simulations.yml` workflow does the same on GitHub, by hand only, and pushes to main. Use
  `--out <scratch dir>` for throwaway tries.
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

- 2026-11-11 (Sergio's call): **Transfers are screened: press 1.** His voicemail answered the
  transfer and the SIP leg reported it as answered, so Mia introduced the caller to a voicemail
  while the caller heard both. Now the line must press 1 (DTMF) and the two can't hear each other
  until then (server-side `update_subscriptions`); no 1 -> Mia hangs up the line and tells the
  caller. Also from that call: "eliminate" is a removal word, a garbled removal makes Mia ask
  "Do you want me to remove the ...?" (a yes runs it), and spoken model numbers ground ("f one
  fifty" = F-150).

- 2026-11-11: **Simulations by hand, after big changes; no nightly run** (Sergio: no gain from
  running them every day, keep the project super cheap). The workflow stays, manual only. One
  branch on GitHub: `main` (merged and stale branches deleted).

- 2026-11-11: **FAQ facts and estimates in code.** Like prices, FAQ facts come from code
  (`faq.py`); the model's wording stays when it has the fact. Body-type estimates follow the
  design's order (year and model first; the type only after "I don't know"), and "car" alone
  is not a body type. Vehicle counts come from the makes the caller names every turn.

- 2026-11-11: **Mia keeps what the caller already said of a vehicle** (Sergio's feedback: never
  make them repeat). The year and make come from the caller's own words in code
  (`grounding.vehicle_details_in`), not from the model's tool calls, which skipped them in his
  call; `save_vehicle` merges them and the next question asks only for what's missing.

- 2026-11-10 (stage 7): **Simulations are a record, not just a test.** Every run (report and
  full transcripts) is committed to `agent/evals/simulations/`, public. The runner
  scripts *when* fragments happen and a model plays the caller (gpt-oss-120b); scoring is code
  against ground truth, so it's cheap (~$0.20 a run), the same every run and re-scorable
  from saved records. Groq's 250k TPM caps it at 2 calls at once. First run: 58%, mostly
  rate limits; it found a crash in #23's no-tools retry and a read-back naming a car that
  wasn't on file (now rebuilt from state, `honest_read_back`).

- 2026-11-10 (stage 8 follow-ups): **CI retries LLM scenarios** (`--reruns 2`): main went red
  after #22 on known 1-in-5 flakes; a scenario now fails the build only after 3 misses in a
  row, and pass rates belong to stage 7. **Dropped step + a question → ask the model again
  with no tools** (not the fallback line, which ignored the FAQ). **keep_going re-reads the
  details** when all is on file but unquoted: a real call was lost after an FAQ at the
  read-back (0/5 → 5/5). Tests can now script the LLM (`tests/scripted_llm.py`) to reproduce a
  guardrail path exactly when the real model won't do it on demand.

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
- 2026-11-09: **Voice picker**: callers choose Mia's voice from 6 (top 2 of ElevenLabs,
  Cartesia, Deepgram). The choice rides in the agent dispatch metadata, so no extra API or
  state; the API only accepts known keys. All voices run at speed 0.92 and get numbers as words.
- 2026-11-09: **Voices, second pass** (Sergio's feedback): American voices only (each tagged
  American in its provider's catalog: Cartesia Skylar and Morgan, ElevenLabs Sarah and Jessica,
  Deepgram Thalia and Athena), back to each provider's **normal pace** (0.92 felt too slow),
  **Cartesia Skylar first** (the page starts with it and doesn't label it "default"), and a
  one-line description per voice under the dropdown. `ELEVENLABS_VOICE_ID` is no longer used
  (that voice's accent couldn't be confirmed); it stays in SSM, harmless.
- 2026-11-09 (UI): After Sergio's first calls: a **keyboard-typing sound** (LiveKit's built-in
  `KEYBOARD_TYPING` clip on a background track, 2 s) plays between "give me one second" and the
  price; `get_quote` waits for it (max 8 s). The chat and the panel's timeline showed the same
  thing twice, so there's **one conversation view**: bubbles from LiveKit's live transcription,
  with tool calls, guardrail drops and per-turn latency placed inline by wall-clock time
  (events carry `at`) behind a "Show details" switch. On desktop the page fits the screen and
  only the conversation scrolls. **Navy theme with dark mode** through CSS-variable tokens on
  one navy scale (the first dark mode was too dark to inspect). Numbers are written out as
  words before TTS (`speech.py`) and a goodbye from Mia hangs up even without `end_call`.
- 2026-11-09: **Palette, third pass** (Sergio: still too dark, "more professional, McKinsey
  colors"): light consulting-style palette (white and cool grey, deep blue `#051C2C` ink,
  electric blue `#2251FF` actions, cyan `#00A9F4` highlights, serif title). **Light by default
  whatever the OS says** (the OS dark mode was what made it dark); dark mode is a toggle,
  remembered in the browser. Wake-up shows a **progress bar**: `/api/wake` reports a `step`
  from the ECS task (`server` while PROVISIONING/PENDING, `loading` once it runs) and the bar
  moves with time inside that step, never 100% before ready.
- 2026-11-10 (stage 8, part 3): **Errors, FAQs, off-topic.** Repeated "not found" on the same
  detail escalates on the 3rd try; service failures escalate at once; both cities are looked
  up before reporting a failure. `keep_going` (code) adds the next question when Mia answers
  without one while details are missing (gpt-oss stopped after FAQ answers). `note_off_topic`
  ends the call on the 3rd unrelated question, guarded so a shipping turn never counts. The
  scenario runner can simulate CarHauler outages per turn. Known flakiness (~1 in 5):
  `faq_mid_call` payment wording, `off_topic_three_strikes` 3rd call not made; both harmless.
- 2026-11-10 (stage 8, part 2): **Changes and the trash.** `update_vehicle`,
  `remove_vehicle`, `undo_last_change` (route changes reuse `save_origin_destination`); each
  change goes to the trash with a new quote ID and drops the quote. Remove and undo only run
  on the caller's own cue (guardrails), since they change what's priced. 4 new scenarios, 5/5
  each; live voice re-quote after a vehicle change worked with the real APIs.
- 2026-11-10 (stage 8, first part): **Self-corrections and silence**, both from Sergio's calls.
  The year a caller corrects to wins, in code (`grounding.corrected_year` in `save_vehicle`):
  the scenario with his exact phrasing failed 5/5 without it (the model kept 2010), passes
  10/10 with it. The same test showed gpt-oss inventing `total_vehicles=2`, so the count is now
  grounded too. Silence: LiveKit's "away" (15 s) -> `silence.py`; the caller stays "away"
  until they speak, so `reset_away_timer()` after "are you still there?" is what lets a second
  silence end the call.
- 2026-11-10: **Dispositions, all-time stats, credits.** Sergio: calls come in bursts, so no
  date ranges or trends over time; add voice dispositions (organic transfer = yes to Mia's
  offer, requested = asked for a person, forced = a tool failed and Mia handed over; hung up
  on hold, hung up, not interested). The worker records `transfer_kind` (and `escalated`, set
  when a tool tells Mia to offer a person); older records are inferred (after a quote:
  organic). The About popup and sidebar credit Sergio Vanegas and Belinda Hu (LinkedIn),
  CarHauler247's public API, "academic, non-commercial", and link the repo.
- 2026-11-10 (stage 6): **Stats tell a story.** Sergio: transfers are the KPI (a
  representative picked up = a qualified lead); time handled by Mia (until the handoff) is time
  the business gets back; a funnel call → cities → vehicles → quote → transfer, over time.
  Milestones per call, not the furthest stage (callers skip around). The API returns one row
  of facts per call; the browser computes KPIs, funnel and days in the viewer's time zone.
  Scripted `smoke-*` calls are hidden by default. Charts are hand-made SVG (no library), one
  ordinal blue ramp validated with the dataviz validator in both modes. **Dark mode is
  graphite**, not navy (Sergio disliked it twice; light mode stays). **Intro popup** with the
  disclosure, once per session, auto-closes after 15 s; "About & disclosure" reopens it.
- 2026-11-09 (stage 9): **Transfer to a licensed representative.** Mia never says "Sergio,
  who built this" (Sergio: sounds arrogant); the page discloses that transfers ring his phone.
  The browser caller isn't SIP, so Mia **dials Sergio into the room** (Twilio Elastic SIP trunk,
  trunk details inline per call) and leaves after a handoff line; the room ends when either
  person hangs up. Twilio upgraded ($20 prepaid, ~1 cent a minute) with **no Twilio number**:
  caller ID is a verified number that is *not* the one called (calling Sergio from his own
  number went to voicemail). Guardrail: `request_human` runs only on the caller's own request
  or a yes to Mia's offer, because it rings a real phone. 10 transfers a day (was 5 until 2026-11-11), 30 s ring, 10 min.
- 2026-11-09 (stage 4): **Local and AWS workers have different names**: the first scripted
  call on AWS was answered by the local Docker worker, because both registered as `mia` on the
  same LiveKit project. Now `MIA_AGENT_NAME` is `mia` only on AWS (task definition and Lambda);
  everything local defaults to `mia-local`. Also, the two warm processes of a fresh task both
  fetched the CarHauler catalog (2 x 69 paid calls): `catalog.warm` now takes a file lock.
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
  Groq account. **Re-checked with the stage 7 simulations (2026-11-11): 20b 71/72, 120b
  64/72 at twice the cost; 20b stays.**
