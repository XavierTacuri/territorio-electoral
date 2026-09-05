import json
import logging
from collections import Counter
from contextvars import ContextVar
from threading import Lock
from time import perf_counter
from typing import Any

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
request_metrics: Counter[tuple[str, str, int]] = Counter()
request_duration_ms: Counter[tuple[str, str]] = Counter()
_metrics_lock = Lock()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_context.get()),
            "message": record.getMessage(),
        }
        for key in ("method", "path", "status_code", "duration_ms", "user_id", "organization_id", "campaign_id", "error_type", "provider", "intent"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def observe_request(method: str, path: str, status_code: int, duration: float) -> None:
    route = path if path in {"/api/v1/health", "/api/v1/ready", "/api/v1/metrics"} else "application"
    with _metrics_lock:
        request_metrics[(method, route, status_code)] += 1
        request_duration_ms[(method, route)] += round(duration * 1000)


def prometheus_metrics() -> str:
    lines = ["# HELP territorio_http_requests_total Solicitudes HTTP.", "# TYPE territorio_http_requests_total counter"]
    with _metrics_lock:
        for (method, route, status), value in sorted(request_metrics.items()):
            lines.append(f'territorio_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {value}')
        lines.extend(("# HELP territorio_http_request_duration_milliseconds_total Duracion HTTP acumulada.", "# TYPE territorio_http_request_duration_milliseconds_total counter"))
        for (method, route), value in sorted(request_duration_ms.items()):
            lines.append(f'territorio_http_request_duration_milliseconds_total{{method="{method}",route="{route}"}} {value}')
    return "\n".join(lines) + "\n"
