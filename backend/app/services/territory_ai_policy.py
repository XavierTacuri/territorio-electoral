import re
from dataclasses import dataclass
from app.schemas.territory_ai import PoliticalSafetyCategory

@dataclass(frozen=True)
class PolicyDecision: allowed:bool;category:PoliticalSafetyCategory;message:str|None=None
class TerritoryAIPolicy:
    SECRET=re.compile(r"territory_ai_api_key|database_url|authorization(?: header)?|cookies?|system prompt|variables? de entorno|environment variables?",re.I)
    WIN=re.compile(r"qui[eé]n (?:va a )?ganar[aá]?|pred(?:ice|ecir).*(?:ganador|elecci[oó]n)|resultado futuro",re.I)
    TARGET=re.compile(r"qu[eé] votantes?.*(?:convencer|persuadir)|personas?.*persuadibles|d[oó]nde.*(?:invertir|gastar).*(?:votos|ganar)|segment(?:a|ar).*(?:votantes|electores)",re.I)
    PERSUADE=re.compile(r"qu[eé] mensaje.*(?:funciona|conviene).*(?:mujeres|j[oó]venes|votantes)|c[oó]mo convencer|estrategia de persuasi[oó]n",re.I)
    PROFILE=re.compile(r"perfil pol[ií]tico individual|c[oó]mo votar[aá] (?:esta|una) persona|afinidad pol[ií]tica individual",re.I)
    def evaluate(self,text:str)->PolicyDecision:
        if self.SECRET.search(text):return PolicyDecision(False,PoliticalSafetyCategory.SECRET_EXTRACTION,"No puedo revelar secretos, configuración interna ni credenciales. Puedo explicar qué fuentes de datos utiliza Territorio IA.")
        if self.WIN.search(text):return PolicyDecision(False,PoliticalSafetyCategory.WIN_PREDICTION,"No realizo predicciones de ganador. Puedo describir participación histórica, padrón y porcentajes observados en estudios agregados.")
        if self.TARGET.search(text):return PolicyDecision(False,PoliticalSafetyCategory.MICROTARGETING,"No ayudo a seleccionar votantes o territorios para obtener votos. Puedo ofrecer un resumen descriptivo y agregado de necesidades o participación.")
        if self.PERSUADE.search(text):return PolicyDecision(False,PoliticalSafetyCategory.PERSUASION,"No genero mensajes de persuasión política dirigidos. Puedo resumir información pública o agregada de forma neutral.")
        if self.PROFILE.search(text):return PolicyDecision(False,PoliticalSafetyCategory.INDIVIDUAL_POLITICAL_PROFILING,"No elaboro perfiles políticos individuales. Puedo trabajar únicamente con información territorial agregada.")
        category=PoliticalSafetyCategory.METHODOLOGY if "metodolog" in text.lower() else PoliticalSafetyCategory.DESCRIPTIVE
        return PolicyDecision(True,category)
