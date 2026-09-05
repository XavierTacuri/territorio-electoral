import re
from app.schemas.territory_ai import TerritoryAIIntent
class TerritoryAIIntentRouter:
    PRIMARY_RULES=((r"panorama electoral|panorama.*(?:actual|ahora)",TerritoryAIIntent.ELECTORAL_PANORAMA),(r"(?:resumen|brief).*(?:debate)|debate.*(?:evidencia|factual|resumen)",TerritoryAIIntent.DEBATE_BRIEF),(r"jornada electoral|estado operativo.*jornada|recintos?.*incidencia|juntas?.*delegado|documentaci[oó]n.*(?:falta|pendiente)|incidencias?.*jornada|cobertura.*jornada",TerritoryAIIntent.ELECTION_DAY_OPERATIONS))
    # "compromiso" ya no enruta a un intent dedicado: Seguimientos/Commitment se
    # retiró como fuente productiva para nuevas respuestas de Territorio IA.
    RULES=((r"padr[oó]n|registro electoral|electores",TerritoryAIIntent.ELECTORAL_REGISTER),(r"proyecci[oó]n|participaci[oó]n central|central proyectad|low|high|votantes esperados",TerritoryAIIntent.TURNOUT_PROJECTION),(r"participaci[oó]n|turnout",TerritoryAIIntent.HISTORICAL_TURNOUT),(r"poblaci[oó]n|demograf|densidad|inec|hombres|mujeres|edades",TerritoryAIIntent.DEMOGRAPHICS),(r"encuesta|estudio|exit poll|tracking|porcentaje observado",TerritoryAIIntent.SURVEY_STUDIES),(r"necesidad",TerritoryAIIntent.NEEDS),(r"calendario|pr[oó]ximos eventos|pr[oó]ximo hito|hitos? electoral",TerritoryAIIntent.CAMPAIGN_SCHEDULE),(r"alertas?|qu[eé] requiere atenci[oó]n|requieren atenci[oó]n",TerritoryAIIntent.OPERATIONAL_ALERTS),(r"actividades|operaci[oó]n|agenda|aprobaci[oó]n|evidencia",TerritoryAIIntent.OPERATIONS),(r"informaci[oó]n p[uú]blica|inteligencia p[uú]blica|noticias|publicaci[oó]n",TerritoryAIIntent.PUBLIC_INTELLIGENCE),(r"fuente|corte de datos",TerritoryAIIntent.SOURCE_LOOKUP),(r"resume|resumen|estado territorial",TerritoryAIIntent.TERRITORY_SUMMARY))
    def route_all(self,question:str,previous:TerritoryAIIntent|None=None)->list[TerritoryAIIntent]:
        normalized=question.lower()
        matches=[intent for pattern,intent in self.PRIMARY_RULES+self.RULES if re.search(pattern,normalized)]
        if TerritoryAIIntent.TURNOUT_PROJECTION in matches and TerritoryAIIntent.HISTORICAL_TURNOUT in matches:matches.remove(TerritoryAIIntent.HISTORICAL_TURNOUT)
        if matches:return list(dict.fromkeys(matches))
        if previous and re.match(r"^(?:¿?y|tambi[eé]n|ahora)",normalized.strip()):return [previous]
        return [TerritoryAIIntent.GENERAL_GROUNDED_SEARCH]
    def route(self,question:str,previous:TerritoryAIIntent|None=None)->TerritoryAIIntent:return self.route_all(question,previous)[0]
