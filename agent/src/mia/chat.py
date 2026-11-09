"""Talk to Mia by typing (no audio, no LiveKit server): ``uv run python -m mia.chat``.

Uses the real Groq model, Google Maps and CarHauler APIs from the repo-root .env, and prints
every tool call with its arguments and result. Type ``/state`` for the full call state,
``/quit`` to leave.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import FunctionCall, FunctionCallOutput
from livekit.agents.llm import ChatMessage

from mia.agent import Mia, make_llm, new_session
from mia.carhauler import CarHaulerClient
from mia.state import QuoteSession
from mia.tools import Services
from mia.vehicles import VehicleResolver

DIM, CYAN, YELLOW, RESET = "\033[2m", "\033[36m", "\033[33m", "\033[0m"


def _print_events(events) -> None:
    for ev in events:
        item = ev.item
        if isinstance(item, FunctionCall):
            print(f"{YELLOW}  → {item.name}({item.arguments}){RESET}")
        elif isinstance(item, FunctionCallOutput):
            try:
                pretty = json.dumps(json.loads(item.output), indent=2)
            except (TypeError, ValueError):
                pretty = item.output
            print(DIM + "\n".join("    " + line for line in pretty.splitlines()) + RESET)
        elif isinstance(item, ChatMessage) and item.role == "assistant":
            print(f"{CYAN}Mia:{RESET} {item.text_content}")


async def main(model: str | None) -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    client = CarHaulerClient()
    services = Services(carhauler=client, resolver=VehicleResolver(client))
    state = QuoteSession()
    llm = make_llm(model)
    agent = Mia(services)
    print(f"{DIM}model: {llm.model}  (/state, /quit){RESET}")
    print(f"{CYAN}Mia:{RESET} {agent.greeting}")
    async with new_session(state, llm) as session:
        await session.start(agent)
        while True:
            try:
                text = await asyncio.to_thread(input, "You: ")
            except (EOFError, KeyboardInterrupt):
                break
            if text.strip() in ("/quit", "/q"):
                break
            if text.strip() == "/state":
                print(json.dumps(state.to_record(), indent=2, default=str))
                continue
            if not text.strip():
                continue
            dropped_before = len(state.dropped_calls)
            result = await session.run(user_input=text)
            for d in state.dropped_calls[dropped_before:]:
                print(f"{DIM}  x guardrail dropped {d['tool']}({d['args']}): {d['why']}{RESET}")
            _print_events(result.events)
            if state.ended:
                break
    await client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Groq model, default openai/gpt-oss-20b")
    asyncio.run(main(parser.parse_args().model))
