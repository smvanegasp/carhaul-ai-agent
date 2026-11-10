# Backlog and staged plan

One branch and one PR per stage. ✅ done · 🔜 next · ⏳ later.

| # | Stage | Status |
| --- | --- | --- |
| 0 | Scaffold: agent/backend/frontend projects, `geo.py` moved into the agent, CI, Dependabot, docs | ✅ |
| 1 | CarHauler client (retries, 401/402, caching), vehicle resolution (fuzzy YMM → trim), pricing and spoken summary | ✅ |
| 2 | Agent core in text: prompt, `QuoteSession` state, tools, guardrails, LiveKit `AgentSession` + Groq; 3 happy-path scenario tests | ✅ |
| 3 | Web calling locally: `/api/token`, call page, Deepgram + ElevenLabs, turn detector, interruptions. Optional: share the local app through ngrok so the teammate can try it before AWS | ✅ |
| 4 | AWS deploy: Terraform (fit + on-demand ECS Fargate worker), Deploy workflow, SSM secrets, TESTING_GUIDE. **Teammate starts testing** | ✅ |
| 5 | Live panel (`mia.events`), call record to DynamoDB, feedback form per call | ✅ |
| 6 | Public dashboard: Past calls (list + detail) and Stats (KPIs, funnel, trends) | ✅ |
| 7 | AI-vs-AI simulation: 8 personas × fragments, report by persona and path, nightly workflow | ⏳ |
| 8 | Non-happy paths: changes + trash, error matrix, FAQs, off-topic guardrail | ⏳ |
| 9 | Transfer to a licensed representative (Sergio's phone) through a Twilio SIP trunk ✅ (this PR); later a phone number to call Mia | 🔜 |

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
      Lambda + HTTP API, S3 + CloudFront (custom domain optional: `domain` in tfvars), GitHub
      OIDC deploy role, email alarms (API errors, Lambda crashes, worker not starting, worker
      errors, record not saved)
- [x] `infra/agent.tf`: ECR, ECS cluster, Fargate task definition (secrets from SSM, health
      check on the worker's :8081 every 10 s, `MIA_TURN_DETECTOR=v1-mini`), default VPC
      (public IP, outbound only). **No ECS service: the worker is on demand**
- [x] On demand: `POST /api/wake` (`backend/app/worker.py`) starts the task (lock row, 20
      starts/day) and reports `starting`/`ready`; the call page wakes Mia on load and waits;
      `mia/idle.py` exits the worker after 10 idle minutes or 2 hours (checked in Docker: it
      drains and exits 0)
- [x] Rate-limit counters in DynamoDB (`db.increment`, TTL); catalog snapshot shared through
      DynamoDB so new tasks don't re-fetch it
- [x] `scripts/deploy.sh`, `scripts/set_aws_secrets.py`, `.github/workflows/deploy.yml` (off
      until `DEPLOY_ENABLED`), CI `terraform` job, Dependabot for the agent image and Terraform
- [x] `docs/TESTING_GUIDE.md`: how to call, 8 persona cards + 4 extra, what to write in the
      feedback
- [x] Sergio: AWS profile `carhaul` (same account as `gym`)
- [x] `terraform -chdir=infra/bootstrap apply` (state bucket), secrets, `scripts/deploy.sh`
      (Sergio, 2026-11-09): https://dj7jlcxkdszj1.cloudfront.net. First apply failed on an
      apostrophe in the security group description (AWS rejects it); fixed and re-run
- [x] Scripted call through the live site: wake 64 s, $724 quote, record + list entry in
      DynamoDB, 0 worker errors. The first try was answered by the local Docker worker (same
      agent name): now `mia` on AWS, `mia-local` locally
- [x] Sergio: confirm the SNS email.
- [x] Sergio's first real browser call (2026-11-09): the page went blank and the call dropped
      6 s in. Cause: `useEffect(() => onTranscript(lines))` returned the array, which React
      took as a cleanup function ("destroy is not a function") and unmounted the page. Stage 3
      was only ever tested with the Python caller. Fixed, error boundaries added, and checked
      in headless Chrome with a fake microphone (`--use-fake-device-for-media-stream`). The
      same call set off the worker-errors alarm: LiveKit's Rust side logs 3 ERRORs whenever
      the caller hangs up first; the alarm now ignores logger `livekit` Later: `domain = "carhaul.sergiovanegas.com"`
      and the 2 DNS records at Hostinger
- [ ] GitHub variables `DEPLOY_ENABLED`, `DISTRIBUTION_ID`, `SITE_URL`
- [ ] Check the worker stops itself on AWS after 10 idle minutes
- [ ] Share the link and TESTING_GUIDE with the teammate

Expected cost (about 40 calls in 10 sessions a month): worker ~5 h awake x $0.06 ≈ $0.30, ECR
storage (2 images per repo) ≈ $0.20, Lambda/DynamoDB/CloudFront/S3/logs/alarms within free
tiers or cents: **AWS ≈ $0.50-1/month**, ~$0 with no calls. Per call on top (rough): Deepgram
~$0.015 for 2 min, Groq < $0.001, ElevenLabs free up to ~10k characters a month, LiveKit free
tier, plus CarHauler's per-call price. Worst case if someone abuses `/api/wake`: 20 starts a
day x 10 min ≈ $6/month.

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
| AWS CLI profile `carhaul` | ✅ IAM user `carhaul-deployer`, account 816940506502 (same as `gym`), default VPC present |
| Twilio | ⏳ stage 9 |

## UI refresh (branch `ui-refresh-typing-sound`, 2026-11-09)

From Sergio's first real calls on the live site:

- [x] Keyboard typing (~2 s) between "give me one second" and the price (`main.before_quote`,
      `tools.get_quote` waits for it; checked in a scripted call: `get_quote` 4.6 s)
- [x] One conversation view (chat + inline tool calls, drops and latency behind "Show
      details") instead of chat + timeline; feedback form at the end of the conversation
- [x] One scroll: desktop page = screen height, only the conversation scrolls; phone = one
      column, page scroll only
- [x] Dark navy theme + dark mode (tokens in `frontend/src/index.css`). Second pass after
      Sergio found it too dark: one navy scale (50-950), dark mode on mid-navy surfaces
- [x] Scrolling: the conversation followed new lines with `scrollIntoView`, which also moved
      the page; now it scrolls only its own box and only while you're at the bottom
- [x] Numbers become words before the voice (`speech.py`, `Mia.tts_node`): prices, model
      years, ZIPs, other numbers
- [x] Mia ends the call herself: after the quote she asks "anything else?" and calls
      `end_call`; a goodbye line without `end_call` also hangs up once it's spoken
      (`guardrails.is_goodbye`; seen on Sergio's call: "...Otherwise, have a great day!" and
      no hang-up). Checked with a scripted call
- [x] Sergio: deployed and merged (#12)

## Voice picker (branch `voice-picker`, on top of the UI refresh, 2026-11-09)

- [x] `mia/voices.py`: 6 voices, 2 per provider (ElevenLabs flash v2.5: Mia's default and
      Jessica; Cartesia sonic-3: Courtney and Jessica; Deepgram Aura-2: Thalia and
      Andromeda), each at speed 0.92 (callers found Mia fast)
- [x] `GET /api/voices`; `/api/token` takes `{"voice": key}` (unknown → default) and passes it
      in the agent dispatch metadata; the worker builds that TTS. The keys are checked to match
      across agent and backend (`tests/test_voices.py`)
- [x] Call page dropdown "Mia's voice", remembered in the browser; the stats show the voice
- [x] `CARTESIA_API_KEY` in `.env`, `/carhaul/agent/` (set_aws_secrets) and the ECS task
- [x] Scripted call with `--voice cartesia-courtney` through `/api/token`: $724 quote, Mia hung
      up herself, voice first audio p50 155 ms in the call
- [x] Sergio: secrets (Cartesia key in SSM) and `scripts/deploy.sh`; merged (#13)

Time to first audio, one-off synthesis of "Your estimated cost is one thousand, one hundred
ninety-one dollars. Would you like me to connect you with Sergio?", 3 runs each, 2026-11-09
(in calls the voices stream, which is faster: Cartesia was 155 ms):

| Voice | TTFB p50 | Runs (ms) | Audio length |
| --- | --- | --- | --- |
| ElevenLabs · Mia (default) | 187 ms | 308, 187, 185 | 6.7 s |
| ElevenLabs · Jessica | 177 ms | 177, 177, 182 | 6.1 s |
| Cartesia · Courtney | 406 ms | 474, 406, 149 | 5.8 s |
| Cartesia · Jessica | 288 ms | 280, 288, 330 | 6.2 s |
| Deepgram · Thalia | 212 ms | 436, 181, 212 | 7.1 s |
| Deepgram · Andromeda | 184 ms | 176, 207, 184 | 7.1 s |

## Voices, second pass (branch `voices-american`, 2026-11-09)

Sergio's feedback: voices too slow, American voices only, Cartesia first, say what each voice is.

- [x] 6 American voices, picked from the providers' catalogs (accent metadata / descriptions):
      Cartesia Skylar (first, the default) and Morgan; ElevenLabs Sarah and Jessica (premade,
      work on the free plan); Deepgram Thalia and Athena. Out: ElevenLabs "Mia" (accent unknown),
      Cartesia Courtney and Jessica (no accent listed), Deepgram Andromeda (casual)
- [x] Normal pace again (no speed setting)
- [x] A one-line description under the dropdown (accent, style, provider model); the page
      starts on the first voice and doesn't call it "default"; a remembered old key falls back
      to Skylar
- [x] Checked in headless Chrome with a fake mic against the Docker stack: description shown,
      the call greets in Skylar's voice, no console errors
- [ ] Sergio: `scripts/deploy.sh` and try them

Same line as before, 3 runs each, 2026-11-09. Audio length shows the pace (lower = faster);
the old voices took 6.1-7.1 s at speed 0.92:

| Voice | TTFB p50 | Runs (ms) | Audio length |
| --- | --- | --- | --- |
| Cartesia · Skylar | 288 ms | 307, 288, 148 | 5.7 s |
| Cartesia · Morgan | 282 ms | 282, 356, 155 | 7.3 s |
| ElevenLabs · Sarah | 192 ms | 340, 192, 188 | 5.9 s |
| ElevenLabs · Jessica | 207 ms | 207, 208, 189 | 5.9 s |
| Deepgram · Thalia | 218 ms | 376, 194, 218 | 6.3 s |
| Deepgram · Athena | 225 ms | 225, 208, 255 | 6.3 s |

Cartesia Iris (also American, customer care) was 7.3 s too, so that slower pace is how those
Cartesia voices talk, not a setting; Skylar is the quickest of the six.

## Call page polish (branch `call-page-polish`, 2026-11-09)

Sergio's feedback: a progress bar while Mia wakes up; the palette still too dark, make it more
professional (McKinsey-like colors).

- [x] `/api/wake` adds `step` (`server` / `loading`, from the ECS task's `lastStatus`); the page
      shows a progress bar with the step and seconds (`lib/wake.ts`: time-based inside the
      step, capped at 95% until ready)
- [x] New palette tokens in `index.css`: white/cool grey, deep blue ink, electric blue buttons,
      cyan highlights; serif title. Light by default even when the OS is dark; "Dark mode"
      toggle in the header (deep-blue surfaces), remembered, applied before the first paint
- [x] Checked in headless Chrome (OS in dark mode, fake mic, `/api/wake` faked to show both
      steps): progress bar, a live call in light and dark, phone width, choice kept on reload,
      no console errors
- [ ] Sergio: `scripts/deploy.sh` (code only; the Lambda gets the new `step`) and look at the
      wake-up on AWS, where the steps are real

## Stage 9: transfer to a licensed representative (branch `stage-9-transfer`, 2026-11-09)

Sergio's feedback: transfers should ring his real phone, as cheaply as possible; Mia shouldn't
say "Sergio, who built this" (sounds arrogant) but "a licensed representative who can assist
you further"; the page should disclose that transfers go to him.

How we chose the carrier (2026-11-09): LiveKit's own numbers are inbound only for now, so the
call out needs a SIP trunk; LiveKit's free plan includes 1,000 third-party SIP minutes. Twilio
(upgraded, $20 prepaid credit, ~1 cent a minute, **no Twilio number**: caller ID is a verified
number) won over a $0 push-and-join-link (no real ring) and VoIP.ms. Twilio blocked trunk
creation until the account passed Trust Hub (KYC). Calling Sergio *from his own number* went
straight to his voicemail (answered in 1.7 s), so the caller ID is another verified number.

- [x] `scripts/setup_twilio_trunk.py`: trunk `carhaul-mia` (`*.pstn.twilio.com`), credential
      list, verified caller ID, `.env` values; idempotent, prints no secrets
- [x] `mia/transfer.py`: settings, inline trunk per call (no LiveKit trunk ID; the SDK's
      `outbound_trunk_config=` helper is broken in livekit-api 1.x), dial tone for the caller,
      30 s ringing, 10 min on the phone, 5 transfers a day (DynamoDB counter), handoff line
- [x] `request_human` starts the transfer after Mia's "connecting you" line; guardrail: only
      when the caller asked for a person or said yes right after Mia's offer (it rings a real
      phone, and gpt-oss invents tool calls)
- [x] Mia leaves after introducing the caller; the room now ends when either of them hangs up
      (`delete_room_on_close=False` + the worker deletes it); no answer → Mia apologizes
- [x] "a licensed representative who can assist you further" everywhere Mia speaks; a test
      checks she never names Sergio. Disclosure under the page title
- [x] Secrets in `set_aws_secrets.py` and the ECS task; task role gets `dynamodb:UpdateItem`.
      `terraform plan`: task definition replaced, 2 policies updated
- [x] Live test with the local worker (scripted caller: "can I talk to a real person?"): Mia's
      line, Sergio's phone answered after 5.4 s, handoff line, Mia left, room closed when the
      caller left, record `transfer: connected`
- [ ] Sergio: `set_aws_secrets.py`, `terraform apply`, `scripts/deploy.sh`; one transfer on AWS

Seen in that test: the first job process after a container restart crashed (exit code -11)
right after joining, and LiveKit re-dispatched the call (31 s to the greeting). Not reproduced
in 2 more calls; watch for it.

## Past calls and the sidebar (branch `call-history`, on top of stage 9, 2026-11-09)

Sergio's feedback: he can't see how previous calls went; tabs or a sidebar to switch views;
after a call the stats panel's scrollbar grew and scrolled into empty space.

- [x] `GET /api/calls` (latest 50, newest first) and `GET /api/calls/{room}` (record +
      feedback); public on purpose, 600 reads per IP an hour, unknown rooms 404
- [x] Sidebar on desktop (collapsible to icons, remembered), tabs on a phone; views in the URL
      hash (`#/calls/<room>` links to one call). The call view stays mounted, so opening Past
      calls during a call doesn't drop it (checked)
- [x] Past calls: list (when, length, outcome, quote) and the call: the same conversation
      (with "Show details": tool calls, JSON, drops, latency) and stats as a live call, plus
      the caller's rating; records without events fall back to the transcript
- [x] Scroll: the stats card now fills its column and only its contents scroll; measured in
      Chrome at 1400x900 after a call: nothing overflows (before: 6 px of blank scroll)
- [x] Checked in headless Chrome against the Docker stack: during and after a call, the
      transfer test call with details, collapsed sidebar, phone list and detail, no errors
- [x] Aggregate stats: the Stats view (next section)

## Stats view, graphite dark mode, intro popup (branch `stats-dashboard`, 2026-11-10)

Sergio's feedback: stats should tell a story, most important KPIs first; a funnel (call →
cities → vehicles → quote → transfer) with conversion rates over time; transfers are the
key KPI (qualified leads); total and average time on calls is time saved for the business;
dark mode still felt off (light mode loved); the intro and disclosure as a popup that closes
itself; make it a better experience.

- [x] `GET /api/stats`: per call `route`, `vehicles`, `quoted`, `transfer`, `mia_s` (until the
      handoff), `test`; written by the worker on new calls (`records.stats_facts`), backfilled
      from the record for older rows (once; 50 per request). A test keeps the worker's and
      the API's code identical
- [x] Stats view: story sentence, KPI row (hero: transfers + rate; calls; time handled by
      Mia total + average; quotes; response time), funnel with share of calls and step
      conversion, calls/transfers per day, small multiples of each step's share per day, a
      table view, range 7 / 30 days / all time, test calls toggle. Ordinal ramp validated
      (light end 2.11:1 on white, 2.16:1 on the dark surface)
- [x] Dark mode: graphite tokens (ink 14.9:1, muted 7.2:1, white on brand 4.6:1)
- [x] Intro popup (once per session, 15 s, pauses on hover/keys); header shortened; "About &
      disclosure" reopens it
- [x] UX: an example sentence on the call card; after a call "See this call in Past calls"
      (retries while the record saves); Past calls hides test calls unless asked
- [x] Checked in headless Chrome: real local data and a synthetic 30-day set (served only to
      the test browser), tooltips, dark mode, phone, popup auto-close; no console errors
- [ ] Sergio: deploy (`scripts/deploy.sh`; no Terraform or secrets) and look at real numbers

## Dispositions, all-time stats, credits (branch `dispositions-and-credits`, 2026-11-10)

- [x] Stats: all time only; the over-time charts and table are gone (calls come in bursts)
- [x] Dispositions (`stats_v` 2, all rows recomputed once): organic / requested / forced
      transfer (qualified leads), hung up on hold, hung up, not interested. The worker records
      `transfer_kind` and `escalated`; old records are inferred. Shown as two groups of ranked
      bars (leads in blue, the rest gray)
- [x] Credits: Sergio Vanegas and Belinda Hu (LinkedIn), CarHauler247 public API, academic and
      non-commercial, GitHub repo; in the About popup and the sidebar footer
- [x] Checked in Chrome (real local data: the transfer test call is a requested transfer;
      synthetic set; phone width), no console errors

## Ideas / later

- **Self-corrections:** "it's twenty ten... twenty twenty Toyota" was saved as 2010 (Sergio's
  call, 2026-11-09): the last value the caller says should win (stage 8).
- **Silence after "anything else?":** if the caller says nothing, Mia waits; LiveKit marks
  the user away after 15 s. Say goodbye and hang up then (stage 8).

- **Voice picker, next:** compare cost per character per provider, and the voices' latency
  in real calls (the call records keep `tts_node_ttfb` and the config event names the voice).

- `happy_path_ngc_3v` is flaky in CI (seen once on 2026-11-09: the 3rd vehicle not saved on turn 5); 10/10 locally on the branch and on main's prompt. Track its pass rate in the stage 7 simulations.

- Agent image is 1.57 GB (onnxruntime, local turn model); slim it for ECS if pulls are slow.
- Silent caller: LiveKit marks the user "away" after 15 s; Mia could ask "are you still there?" (stage 8).
- Frontend bundle is 811 kB (LiveKit client); code-split when the dashboard arrives.

- Compare `openai/gpt-oss-20b` vs `openai/gpt-oss-120b` with the simulation report.
- Ambiguous-city detection from geocoding, so Mia only confirms the state when needed.
