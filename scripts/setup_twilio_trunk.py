"""Set up the Twilio SIP trunk Mia dials Sergio through (stage 9 transfer). Safe to re-run.

Run from the repo root:  cd agent && uv run python ../scripts/setup_twilio_trunk.py

Reads from the repo-root .env (an API key is enough; it can be deleted after setup):
    TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TRANSFER_PHONE_NUMBER

Then, reusing whatever already exists instead of duplicating it:
1. the Elastic SIP trunk "carhaul-mia" with a ``*.pstn.twilio.com`` address
2. the credential list "livekit" with user "mia-livekit" (password generated here), attached
   to the trunk: LiveKit authenticates with it when it dials out
3. TRANSFER_PHONE_NUMBER as a verified caller ID: Mia calls Sergio *from* his own number, so no
   Twilio number (and no monthly fee) is needed. If it isn't verified yet, Twilio calls the
   phone and Sergio types the 6-digit code this script shows
4. writes TWILIO_SIP_ADDRESS, TWILIO_SIP_USERNAME and TWILIO_SIP_PASSWORD into .env

Nothing secret is printed, and the phone number is masked.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

TRUNK_NAME = "carhaul-mia"
CREDENTIAL_LIST_NAME = "livekit"
SIP_USERNAME = "mia-livekit"

TRUNKING = "https://trunking.twilio.com/v1"
API = "https://api.twilio.com/2010-04-01"


def mask(number: str) -> str:
    return number[:2] + "*" * max(0, len(number) - 6) + number[-4:]


def new_password() -> str:
    # Twilio: at least 12 characters, upper and lower case and a digit.
    return "Mia" + secrets.token_hex(12) + "7"


def update_env(values: dict[str, str]) -> None:
    """Set these keys in .env, keeping every other line as it is (written via a temp file)."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    left = dict(values)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in left and not line.lstrip().startswith("#"):
            out.append(f"{key}={left.pop(key)}")
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in left.items()]
    tmp = ENV_FILE.with_name(".env.tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_FILE)


class Twilio:
    def __init__(self, account: str, key: str, secret: str):
        self.account = account
        self.http = httpx.Client(auth=(key, secret), timeout=30)

    def call(self, method: str, url: str, **data: str) -> dict:
        res = self.http.request(method, url, data=data or None)
        if res.status_code >= 400:
            body = res.json() if "json" in res.headers.get("content-type", "") else {}
            raise TwilioError(res.status_code, body.get("code"), body.get("message", res.text))
        return res.json() if res.content else {}

    def acct(self, path: str) -> str:
        return f"{API}/Accounts/{self.account}/{path}"


class TwilioError(Exception):
    def __init__(self, status: int, code: int | None, message: str):
        super().__init__(f"HTTP {status} (Twilio code {code}): {message}")
        self.status, self.code = status, code


def ensure_trunk(tw: Twilio) -> dict:
    trunks = tw.call("GET", f"{TRUNKING}/Trunks?PageSize=100")["trunks"]
    for t in trunks:
        if t["friendly_name"] == TRUNK_NAME:
            if t.get("domain_name"):
                print(f"Trunk: reusing {TRUNK_NAME} ({t['domain_name']})")
                return t
            return set_domain(tw, t)
    print(f"Trunk: creating {TRUNK_NAME}")
    return set_domain(tw, tw.call("POST", f"{TRUNKING}/Trunks", FriendlyName=TRUNK_NAME))


def set_domain(tw: Twilio, trunk: dict) -> dict:
    """Give the trunk a *.pstn.twilio.com address, trying variants if the name is taken."""
    candidates = [TRUNK_NAME, f"{TRUNK_NAME}-sergio"] + [
        f"{TRUNK_NAME}-{secrets.token_hex(3)}" for _ in range(3)
    ]
    for name in candidates:
        domain = f"{name}.pstn.twilio.com"
        try:
            trunk = tw.call("POST", f"{TRUNKING}/Trunks/{trunk['sid']}", DomainName=domain)
            print(f"Trunk: address {domain}")
            return trunk
        except TwilioError as err:
            print(f"Trunk: {domain} not available ({err})")
    sys.exit("Couldn't give the trunk an address; see the errors above.")


def ensure_credentials(tw: Twilio, trunk: dict, password: str | None) -> str:
    """The "livekit" credential list with SIP_USERNAME, attached to the trunk. Returns the
    password in use (the one in .env if the credential already exists with it)."""
    lists = tw.call("GET", tw.acct("SIP/CredentialLists.json?PageSize=100"))["credential_lists"]
    cl = next((c for c in lists if c["friendly_name"] == CREDENTIAL_LIST_NAME), None)
    if cl is None:
        print(f"Credential list: creating {CREDENTIAL_LIST_NAME}")
        cl = tw.call("POST", tw.acct("SIP/CredentialLists.json"), FriendlyName=CREDENTIAL_LIST_NAME)
    else:
        print(f"Credential list: reusing {CREDENTIAL_LIST_NAME}")

    creds_url = tw.acct(f"SIP/CredentialLists/{cl['sid']}/Credentials")
    creds = tw.call("GET", f"{creds_url}.json")["credentials"]
    existing = next((c for c in creds if c["username"] == SIP_USERNAME), None)
    if existing and password:
        print(f"Credential: {SIP_USERNAME} exists, keeping the password in .env")
    elif existing:
        password = new_password()
        tw.call("POST", f"{creds_url}/{existing['sid']}.json", Password=password)
        print(f"Credential: {SIP_USERNAME} exists, set a new password (none in .env)")
    else:
        password = password or new_password()
        tw.call("POST", f"{creds_url}.json", Username=SIP_USERNAME, Password=password)
        print(f"Credential: created {SIP_USERNAME}")

    attached = tw.call("GET", f"{TRUNKING}/Trunks/{trunk['sid']}/CredentialLists")
    if any(c["sid"] == cl["sid"] for c in attached["credential_lists"]):
        print("Trunk: credential list already attached")
    else:
        tw.call(
            "POST", f"{TRUNKING}/Trunks/{trunk['sid']}/CredentialLists", CredentialListSid=cl["sid"]
        )
        print("Trunk: credential list attached")
    return password


def ensure_caller_id(tw: Twilio, number: str) -> None:
    def verified() -> bool:
        url = tw.acct(f"OutgoingCallerIds.json?PhoneNumber={number.replace('+', '%2B')}")
        return bool(tw.call("GET", url)["outgoing_caller_ids"])

    def owned() -> bool:
        url = tw.acct(f"IncomingPhoneNumbers.json?PhoneNumber={number.replace('+', '%2B')}")
        return bool(tw.call("GET", url)["incoming_phone_numbers"])

    if verified() or owned():
        print(f"Caller ID: {mask(number)} is verified")
        return
    req = tw.call(
        "POST", tw.acct("OutgoingCallerIds.json"), PhoneNumber=number, FriendlyName="Sergio"
    )
    print(
        f"\nCaller ID: Twilio is calling {mask(number)} now. Answer and type this code on the "
        f"keypad:  {req['validation_code']}\n"
    )
    for _ in range(40):  # ~2 minutes
        time.sleep(3)
        if verified():
            print("Caller ID: verified")
            return
    sys.exit("Caller ID: not verified yet. Re-run the script to try again.")


def main() -> None:
    env = {**dotenv_values(ENV_FILE), **os.environ}
    needed = ["TWILIO_ACCOUNT_SID", "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET"]
    needed.append("TRANSFER_PHONE_NUMBER")
    missing = [k for k in needed if not env.get(k)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    number = env["TRANSFER_PHONE_NUMBER"].strip()
    if not (number.startswith("+1") and number[1:].isdigit() and len(number) == 12):
        sys.exit("TRANSFER_PHONE_NUMBER must look like +1 and 10 digits, no spaces or dashes.")

    tw = Twilio(env["TWILIO_ACCOUNT_SID"], env["TWILIO_API_KEY_SID"], env["TWILIO_API_KEY_SECRET"])
    trunk = ensure_trunk(tw)
    password = ensure_credentials(tw, trunk, env.get("TWILIO_SIP_PASSWORD"))
    update_env(
        {
            "TWILIO_SIP_ADDRESS": trunk["domain_name"],
            "TWILIO_SIP_USERNAME": SIP_USERNAME,
            "TWILIO_SIP_PASSWORD": password,
        }
    )
    print("Wrote TWILIO_SIP_ADDRESS, TWILIO_SIP_USERNAME, TWILIO_SIP_PASSWORD to .env")
    ensure_caller_id(tw, number)
    print("\nDone. LiveKit can now dial out through", trunk["domain_name"])


if __name__ == "__main__":
    try:
        main()
    except TwilioError as err:
        sys.exit(f"Twilio said: {err}")
