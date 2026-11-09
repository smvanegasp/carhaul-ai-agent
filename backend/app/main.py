import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import calls, db, livekit_token, ssm
from app.config import on_aws, origin_secret


@asynccontextmanager
async def lifespan(_: FastAPI):
    ssm.load_parameters()
    if os.environ.get("AUTO_CREATE_TABLE") == "1":  # docker compose (DynamoDB Local)
        db.create_table_if_missing()
    yield


app = FastAPI(
    title="CarHaul Mia API",
    # Interactive API docs locally only; on AWS they would just map the API for strangers.
    docs_url=None if on_aws() else "/api/docs",
    openapi_url=None if on_aws() else "/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(livekit_token.router)
app.include_router(calls.router)


@app.middleware("http")
async def require_cloudfront(request: Request, call_next):
    """On AWS only CloudFront may call the API (it sends the shared X-Origin-Verify secret)."""
    expected = origin_secret()
    if expected and not hmac.compare_digest(
        request.headers.get("x-origin-verify", "").encode(), expected.encode()
    ):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
