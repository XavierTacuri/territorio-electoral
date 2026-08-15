import re
from app.schemas.territory_ai import TerritoryAIIntent
class TerritoryAIIntentRouter:
    RULES=((r"padr[oó]n|registro electoral|electores",TerritoryAIIntent.ELECTORAL_REGISTER),(r"proyecci[oó]n|participaci[oó]n central|central proyectad|low|high|votantes esperados",TerritoryAIIntent.TURNOUT_PROJECTION),(r"participaci[oó]n|turnout",TerritoryAIIntent.HISTORICAL_TURNOUT),(r"poblaci[oó]n|demograf|densidad|inec|hombres|mujeres|edades",TerritoryAIIntent.DEMOGRAPHICS),(r"encuesta|estudio|exit poll|tracking|porcentaje observado",TerritoryAIIntent.SURVEY_STUDIES),(r"necesidad",TerritoryAIIntent.NEEDS),(r"compromiso",TerritoryAIIntent.COMMITMENTS),(r"actividades|operaci[oó]n|agenda|aprobaci[oó]n",TerritoryAIIntent.OPERATIONS),(r"informaci[oó]n p[uú]blica|inteligencia p[uú]blica|noticias|publicaci[oó]n",TerritoryAIIntent.PUBLIC_INTELLIGENCE),(r"fuente|corte de datos",TerritoryAIIntent.SOURCE_LOOKUP),(r"resume|resumen|estado territorial",TerritoryAIIntent.TERRITORY_SUMMARY))
    def route_all(self,question:str,previous:TerritoryAIIntent|None=None)->list[TerritoryAIIntent]:
        normalized=question.lower()
        matches=[intent for pattern,intent in self.RULES if re.search(pattern,normalized)]
        if TerritoryAIIntent.TURNOUT_PROJECTION in matches and TerritoryAIIntent.HISTORICAL_TURNOUT in matches:matches.remove(TerritoryAIIntent.HISTORICAL_TURNOUT)
        if matches:return list(dict.fromkeys(matches))
        if previous and re.match(r"^(?:¿?y|tambi[eé]n|ahora)",normalized.strip()):return [previous]
        return [TerritoryAIIntent.GENERAL_GROUNDED_SEARCH]
    def route(self,question:str,previous:TerritoryAIIntent|None=None)->TerritoryAIIntent:return self.route_all(question,previous)[0]
