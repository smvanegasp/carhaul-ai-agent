# Mia: a voice AI agent for car-shipping quotes

An academic, non-commercial project by [Sergio Vanegas](https://www.linkedin.com/in/sergio-vanegas/)
and [Belinda Hu](https://www.linkedin.com/in/belinda-hu/). Prices come from the public API of
[CarHauler247](https://carhauler247.com/).

Call Mia from your browser, tell her where your car is going and what it is, and she gives you
an open car-shipping quote from the [CarHauler247](https://carhauler247.com/) API. While you
talk, a live panel shows the transcript, every tool call (with its JSON) and how long each part
of the pipeline took. **Past calls** shows every saved call the same way (conversation, tool
calls, latency), and **Stats** tells the story: transfers to a licensed representative
(qualified leads), time handled by Mia, and the funnel from call to transfer over time.

> Status: live on AWS (stages 0-5). The public dashboard, harder conversations and a phone
> line are coming in stages (see [docs/BACKLOG.md](docs/BACKLOG.md)).

## Stack

| Part | Choice |
| --- | --- |
| Real-time audio | LiveKit Cloud (WebRTC); SIP out through a Twilio trunk to transfer callers to a person |
| Speech-to-text | Deepgram nova-3 |
| LLM | Groq, `openai/gpt-oss-20b` |
| Text-to-speech | The caller picks one of 6 American voices: Cartesia sonic-3 (Skylar, the first choice), ElevenLabs flash v2.5 or Deepgram Aura-2, two each |
| Turn taking | Silero VAD, LiveKit turn detector, interruptions (caller can talk over Mia) |
| Agent | Python 3.12, `livekit-agents` 1.8, uv |
| API | FastAPI on AWS Lambda (container image), DynamoDB |
| Web | React, Vite, Tailwind |
| Infra | Docker, Terraform, ECS Fargate (agent worker), CloudFront, GitHub Actions with OIDC |

## Guardrails

The LLM decides what to ask; code decides what's true.

- **Prices are computed by code** and read word for word; the model never does arithmetic.
- **Grounding:** a tool call may only save a city, year, make or model the caller actually said
  (typo and nickname tolerant). In testing, `gpt-oss-20b` answered "Yeah, sure" by saving
  "Los Angeles" as the origin every time; those calls are now dropped before they run.
- **No quote without a yes:** the quote runs only right after the caller confirms the read-back.
- **One question at a time:** repeated sentences and extra questions are trimmed before speech.
- **API failures** are retried (3 attempts, exponential backoff), then escalated to a person.

## How a call works

```
Browser ──POST /api/token──► API: rate limit, new room "call-<id>", token that dispatches "mia"
   │ WebRTC (mic + Mia's voice, transcripts)
   ▼
LiveKit Cloud ◄──► agent worker: Deepgram → Groq (+ guardrails, tools) → ElevenLabs
```

Each call gets its own room. Mia greets first, says "give me one second" while the quote is
computed, hangs up after her goodbye (the room is deleted, which ends the call in the browser)
and stops at 6 minutes. If the caller asks for a person, Mia dials a licensed representative's
phone into the same room (Twilio Elastic SIP trunk), introduces the caller and leaves; a
guardrail makes sure only the caller's own request can trigger that real phone call. Calls are rate limited per IP and per day: every call costs money.

**On AWS** (Terraform in `infra/`), built to cost about $1 a month: CloudFront serves the web
app from S3 and forwards `/api` to FastAPI on Lambda. The voice worker is an **on-demand** ECS
Fargate task: opening the call page wakes it (about a minute), and it shuts itself down after
10 idle minutes, so an unused site costs almost nothing. It only connects out (no load
balancer, no NAT). Calls, feedback and rate-limit counters live in one DynamoDB table; secrets
come from SSM.
Merging to `main` deploys through GitHub Actions with OIDC (no AWS keys in GitHub). Alarms email
when the API errors, the worker can't start or logs errors, or a call record isn't saved.

**Live panel.** The worker publishes what it does as events on the room (topic `mia.events`):
each turn with its latency (end of turn, speech to text, LLM first token, voice first audio,
total), each tool call with its arguments, the JSON the LLM got back and its duration, every
call the guardrail dropped, and what's on file. The call page shows one conversation (the
live transcript, with the tool calls and latency inline behind "Show details") next to the
call's stats, keeps it afterwards, and ends with a feedback form. When the call ends the worker saves the whole
record (state, transcript, events, latency, talk time, interruptions) to DynamoDB; feedback is
saved next to it. The dashboard (stage 6) reads those records.

**Latency** (6 scripted voice calls, 2026-11-09, `python -m mia.smoke`): per call, the median
time from the caller's last word to Mia starting to answer was 0.95-1.6 s on the server (end of
turn ~0.58 s, LLM first token ~0.3 s, TTS first audio ~0.17 s, plus tool time) and 1.1-1.8 s as
heard by the caller. Slow outliers (2.5-4 s) came from the turn detector waiting out a pause
mid-sentence and, once, a 3 s Groq response.

## How it's tested

1. Unit tests for every tool, including typos and API failures.
2. Scenario tests: reference conversations replayed in text against the real LLM, checking the
   tool calls (an LLM judge checks the wording). The model isn't deterministic, so CI retries a
   failed scenario twice; pass rates come from the simulations (4).
3. Voice smoke test: a scripted caller (a different TTS voice) phones Mia through LiveKit and
   checks the whole call end to end, with timings.
4. AI-vs-AI simulation: 8 caller personas (generous or not, complete or partial, verbose or not)
   x 9 paths (happy, questions, changes, a person, off-topic), a model playing the caller and
   code scoring every call against its ground truth. It runs every night and **every run's
   transcripts are kept** in [agent/evals/simulations/](agent/evals/simulations/README.md).
5. Human testing with per-call feedback.

## Run locally

See [AGENTS.md](AGENTS.md#4-run-and-test).

## License

MIT
