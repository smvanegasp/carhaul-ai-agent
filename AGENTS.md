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

## 2. How we work

- **Small stages, one branch and one PR each** (`stage-N-name`). Sergio merges; merging deploys
  (from stage 4).
- Tests and lint pass before a PR. Behavior changes to Mia come with a scenario test.
- The agent may run `terraform plan`; **`terraform apply` needs Sergio's OK.** CI never applies
  Terraform.
- Check `git status` before committing; never `git add -A` blindly.

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

### Repo map

| Path | What |
| --- | --- |
| `agent/` | uv project `mia-agent`, package `src/mia/`. `geo.py`: city → ZIP (Google Maps, typo-tolerant). Later: prompt, state, tools, CarHauler client, pricing, telemetry, evals |
| `backend/` | uv project `carhaul-api`: FastAPI for Lambda (`app/`). Later: LiveKit token, calls, stats, feedback |
| `frontend/` | React 19 + Vite + Tailwind v4. Later: call page with live panel, dashboard |
| `notebooks/` | Exploration only; kernel is `agent/.venv` (`uv sync --group notebooks`) |
| `docs/` | BACKLOG, CONVERSATION_DESIGN, TESTING_GUIDE (stage 4) |
| `infra/`, `scripts/` | Stage 4: Terraform and deploy/secrets scripts (copied from fit) |

## 4. Run and test

```sh
cd agent    && uv sync && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd backend  && uv sync && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd frontend && npm ci && npm test && npm run build
docker compose up        # api on :8020, web on :5190
```

- `uv run pytest -m live` (in `agent/`) runs tests that call **paid APIs** (Google Maps now,
  CarHauler and Groq later). They are deselected by default and never run in CI except where a
  stage says so explicitly. `tests/test_geo_accuracy.py` is about 100 Google calls.
- CI (`.github/workflows/ci.yml`): agent, backend, frontend, docker build, gitleaks.

## 5. Secrets and safety

- Local secrets live in the repo-root `.env` (git-ignored); names are in `.env.example`. On AWS
  they go to SSM Parameter Store under `/carhaul/` (stage 4, `scripts/set_aws_secrets.py`).
- **Never print, cat or echo secret values**; check only that a variable is set (or its length).
  Never ask Sergio to paste keys into chat. Never commit them; gitleaks runs in CI.
- Sergio's phone number (stage 9) goes only to SSM as `TRANSFER_PHONE_NUMBER`.
- The site is public and every call spends money (Groq, Deepgram, ElevenLabs, LiveKit): keep the
  token-endpoint rate limit, the daily call cap and the max call length.

## 6. Decisions log

- 2026-11-08: Browser calling first, phone (Twilio + LiveKit SIP) in stage 9. LiveKit **Cloud**,
  not self-hosted. Brand and persona: **Mia from F&F**. Teammate role: manual tester and
  feedback. Prices and the spoken quote summary are computed by code, never by the LLM.
