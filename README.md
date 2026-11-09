# Mia: a voice AI agent for car-shipping quotes

Call Mia from your browser, tell her where your car is going and what it is, and she gives you
an open car-shipping quote from the [CarHauler247](https://carhauler247.com/) API. While you
talk, a live panel shows the transcript, every tool call (with its JSON) and how long each part
of the pipeline took. A public dashboard shows how calls go overall.

> Status: early. The city → ZIP geocoding is built and tested; the agent, calling and dashboard
> are coming in stages (see [docs/BACKLOG.md](docs/BACKLOG.md)).

## Stack

| Part | Choice |
| --- | --- |
| Real-time audio | LiveKit Cloud (WebRTC; SIP for phone calls later) |
| Speech-to-text | Deepgram |
| LLM | Groq, `openai/gpt-oss-20b` |
| Text-to-speech | ElevenLabs |
| Agent | Python 3.12, `livekit-agents`, uv |
| API | FastAPI on AWS Lambda (container image), DynamoDB |
| Web | React, Vite, Tailwind |
| Infra | Docker, Terraform, ECS Fargate (agent worker), CloudFront, GitHub Actions with OIDC |

## How it's tested

1. Unit tests for every tool, including typos and API failures.
2. Scenario tests: reference conversations replayed in text, checking the tool calls.
3. AI-vs-AI simulation: 8 caller personas (generous or not, complete or partial, verbose or not)
   combined with conversation fragments, scored against ground truth.
4. Human testing with per-call feedback.

## Run locally

See [AGENTS.md](AGENTS.md#4-run-and-test).

## License

MIT
