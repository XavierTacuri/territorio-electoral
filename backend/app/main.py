import time
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.schemas.health import RootResponse

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(CORSMiddleware, allow_origins=settings.frontend_origin_list,
    allow_credentials=True, allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"])


@app.middleware("http")
async def request_security(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    if settings.secure_headers_enabled:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


@app.get("/", response_model=RootResponse, tags=["root"])
def root() -> RootResponse:
    return RootResponse(name=settings.app_name, status="running")
