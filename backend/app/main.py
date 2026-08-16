import logging
import re
import time
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.observability import configure_logging, observe_request, prometheus_metrics, request_id_context
from app.schemas.health import RootResponse

configure_logging()
logger = logging.getLogger("territorio.http")
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
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied_id) else str(uuid4())
    request.state.request_id = request_id
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.error("unexpected_request_error", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse(
            status_code=500,
            content={"detail": f"Ha ocurrido un error inesperado. Código de referencia: {request_id}"},
        )
    duration = time.perf_counter() - started
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration * 1000:.2f}"
    if settings.secure_headers_enabled:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    observe_request(request.method, request.url.path, response.status_code, duration)
    logger.info("request_complete", extra={"method": request.method, "path": request.url.path,
        "status_code": response.status_code, "duration_ms": round(duration * 1000, 2)})
    request_id_context.reset(token)
    return response


@app.get(f"{settings.api_v1_prefix}/metrics", include_in_schema=False)
def metrics(request: Request):
    if not settings.metrics_enabled:
        return JSONResponse(status_code=404, content={"detail": "Recurso no disponible"})
    authorization = request.headers.get("Authorization", "")
    if authorization != f"Bearer {settings.metrics_token}":
        return JSONResponse(status_code=403, content={"detail": "Acceso no autorizado"})
    return PlainTextResponse(prometheus_metrics(), media_type="text/plain; version=0.0.4")


@app.get("/", response_model=RootResponse, tags=["root"])
def root() -> RootResponse:
    return RootResponse(name=settings.app_name, status="running")
