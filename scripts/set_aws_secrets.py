"""Put the app's secrets in SSM Parameter Store for the AWS deployment.

Run from the repo root:  cd backend && uv run python ../scripts/set_aws_secrets.py

Values come from the repo-root .env (the same names as local development); anything missing
is asked for with a hidden prompt. Nothing secret is printed. Two paths, so each part reads
only what it needs:

- /carhaul/api/    the API (Lambda): the LiveKit key to mint call tokens
- /carhaul/agent/  the voice worker (ECS): LiveKit, Groq, Deepgram, ElevenLabs, Cartesia,
                   CarHauler, Google

Uses the "carhaul" AWS profile unless AWS_PROFILE is set. If the API is already deployed, it
is restarted so it reads the new values; the on-demand worker reads them at its next start.
"""

import getpass
import os
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "/carhaul/"
LIVEKIT = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
PARAMETERS = {
    "api": LIVEKIT,
    # Must match local.agent_secrets in infra/agent.tf.
    "agent": [
        *LIVEKIT,
        "GROQ_API_KEY",
        "DEEPGRAM_API_KEY",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_ID",
        "CARHAULER_API_KEY",
        "GOOGLE_MAPS_API_KEY",
        "CARTESIA_API_KEY",
    ],
}
# Local .env names that differ from the AWS ones.
ALIASES = {"CARHAULER_API_KEY": ["CARHAULER_API_KEY", "CARHAULER_API_KEY_QA"]}


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def value_for(name: str, env: dict[str, str]) -> str:
    for key in ALIASES.get(name, [name]):
        if env.get(key):
            return env[key]
    value = getpass.getpass(f"{name} (hidden): ").strip()
    if not value:
        sys.exit(f"{name} is empty; nothing saved.")
    return value


def main() -> None:
    session = boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE", "carhaul"), region_name="us-east-1"
    )
    ssm = session.client("ssm")
    env = read_env()

    values = {name: value_for(name, env) for name in dict.fromkeys(sum(PARAMETERS.values(), []))}
    for part, names in PARAMETERS.items():
        for name in names:
            ssm.put_parameter(
                Name=f"{PREFIX}{part}/{name}",
                Value=values[name],
                Type="SecureString",
                Overwrite=True,
            )
            print(f"Saved {PREFIX}{part}/{name}")

    # Lambda reads SSM at cold start: redeploying the same image replaces warm instances.
    lam = session.client("lambda")
    try:
        image = lam.get_function(FunctionName="carhaul-api")["Code"]["ImageUri"]
        lam.update_function_code(FunctionName="carhaul-api", ImageUri=image)
        print("Restarted the API so it picks up the new values.")
    except lam.exceptions.ResourceNotFoundException:
        pass


if __name__ == "__main__":
    main()
