from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_admin
from app.core.config import settings
from app.models.user import User
from app.schemas.ai_provider import AiProviderConfiguration, AiProviderConnectionResult
from app.services.territory_ai_provider import AiProviderAuthenticationError, AiProviderError, OpenAIProvider

router = APIRouter(prefix="/admin/ai-provider", tags=["ai-provider"])


@router.get("", response_model=AiProviderConfiguration)
def configuration(_: User = Depends(require_admin)) -> AiProviderConfiguration:
    provider = settings.territory_ai_provider
    configured = bool(settings.openai_api_key and settings.openai_api_key.strip())
    if settings.app_env.lower() == "e2e" or (provider == "fake" and settings.app_env.lower() in {"development", "dev", "local"}):
        return AiProviderConfiguration(provider="fake", provider_label="Proveedor de pruebas",
            model="territory-ai-fake-v1", status="CONNECTED", api_key_configured=False)
    available = provider == "openai" and configured and bool(settings.territory_ai_model)
    return AiProviderConfiguration(provider=provider, provider_label="OpenAI" if provider == "openai" else "No configurado",
        model=settings.territory_ai_model or None, status="CONNECTED" if available else "NOT_CONFIGURED",
        api_key_configured=configured)


@router.post("/test", response_model=AiProviderConnectionResult)
def test_connection(_: User = Depends(require_admin)) -> AiProviderConnectionResult:
    if settings.app_env.lower() == "e2e" or (settings.territory_ai_provider == "fake" and settings.app_env.lower() in {"development", "dev", "local"}):
        return AiProviderConnectionResult(status="CONNECTED", provider="fake",
            model="territory-ai-fake-v1", checked_at=datetime.now(timezone.utc))
    if settings.territory_ai_provider != "openai" or not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="No se ha configurado una clave de API.")
    provider = OpenAIProvider()
    try:
        provider.test_connection()
    except AiProviderAuthenticationError as exc:
        raise HTTPException(status_code=503, detail="No fue posible autenticar con el proveedor de IA.") from exc
    except (AiProviderError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="No fue posible conectar con el proveedor de IA.") from exc
    return AiProviderConnectionResult(status="CONNECTED", provider="openai", model=provider.model,
        checked_at=datetime.now(timezone.utc))
