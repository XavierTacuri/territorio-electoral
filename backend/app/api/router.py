from fastapi import APIRouter
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.roles import router as roles_router
from app.api.routes.users import router as users_router
from app.api.routes.territory import router as territory_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.operational import router as operational_router
from app.api.routes.surveys import router as surveys_router
from app.api.routes.data_imports import router as data_imports_router
from app.api.routes.electoral import router as electoral_router
from app.api.routes.demographics import router as demographics_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.maps import router as maps_router, geometry_router
from app.api.routes.reports import router as reports_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.security import router as security_router
from app.api.routes.participation import router as participation_router
from app.api.routes.survey_studies import router as survey_studies_router
from app.api.routes.public_intelligence import router as public_intelligence_router
from app.api.routes.entitlements import router as entitlements_router
from app.api.routes.organizations import router as organizations_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(roles_router)
api_router.include_router(users_router)
api_router.include_router(territory_router)
api_router.include_router(campaigns_router)
api_router.include_router(operational_router)
api_router.include_router(surveys_router)
api_router.include_router(data_imports_router)
api_router.include_router(electoral_router)
api_router.include_router(demographics_router)
api_router.include_router(dashboard_router)
api_router.include_router(maps_router)
api_router.include_router(geometry_router)

api_router.include_router(reports_router)
api_router.include_router(alerts_router)
api_router.include_router(security_router)
api_router.include_router(participation_router)
api_router.include_router(survey_studies_router)
api_router.include_router(public_intelligence_router)
api_router.include_router(entitlements_router)
api_router.include_router(organizations_router)
