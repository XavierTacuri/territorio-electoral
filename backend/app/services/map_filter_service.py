from app.core.config import settings
from app.schemas.dashboard import DashboardFilters
from app.schemas.maps import MapFilters
from app.services.dashboard_filter_service import DashboardFilterService
from app.services.exceptions import BusinessRuleError
class MapFilterService(DashboardFilterService):
 def validate_map(self,filters:MapFilters):
  tolerance=filters.simplify_tolerance if filters.simplify_tolerance is not None else settings.map_default_simplify_tolerance
  if tolerance>settings.map_max_simplify_tolerance:raise BusinessRuleError("La tolerancia supera el máximo permitido")
  limit=filters.limit or settings.map_max_features
  if limit>settings.map_max_features:raise BusinessRuleError("La consulta geográfica supera el límite permitido")
  return tolerance,limit
 @staticmethod
 def dashboard_filters(filters:MapFilters):
  return DashboardFilters(date_from=filters.date_from,date_to=filters.date_to,period=filters.period,parish_id=filters.parish_id,community_id=filters.community_id,sector_id=filters.sector_id)
