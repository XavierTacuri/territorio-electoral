from app.schemas.territory_ai import TerritoryAIIntent,TerritoryAIQueryPlan,TerritoryAISourceKind
class TerritoryAIQueryPlanner:
    SOURCES={
      TerritoryAIIntent.TERRITORY_SUMMARY:[TerritoryAISourceKind.CNE,TerritoryAISourceKind.TURNOUT_MODEL,TerritoryAISourceKind.INEC,TerritoryAISourceKind.TERRITORIAL_ACTIVITY,TerritoryAISourceKind.CITIZEN_NEED,TerritoryAISourceKind.COMMITMENT,TerritoryAISourceKind.SURVEY_STUDY,TerritoryAISourceKind.PUBLIC_INTELLIGENCE],
      TerritoryAIIntent.ELECTORAL_REGISTER:[TerritoryAISourceKind.CNE],TerritoryAIIntent.HISTORICAL_TURNOUT:[TerritoryAISourceKind.CNE],TerritoryAIIntent.TURNOUT_PROJECTION:[TerritoryAISourceKind.TURNOUT_MODEL],TerritoryAIIntent.DEMOGRAPHICS:[TerritoryAISourceKind.INEC],TerritoryAIIntent.SURVEY_STUDIES:[TerritoryAISourceKind.SURVEY_STUDY],TerritoryAIIntent.OPERATIONS:[TerritoryAISourceKind.TERRITORIAL_ACTIVITY],TerritoryAIIntent.NEEDS:[TerritoryAISourceKind.CITIZEN_NEED],TerritoryAIIntent.COMMITMENTS:[TerritoryAISourceKind.COMMITMENT],TerritoryAIIntent.PUBLIC_INTELLIGENCE:[TerritoryAISourceKind.PUBLIC_INTELLIGENCE],TerritoryAIIntent.SOURCE_LOOKUP:[TerritoryAISourceKind.SYSTEM_METADATA],TerritoryAIIntent.GENERAL_GROUNDED_SEARCH:[TerritoryAISourceKind.PUBLIC_INTELLIGENCE],}
    def plan(self,intent,territory=None,context_ids=None):
        intents=[intent] if isinstance(intent,TerritoryAIIntent) else list(intent)
        source_kinds=list(dict.fromkeys(kind for item in intents for kind in self.SOURCES[item]))
        return TerritoryAIQueryPlan(intent=intents[0],intents=intents,source_kinds=source_kinds,territory=territory,context_ids=context_ids or {})
