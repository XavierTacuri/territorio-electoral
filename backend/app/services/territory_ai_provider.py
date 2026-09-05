import json
from dataclasses import dataclass, field
from time import perf_counter

import httpx

from app.core.config import settings


class AiProviderError(RuntimeError):
    pass


class AiProviderAuthenticationError(AiProviderError):
    pass


class AiProviderRateLimitError(AiProviderError):
    pass


@dataclass
class ProviderResult:
    answer: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    citation_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    total_tokens: int | None = None
    latency_ms: int | None = None


class UnavailableAiProvider:
    name = "unavailable"
    available = False

    def generate(self, question, context):
        raise AiProviderError("Proveedor no configurado")

    def test_connection(self):
        raise AiProviderError("Proveedor no configurado")


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout: float | None = None, client: httpx.Client | None = None):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model if model is not None else settings.territory_ai_model
        self.timeout = timeout or settings.territory_ai_timeout_seconds
        self.available = bool(self.api_key and self.model)
        self.client = client

    def _request(self, payload: dict) -> tuple[dict, int]:
        if not self.available:
            raise AiProviderError("Proveedor no configurado")
        started = perf_counter()
        client = self.client or httpx.Client(timeout=self.timeout)
        close = self.client is None
        try:
            response = client.post("https://api.openai.com/v1/responses", json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
            if response.status_code in {401, 403}:
                raise AiProviderAuthenticationError("Credencial del proveedor no válida")
            if response.status_code == 429:
                raise AiProviderRateLimitError("Límite del proveedor alcanzado")
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise AiProviderError("Respuesta inválida del proveedor") from exc
            return data, round((perf_counter() - started) * 1000)
        except httpx.TimeoutException as exc:
            raise TimeoutError("El proveedor no respondió a tiempo") from exc
        except httpx.HTTPError as exc:
            raise AiProviderError("No fue posible conectar con el proveedor") from exc
        finally:
            if close:
                client.close()

    @staticmethod
    def _text(data: dict) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        return "".join(part.get("text", "") for item in data.get("output", [])
            for part in item.get("content", []) if part.get("type") == "output_text")

    def generate(self, question, context):
        instructions = context.get("system_prompt", "") + (
            "\nResponde exclusivamente como JSON con answer, citation_ids y limitations.")
        grounded_input = question
        if context.get("panorama_facts") is not None:
            grounded_input += "\n\nHechos autorizados ya extraídos (no recalcular):\n" + json.dumps(
                context["panorama_facts"], ensure_ascii=False, default=str)
        grounded_input += "\n\nEvidencia autorizada:\n" + json.dumps(
            context.get("documents", []), ensure_ascii=False, default=str)
        data, latency = self._request({"model": self.model, "instructions": instructions,
            "input": grounded_input, "text": {"format": {"type": "json_object"}}})
        try:
            structured = json.loads(self._text(data))
        except (TypeError, json.JSONDecodeError) as exc:
            raise AiProviderError("Respuesta inválida del proveedor") from exc
        if (not isinstance(structured, dict) or not isinstance(structured.get("answer"), str)
                or not isinstance(structured.get("citation_ids", []), list)
                or not isinstance(structured.get("limitations", []), list)):
            raise AiProviderError("Salida estructurada inválida del proveedor")
        usage = data.get("usage") or {}
        return ProviderResult(answer=structured.get("answer", ""), model=data.get("model", self.model),
            input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"), latency_ms=latency,
            citation_ids=structured.get("citation_ids") or [], limitations=structured.get("limitations") or [])

    def test_connection(self):
        self._request({"model": self.model, "input": "Responde únicamente OK.",
            "max_output_tokens": 8})


def build_ai_provider():
    if settings.territory_ai_provider == "openai":
        return OpenAIProvider()
    return UnavailableAiProvider()
