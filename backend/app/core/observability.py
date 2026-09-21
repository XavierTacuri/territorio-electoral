import json
import logging
import re
from collections import Counter
from contextvars import ContextVar
from threading import Lock
from time import perf_counter
from typing import Any

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
request_metrics: Counter[tuple[str, str, int]] = Counter()
request_duration_ms: Counter[tuple[str, str]] = Counter()
event_metrics: Counter[str] = Counter()
_metrics_lock = Lock()

# §14/§15 Fase 4B: centralized redaction — never rely on call sites
# remembering not to log something sensitive. Two independent layers:
# JsonFormatter's fixed field whitelist below (a key not in that list is
# simply never serialized, regardless of what a caller passes via `extra=`)
# and this filter, which additionally scrubs any `extra` key that LOOKS
# sensitive (defense-in-depth against a future whitelist entry) and any
# secret-shaped substring inside the log message itself (a raw f-string a
# call site wrote directly into `logger.info(...)` rather than via `extra=`).
_SENSITIVE_KEY_PATTERN = re.compile(r"token|authorization|cookie|password|secret|presigned|signature|database_url", re.IGNORECASE)
_LOG_RECORD_RESERVED_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text",
    "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "getMessage",
})
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT-shaped
    re.compile(r"[?&]X-Amz-Signature=[^&\s]+", re.IGNORECASE),
    re.compile(r"[?&]X-Amz-Credential=[^&\s]+", re.IGNORECASE),
    re.compile(r"postgresql(\+\w+)?://[^\s]+", re.IGNORECASE),
)


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__.keys()):
            if key in _LOG_RECORD_RESERVED_ATTRS:
                continue
            if _SENSITIVE_KEY_PATTERN.search(key):
                setattr(record, key, "[REDACTED]")
        message = record.getMessage()
        redacted = message
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_context.get()),
            "message": record.getMessage(),
        }
        for key in ("method", "path", "status_code", "duration_ms", "user_id", "organization_id", "campaign_id", "error_type", "provider", "intent", "operation_id", "act_id", "revision_id", "size_bytes", "mime_type", "outcome"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SensitiveDataFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def observe_request(method: str, path: str, status_code: int, duration: float) -> None:
    route = path if path in {"/api/v1/health", "/api/v1/ready", "/api/v1/metrics"} else "application"
    with _metrics_lock:
        request_metrics[(method, route, status_code)] += 1
        request_duration_ms[(method, route)] += round(duration * 1000)
    if status_code >= 500:
        record_event("http_requests_5xx_total")


def record_event(name: str) -> None:
    """Fase 4B §17: generic counter for election-day/artifact events (e.g.
    act_submit_total, artifact_upload_failure_total) — reuses the same
    process-local Counter + Prometheus text-exposition mechanism as the HTTP
    metrics above, no second metrics system. `name` must already be a safe,
    low-cardinality Prometheus-style counter name (no user/act/candidate
    identifiers — see call sites)."""
    with _metrics_lock:
        event_metrics[name] += 1


def prometheus_metrics() -> str:
    lines = ["# HELP territorio_http_requests_total Solicitudes HTTP.", "# TYPE territorio_http_requests_total counter"]
    with _metrics_lock:
        for (method, route, status), value in sorted(request_metrics.items()):
            lines.append(f'territorio_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {value}')
        lines.extend(("# HELP territorio_http_request_duration_milliseconds_total Duracion HTTP acumulada.", "# TYPE territorio_http_request_duration_milliseconds_total counter"))
        for (method, route), value in sorted(request_duration_ms.items()):
            lines.append(f'territorio_http_request_duration_milliseconds_total{{method="{method}",route="{route}"}} {value}')
        if event_metrics:
            lines.extend(("# HELP territorio_events_total Contadores operativos de Jornada Electoral/artifacts.", "# TYPE territorio_events_total counter"))
            for name, value in sorted(event_metrics.items()):
                lines.append(f'territorio_events_total{{event="{name}"}} {value}')
    return "\n".join(lines) + "\n"
