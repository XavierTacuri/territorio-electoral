"""Catálogo de temas compartido por informes temáticos, preparación para debate
y alertas de recurrencia de necesidades — una sola fuente de verdad evita que
estas tres superficies clasifiquen el mismo registro en temas distintos.
"""
THEME_KEYWORDS = {
    "VIALIDAD": ["vial", "carretera", "calle", "asfalt", "pavimento", "puente"],
    "AGUA": ["agua", "saneamiento", "alcantarillado", "potable"],
    "SEGURIDAD": ["seguridad", "delincuenc", "robo", "violencia"],
    "CONECTIVIDAD": ["conectividad", "internet", "señal", "telefon"],
    "EMPLEO": ["empleo", "trabajo", "desempleo", "productiv"],
    "SALUD": ["salud", "médic", "hospital", "clínic", "centro de salud"],
    "EDUCACION": ["educaci", "escuela", "colegio", "docente"],
    "TRANSPORTE": ["transporte", "bus", "movilidad"],
    "VIVIENDA": ["vivienda", "habitacional"],
    "AMBIENTE": ["ambiente", "basura", "contaminac", "reciclaje", "desechos"],
    "PRESUPUESTO": ["presupuesto", "partida presupuestaria", "asignación de recursos", "gasto público"],
    "OBRAS_PUBLICAS": ["obra pública", "obras públicas", "construcción de obra", "infraestructura pública"],
    "OTROS": [],
}
THEME_LABELS = {
    "VIALIDAD": "Vialidad", "AGUA": "Agua y saneamiento", "SEGURIDAD": "Seguridad", "CONECTIVIDAD": "Conectividad",
    "EMPLEO": "Empleo", "SALUD": "Salud", "EDUCACION": "Educación", "TRANSPORTE": "Transporte",
    "VIVIENDA": "Vivienda", "AMBIENTE": "Ambiente", "PRESUPUESTO": "Presupuesto", "OBRAS_PUBLICAS": "Obras públicas",
    "OTROS": "Otros",
}
THEMES = set(THEME_KEYWORDS)


def theme_match(theme: str, *texts: str | None) -> bool:
    keywords = THEME_KEYWORDS.get(theme, [])
    if not keywords:
        return True
    haystack = " ".join(t for t in texts if t).casefold()
    return any(k in haystack for k in keywords)
