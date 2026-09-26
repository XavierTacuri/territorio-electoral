import logging
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.router import api_router
from app.core.config import settings
from app.core.observability import configure_logging, observe_request, prometheus_metrics, request_id_context
from app.schemas.health import RootResponse

configure_logging()
logger = logging.getLogger("territorio.http")
if settings.app_env.lower() == "production" and settings.artifact_storage_provider == "local":
    # Not a hard failure — Render staging runs APP_ENV=production today with
    # local storage and must keep working (§5 Fase 4A). An AWS production
    # deployment MUST set ARTIFACT_STORAGE_PROVIDER=s3 (see
    # docs/aws/PRODUCTION_ARCHITECTURE.md) since local storage does not
    # survive a redeploy or a second instance; this only makes that gap
    # observable instead of silent.
    logging.getLogger("territorio.storage").warning("artifact_storage_local_in_production")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fase 4B §20: graceful shutdown for ECS SIGTERM. Uvicorn/Gunicorn
    # already stop accepting new connections and let in-flight requests
    # finish (their own --timeout-graceful-shutdown / stop timeout, not
    # reimplemented here — see docs/aws/PRODUCTION_ARCHITECTURE.md for the
    # recommended value); this hook's only job is what only the app itself
    # can do: dispose the SQLAlchemy pool so every checked-out connection is
    # returned/closed cleanly instead of dropped when the process exits.
    # Nothing here can lose an already-confirmed commit — disposal happens
    # strictly after in-flight requests (and their commits) have completed.
    yield
    from app.db.session import engine

    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)

_HEALTH_CHECK_PATH = f"{settings.api_v1_prefix}/health"


class _HealthCheckHostExemptMiddleware:
    """Exceptua UNICAMENTE `GET {api_v1_prefix}/health` (path exacto, sin
    trailing slash, sin distinguir metodo != GET) de la validacion de Host
    que hace `starlette.middleware.trustedhost.TrustedHostMiddleware` para
    el resto de la aplicacion.

    Por que existe: los health checks de un target group de ALB con
    target_type=ip (ver infra/terraform/modules/alb) llegan con el header
    Host igual a la IP privada de la task ECS, nunca el dominio real ni el
    DNS del ALB configurados en trusted_hosts — comportamiento documentado
    de AWS, el mismo problema conocido de Django ALLOWED_HOSTS con ELB. Sin
    esta excepcion, TrustedHostMiddleware devolveria 400 a cada probe del
    ALB y el target group nunca marcaria una task como healthy, sin
    importar si trusted_hosts contiene un dominio real o el DNS del ALB.

    Por que NO debilita TrustedHostMiddleware: reutiliza la clase REAL de
    Starlette (sin reimplementar su logica de matching a mano, evitando
    divergencia silenciosa) para TODO lo que no sea esta unica excepcion —
    incluye conexiones websocket (aunque esta aplicacion no expone ninguna
    hoy) y el comportamiento www_redirect original. La excepcion en si NO
    es un atajo que devuelva 200 sin mas: delega en `self._passthrough_app`,
    que es la MISMA cadena ASGI interna (router incluido) que ejecuta
    `health_check()` (backend/app/api/routes/health.py) de verdad — un
    fallo real de la aplicacion (p. ej. un error de arranque) seguiria
    devolviendo un error real, no un 200 falso.

    Por que la condicion es (metodo, path) exactos y NO User-Agent: el
    header User-Agent es trivialmente falsificable por cualquier cliente,
    asi que nunca deberia ser la unica puerta de una excepcion de
    seguridad — y aqui ademas no aporta nada: el endpoint expuesto no tiene
    efectos secundarios ni datos sensibles (siempre devuelve el mismo "ok"
    a cualquier cliente con un Host confiable), asi que restringir ademas
    por el User-Agent real de ALB (`ELB-HealthChecker/2.0`) anadiria
    fragilidad (AWS podria cambiar ese string sin aviso, rompiendo health
    checks reales en silencio) sin reducir ningun riesgo real. El metodo
    GET (unico que ALB usa para health checks HTTP/HTTPS) y el path exacto
    ya cierran cualquier superficie de bypass util: un trailing slash
    (`/health/`), un query string (`?x=1`, que Starlette separa de
    `scope["path"]` y por tanto no rompe la igualdad exacta), o un metodo
    distinto (POST/DELETE/...) NUNCA igualan `scope["path"] == exempt_path
    and scope["method"] == "GET"` simultaneamente y por tanto siguen
    pasando por la validacion de Host normal, sin excepcion.
    """

    def __init__(self, app: ASGIApp, *, exempt_path: str, allowed_hosts: list[str]) -> None:
        self._exempt_path = exempt_path
        self._passthrough_app = app
        self._trusted_host_app = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == self._exempt_path:
            await self._passthrough_app(scope, receive, send)
            return
        await self._trusted_host_app(scope, receive, send)


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(_HealthCheckHostExemptMiddleware, exempt_path=_HEALTH_CHECK_PATH, allowed_hosts=settings.trusted_host_list)
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
        logger.error("unexpected_request_error", extra={"method": request.method, "path": request.url.path}, exc_info=True)
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
