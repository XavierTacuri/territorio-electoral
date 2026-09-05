import json

import httpx
import pytest

from app.services.territory_ai_provider import (
    AiProviderAuthenticationError,
    AiProviderError,
    AiProviderRateLimitError,
    OpenAIProvider,
)


def provider(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAIProvider(api_key="synthetic-test-key", model="synthetic-model", client=client)


def response_payload(*, text=None, usage=True):
    payload = {"model": "synthetic-model", "output_text": text or json.dumps({
        "answer": "Respuesta basada en evidencia.", "citation_ids": ["evidence-1"], "limitations": []})}
    if usage:
        payload["usage"] = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    return payload


def test_openai_provider_success_and_usage():
    captured = {}
    def handler(request):
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=response_payload())
    result = provider(handler).generate("Pregunta", {"system_prompt": "Política", "documents": [{"evidence_id": "evidence-1"}]})
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (11, 7, 18)
    assert result.model == "synthetic-model" and result.latency_ms is not None
    assert "evidence-1" in captured["payload"]["input"]
    assert captured["authorization"] == "Bearer synthetic-test-key"


def test_openai_provider_receives_pre_extracted_panorama_facts():
    captured = {}
    def handler(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=response_payload())
    provider(handler).generate("Panorama", {
        "documents": [{"evidence_id": "evidence-1"}],
        "panorama_facts": {"current_roll": {"registered_voters": 12345}},
    })
    assert '"registered_voters": 12345' in captured["payload"]["input"]
    assert "no recalcular" in captured["payload"]["input"]


def test_openai_provider_without_usage():
    result = provider(lambda _: httpx.Response(200, json=response_payload(usage=False))).generate(
        "Pregunta", {"documents": []})
    assert result.input_tokens is None and result.output_tokens is None and result.total_tokens is None


@pytest.mark.parametrize("status,error", [(401, AiProviderAuthenticationError),
    (403, AiProviderAuthenticationError), (429, AiProviderRateLimitError)])
def test_openai_provider_controlled_http_errors(status, error):
    with pytest.raises(error):
        provider(lambda _: httpx.Response(status)).test_connection()


def test_openai_provider_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)
    with pytest.raises(TimeoutError):
        provider(handler).test_connection()


def test_openai_provider_invalid_json_response():
    with pytest.raises(AiProviderError):
        provider(lambda _: httpx.Response(200, content=b"not-json")).test_connection()


def test_openai_provider_invalid_structured_output():
    with pytest.raises(AiProviderError):
        provider(lambda _: httpx.Response(200, json=response_payload(text='{"unexpected": true}'))).generate(
            "Pregunta", {"documents": []})
