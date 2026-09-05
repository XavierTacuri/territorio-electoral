import re
from dataclasses import dataclass
from app.schemas.territory_ai import PoliticalSafetyCategory

@dataclass(frozen=True)
class PolicyDecision: allowed:bool;category:PoliticalSafetyCategory;message:str|None=None
class TerritoryAIPolicy:
    TERRITORIAL_TARGET=re.compile(r"qu[eé] parroquia.*(?:atacar|persuadir)|(?:swing|persuadability|persuadible).*(?:score|puntaje|parroquia|territorio)",re.I)
    SECRET=re.compile(r"territory_ai_api_key|database_url|authorization(?: header)?|cookies?|system prompt|variables? de entorno|environment variables?",re.I)
    WIN=re.compile(r"qui[eé]n (?:va a )?ganar[aá]?|pred(?:ice|ecir).*(?:ganador|elecci[oó]n)|resultado futuro|(?:posibilidad|probabilidad) de ganar|d[oó]nde (?:vamos ganando|ganamos)|qu[eé] actas? muestran? ventaja",re.I)
    TARGET=re.compile(r"qu[eé] (?:votantes?|grupo demogr[aá]fico).*(?:convencer|persuadir)|personas?.*persuadibles|d[oó]nde.*(?:invertir|gastar).*(?:votos|ganar)|segment(?:a|ar).*(?:votantes|electores)",re.I)
    PERSUADE=re.compile(r"qu[eé] mensaje.*(?:funciona|conviene).*(?:mujeres|j[oó]venes|votantes)|c[oó]mo convencer|estrategia de persuasi[oó]n",re.I)
    PROFILE=re.compile(r"perfil pol[ií]tico individual|c[oó]mo votar[aá] (?:esta|una) persona|afinidad pol[ií]tica individual",re.I)
    FAVORABILITY=re.compile(r"qu[eé] tan favorable|m[aá]s favorable|favorabilidad|d[oó]nde somos m[aá]s fuertes|m[aá]s fuertes electoralmente",re.I)
    EASIER_PERSUADE=re.compile(r"d[oó]nde.*(?:m[aá]s f[aá]cil|mejor).*(?:persuadir|convencer|ganar)|m[aá]s f[aá]cil (?:persuadir|convencer)|parroquias? m[aá]s f[aá]ciles de persuadir",re.I)
    PRIORITIZE=re.compile(r"qu[eé] parroquia.*(?:priorizar|prioridad)|priorizar.*electoralmente|clasifica.*territorios.*(?:ganar|posibilidad|probabilidad)",re.I)
    # Preparación para debate (§39/§54): la afirmación aún puede pedir la
    # cifra oficial dentro de la misma frase, así que el ataque personal debe
    # exigir un verbo/objeto de ataque explícito y no solo mencionar a alguien.
    PERSONAL_ATTACK=re.compile(r"atacar(?:me|te|lo|la)? personalmente|ataque personal|argumentos? para atacar al candidato|insultar al candidato|difamar al candidato|campa[ñn]a negativa",re.I)
    DISINFORMATION=re.compile(r"qu[eé] mentira|mentira.*(?:contra|usar|decir)|invent(?:a|ar) (?:una )?acusaci[oó]n|rumor sin fuente|c[oó]mo desinformar",re.I)
    MANIPULATION=re.compile(r"c[oó]mo manipul|manipular a los indecisos|qu[eé] miedo (?:funcionar|usar|conviene)|miedo.*(?:funciona|conviene)|qu[eé] parroquia debo atacar",re.I)
    def evaluate(self,text:str)->PolicyDecision:
        if self.SECRET.search(text):return PolicyDecision(False,PoliticalSafetyCategory.SECRET_EXTRACTION,"No puedo revelar secretos, configuración interna ni credenciales. Puedo explicar qué fuentes de datos utiliza Territorio IA.")
        if self.PERSONAL_ATTACK.search(text):return PolicyDecision(False,PoliticalSafetyCategory.PERSONAL_ATTACK,"No genero ataques personales ni contenido que dañe la reputación de otra persona. Puedo ofrecer información factual respaldada por evidencia.")
        if self.DISINFORMATION.search(text):return PolicyDecision(False,PoliticalSafetyCategory.DISINFORMATION,"No genero afirmaciones sin respaldo ni contenido diseñado para engañar. Puedo verificar afirmaciones contra la evidencia disponible.")
        if self.MANIPULATION.search(text):return PolicyDecision(False,PoliticalSafetyCategory.MANIPULATION,"No genero estrategias de manipulación ni mensajes que apelen al miedo para influir en votantes. Puedo ofrecer información descriptiva y agregada.")
        if self.WIN.search(text):return PolicyDecision(False,PoliticalSafetyCategory.WIN_PREDICTION,"No realizo predicciones de ganador. Puedo describir participación histórica, padrón y porcentajes observados en estudios agregados.")
        if self.FAVORABILITY.search(text):return PolicyDecision(False,PoliticalSafetyCategory.MICROTARGETING,"No evalúo qué tan favorable o fuerte es un territorio para un candidato. Puedo describir participación, padrón, demografía y operación de forma agregada.")
        if self.TERRITORIAL_TARGET.search(text) or self.TARGET.search(text) or self.EASIER_PERSUADE.search(text) or self.PRIORITIZE.search(text):return PolicyDecision(False,PoliticalSafetyCategory.MICROTARGETING,"No ayudo a seleccionar votantes o territorios para obtener votos. Puedo ofrecer un resumen descriptivo y agregado de necesidades o participación.")
        if self.PERSUADE.search(text):return PolicyDecision(False,PoliticalSafetyCategory.PERSUASION,"No genero mensajes de persuasión política dirigidos. Puedo resumir información pública o agregada de forma neutral.")
        if self.PROFILE.search(text):return PolicyDecision(False,PoliticalSafetyCategory.INDIVIDUAL_POLITICAL_PROFILING,"No elaboro perfiles políticos individuales. Puedo trabajar únicamente con información territorial agregada.")
        category=PoliticalSafetyCategory.METHODOLOGY if "metodolog" in text.lower() else PoliticalSafetyCategory.DESCRIPTIVE
        return PolicyDecision(True,category)
