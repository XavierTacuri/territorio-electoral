from app.schemas.territory_ai import TerritoryAIIntent,TerritoryAIQueryPlan,TerritoryAISourceKind
class TerritoryAIQueryPlanner:
    SOURCES={
      TerritoryAIIntent.ELECTORAL_PANORAMA:[TerritoryAISourceKind.CNE,TerritoryAISourceKind.TURNOUT_MODEL,TerritoryAISourceKind.INEC,TerritoryAISourceKind.SURVEY_STUDY,TerritoryAISourceKind.TERRITORIAL_ACTIVITY,TerritoryAISourceKind.CITIZEN_NEED,TerritoryAISourceKind.PUBLIC_INTELLIGENCE],
      # Needs-first (§7-22): CitizenNeed -> TerritorialActivity -> ActivityEvidence
      # -> SurveyStudy -> PublicIntelligence, con CNE/INEC al final como
      # contexto oficial de menor prioridad (nunca el punto de partida).
      TerritoryAIIntent.DEBATE_BRIEF:[TerritoryAISourceKind.CITIZEN_NEED,TerritoryAISourceKind.TERRITORIAL_ACTIVITY,TerritoryAISourceKind.ACTIVITY_EVIDENCE,TerritoryAISourceKind.SURVEY_STUDY,TerritoryAISourceKind.PUBLIC_INTELLIGENCE,TerritoryAISourceKind.CNE,TerritoryAISourceKind.INEC],
      TerritoryAIIntent.ELECTION_DAY_OPERATIONS:[TerritoryAISourceKind.ELECTION_DAY],
      TerritoryAIIntent.TERRITORY_SUMMARY:[TerritoryAISourceKind.CNE,TerritoryAISourceKind.TURNOUT_MODEL,TerritoryAISourceKind.INEC,TerritoryAISourceKind.TERRITORIAL_ACTIVITY,TerritoryAISourceKind.CITIZEN_NEED,TerritoryAISourceKind.ACTIVITY_EVIDENCE,TerritoryAISourceKind.SURVEY_STUDY,TerritoryAISourceKind.PUBLIC_INTELLIGENCE],
      TerritoryAIIntent.ELECTORAL_REGISTER:[TerritoryAISourceKind.CNE],TerritoryAIIntent.HISTORICAL_TURNOUT:[TerritoryAISourceKind.CNE,TerritoryAISourceKind.TURNOUT_MODEL,TerritoryAISourceKind.SYSTEM_METADATA],TerritoryAIIntent.TURNOUT_PROJECTION:[TerritoryAISourceKind.TURNOUT_MODEL],TerritoryAIIntent.DEMOGRAPHICS:[TerritoryAISourceKind.INEC],TerritoryAIIntent.SURVEY_STUDIES:[TerritoryAISourceKind.SURVEY_STUDY],TerritoryAIIntent.OPERATIONS:[TerritoryAISourceKind.TERRITORIAL_ACTIVITY,TerritoryAISourceKind.ACTIVITY_EVIDENCE],TerritoryAIIntent.NEEDS:[TerritoryAISourceKind.CITIZEN_NEED],TerritoryAIIntent.COMMITMENTS:[TerritoryAISourceKind.COMMITMENT],TerritoryAIIntent.PUBLIC_INTELLIGENCE:[TerritoryAISourceKind.PUBLIC_INTELLIGENCE],TerritoryAIIntent.SOURCE_LOOKUP:[TerritoryAISourceKind.SYSTEM_METADATA],TerritoryAIIntent.GENERAL_GROUNDED_SEARCH:[TerritoryAISourceKind.PUBLIC_INTELLIGENCE],TerritoryAIIntent.CAMPAIGN_SCHEDULE:[TerritoryAISourceKind.CAMPAIGN_SCHEDULE],TerritoryAIIntent.OPERATIONAL_ALERTS:[TerritoryAISourceKind.OPERATIONAL_ALERT],}
    def plan(self,intent,territory=None,context_ids=None):
        intents=[intent] if isinstance(intent,TerritoryAIIntent) else list(intent)
        source_kinds=list(dict.fromkeys(kind for item in intents for kind in self.SOURCES[item]))
        return TerritoryAIQueryPlan(intent=intents[0],intents=intents,source_kinds=source_kinds,territory=territory,context_ids=context_ids or {})
