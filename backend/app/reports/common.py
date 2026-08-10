from datetime import date
from decimal import Decimal
from typing import Any


def format_integer_es_ec(value: Any) -> str:
    if value is None:
        return "No disponible"
    return f"{int(value):,}".replace(",", ".")


def format_decimal_es_ec(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "No disponible"
    return f"{float(value):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_percent_es_ec(value: Any) -> str:
    return "No disponible" if value is None else f"{format_decimal_es_ec(float(value) * 100)} %"


def format_date_es_ec(value: Any) -> str:
    if value is None:
        return "No disponible"
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d/%m/%Y") if isinstance(value, date) else str(value)


def display_value(value: Any, kind: str | None = None) -> str:
    if isinstance(value, date): return format_date_es_ec(value)
    if kind == "integer": return format_integer_es_ec(value)
    if kind == "percent": return format_percent_es_ec(value)
    if kind == "decimal": return format_decimal_es_ec(value)
    if kind == "density": return "No disponible" if value is None else f"{format_decimal_es_ec(value)} hab./km²"
    if kind == "date": return format_date_es_ec(value)
    if value is None: return "No disponible"
    if isinstance(value, date): return format_date_es_ec(value)
    if isinstance(value, Decimal): return format_decimal_es_ec(value)
    if isinstance(value, (dict, list)): return str(value)
    return str(value)


def sanitize_excel_text(value: Any):
    if not isinstance(value, str): return value
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def visible_value(value: Any):
    return display_value(value)


def flatten_metrics(data: dict[str, Any]):
    rows = []
    for metric in data.get("metrics", []):
        if hasattr(metric, "model_dump"): metric = metric.model_dump()
        rows.append([metric.get("label", metric.get("code", "")), metric.get("value"), metric.get("unit", "")])
    return rows
