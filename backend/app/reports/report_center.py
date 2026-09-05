"""Bloques de contenido para los informes del Centro de Informes.

Estas funciones solo dan forma tabular a hechos ya calculados por
ReportDataService — nunca recalculan cifras ni acceden a la base de datos.
"""
EVIDENCE_CLASS_LABELS = {"OFFICIAL": "Oficial", "PUBLIC": "Fuente pública", "CAMPAIGN": "Registro de campaña", "DEMO": "Datos simulados"}
DISCLAIMER = "Informe descriptivo generado por Territorio Electoral. No constituye predicción electoral, persuasión política ni perfilamiento individual."


def narrative_sections(narrative):
    return [
        {"title": "Resumen ejecutivo", "text": narrative["resumen_ejecutivo"], "headers": [], "rows": []},
        {"title": "Hallazgos principales", "headers": ["Hallazgo"], "rows": [[h] for h in narrative["hallazgos_principales"]]},
    ]


def citations_section(citations):
    rows = [[c["title"], c["source_name"], EVIDENCE_CLASS_LABELS.get(c["evidence_class"], c["evidence_class"]), c.get("record_date"), c.get("source_url") or c.get("deep_link") or "No disponible"] for c in citations]
    return {"title": "Evidencia y fuentes", "headers": ["Elemento", "Fuente", "Clasificación", "Fecha", "Enlace"], "formats": [None, None, None, "date", None], "rows": rows}


def limitations_section(limitations, is_demo):
    text = DISCLAIMER
    if is_demo:
        text += "\n\nATENCIÓN: este informe incluye datos simulados para demostración, marcados explícitamente en la evidencia."
    if limitations:
        text += "\n\n" + "\n".join(f"- {item}" for item in limitations)
    return {"title": "Limitaciones y calidad", "text": text, "headers": [], "rows": []}


def _metric_value(overview, code):
    for metric in overview.get("metrics", []):
        if hasattr(metric, "model_dump"): metric = metric.model_dump()
        if metric.get("code") == code: return metric.get("value")
    return None


def executive_sections(data):
    overview = data["overview"]
    rows = [["Actividades completadas", _metric_value(overview, "completed_activities")],
            ["Parroquias con cobertura", f"{overview['territorial_coverage']['covered_parishes']} / {overview['territorial_coverage']['accessible_parishes']}"],
            ["Necesidades activas", _metric_value(overview, "active_needs")],
            ["Encuestas publicadas", overview["survey_summary"]["published"]]]
    sections = [{"title": "Panorama operativo", "headers": ["Indicador", "Valor"], "rows": rows}]
    analysis = data.get("current_election")
    if analysis:
        snapshot = analysis.get("snapshot", {})
        sections.append({"title": "Contexto electoral", "headers": ["Indicador", "Valor"], "formats": [None, "integer"],
                          "rows": [["Padrón actual", snapshot.get("registered_voters")], ["Corte", snapshot.get("snapshot_date")]]})
    if data.get("studies"):
        sections.append({"title": "Encuestas publicadas", "headers": ["Estudio", "Estado", "Cierre de campo"], "rows": [[s["name"], s["status"], s["fieldwork_end_date"]] for s in data["studies"]]})
    if data.get("public_items"):
        sections.append({"title": "Información pública reciente", "headers": ["Título", "Publicador", "Publicado"], "formats": [None, None, "date"], "rows": [[p["title"], p["publisher"], p["published_at"]] for p in data["public_items"]]})
    return sections


def parish_profile_sections(data):
    sections = []
    if data.get("activities"):
        sections.append({"title": "Actividades en la parroquia", "headers": ["Actividad", "Fecha", "Estado"], "formats": [None, "date", None], "rows": [[a["title"], a["date"], a["status"]] for a in data["activities"]]})
    if data.get("needs"):
        sections.append({"title": "Necesidades registradas", "headers": ["Necesidad", "Estado", "Prioridad"], "rows": [[n["title"], n["status"], n["priority"]] for n in data["needs"]]})
    if data.get("evidence"):
        sections.append({"title": "Evidencia disponible", "headers": ["Título", "Tipo", "Fecha"], "formats": [None, None, "date"], "rows": [[e["title"], e["evidence_type"], e["date"]] for e in data["evidence"]]})
    if data.get("studies"):
        sections.append({"title": "Encuestas con cobertura parroquial", "headers": ["Estudio", "Estado", "Cierre de campo"], "rows": [[s["name"], s["status"], s["fieldwork_end_date"]] for s in data["studies"]]})
    if data.get("public_items"):
        sections.append({"title": "Información pública", "headers": ["Título", "Publicador", "Publicado"], "formats": [None, None, "date"], "rows": [[p["title"], p["publisher"], p["published_at"]] for p in data["public_items"]]})
    return sections


def electoral_descriptive_sections(data):
    if not data.get("studies"):
        return []
    return [{"title": "Encuestas publicadas", "headers": ["Estudio", "Estado", "Cierre de campo", "Muestra"], "formats": [None, None, "date", "integer"], "rows": [[s["name"], s["status"], s["fieldwork_end_date"], s["sample_size_total"]] for s in data["studies"]]}]


def operation_sections(data):
    sections = [{"title": "Resumen operativo", "headers": ["Indicador", "Valor"], "formats": [None, "integer"],
                 "rows": [["Actividades realizadas", data["completed_count"]], ["Actividades próximas", data["upcoming_count"]], ["Parroquias con cobertura", data["covered_parishes"]], ["Necesidades detectadas", len(data["needs"])]]}]
    if data.get("chronology"):
        sections.append({"title": "Cronología de actividades", "headers": ["Fecha", "Actividad", "Estado"], "formats": ["date", None, None], "rows": [[c["date"], c["title"], c["status"]] for c in data["chronology"]]})
    if data.get("needs"):
        sections.append({"title": "Necesidades detectadas", "headers": ["Necesidad", "Estado", "Prioridad"], "rows": [[n["title"], n["status"], n["priority"]] for n in data["needs"]]})
    if data.get("evidence"):
        sections.append({"title": "Evidencia disponible", "headers": ["Título", "Tipo"], "rows": [[e["title"], e["evidence_type"]] for e in data["evidence"]]})
    return sections


ELECTION_DAY_STATUS_LABELS = {"PREPARATION": "En preparación", "ACTIVE": "Jornada activa", "CLOSED": "Jornada cerrada"}


def election_day_sections(data):
    coverage = data["coverage"]
    sections = [{"title": "Estado de la jornada", "headers": ["Indicador", "Valor"], "rows": [
        ["Estado", ELECTION_DAY_STATUS_LABELS.get(data["election_day_status"], data["election_day_status"])],
        ["Recintos cubiertos", f"{coverage['covered_polling_places']} / {coverage['total_polling_places']}"],
        ["Juntas cubiertas", f"{coverage['covered_boards']} / {coverage['total_boards']}"],
        ["Personal confirmado", coverage["personnel_confirmed"]],
        ["Personal presente", coverage["personnel_checked_in"]],
        ["Incidencias abiertas", coverage["open_incidents"]],
        ["Documentos recibidos", f"{coverage['documents_received']} / {coverage['expected_documents']}"],
    ]}]
    sections.append({"title": "Incidencias", "headers": ["Recinto", "Categoría", "Estado"], "rows": [[i["polling_place_name"], i["category"], i["status"]] for i in data["incidents"]]} if data.get("incidents") else
                     {"title": "Incidencias", "text": "No hay incidencias registradas.", "headers": [], "rows": []})
    sections.append({"title": "Documentación recibida", "headers": ["Recinto", "Tipo", "Estado"], "rows": [[d["polling_place_name"], d["document_type"], d["status"]] for d in data["documents"]]} if data.get("documents") else
                     {"title": "Documentación recibida", "text": "Aún no se han recibido documentos.", "headers": [], "rows": []})
    if data.get("chronology"):
        sections.append({"title": "Cronología", "headers": ["Fecha", "Evento", "Estado"], "formats": ["date", None, None], "rows": [[c["date"], c["title"], c["status"]] for c in data["chronology"]]})
    if data["election_day_status"] == "ACTIVE":
        sections.insert(0, {"title": "Aviso", "text": "INFORME OPERATIVO PROVISIONAL: la jornada sigue activa y los datos pueden cambiar hasta su cierre.", "headers": [], "rows": []})
    return sections


def debate_brief_sections(data):
    sections = []
    if data.get("official_rows"):
        sections.append({"title": "Datos oficiales", "headers": ["Indicador", "Valor", "Fuente"], "rows": data["official_rows"]})
    else:
        sections.append({"title": "Datos oficiales", "text": "No hay datos oficiales disponibles para este contexto.", "headers": [], "rows": []})
    sections.append({"title": "Evidencia territorial", "headers": ["Título", "Tipo"], "rows": [[e["title"], e["evidence_type"]] for e in data["evidence"]]} if data.get("evidence") else
                     {"title": "Evidencia territorial", "text": "No hay evidencia territorial disponible para este tema.", "headers": [], "rows": []})
    sections.append({"title": "Actividades relacionadas", "headers": ["Actividad", "Fecha", "Estado"], "formats": [None, "date", None], "rows": [[a["title"], a["date"], a["status"]] for a in data["activities"]]} if data.get("activities") else
                     {"title": "Actividades relacionadas", "text": "No hay actividades registradas para este tema.", "headers": [], "rows": []})
    sections.append({"title": "Necesidades registradas", "headers": ["Necesidad", "Estado", "Prioridad"], "rows": [[n["title"], n["status"], n["priority"]] for n in data["needs"]]} if data.get("needs") else
                     {"title": "Necesidades registradas", "text": "No hay necesidades registradas para este tema.", "headers": [], "rows": []})
    if data.get("studies"):
        sections.append({"title": "Estudios y encuestas", "headers": ["Estudio", "Cierre de campo"], "rows": [[s["name"], s["fieldwork_end_date"]] for s in data["studies"]]})
    if data.get("public_items"):
        sections.append({"title": "Información pública", "headers": ["Título", "Publicador"], "rows": [[p["title"], p["publisher"]] for p in data["public_items"]]})
    qa = data.get("qa_pairs") or []
    sections.append({"title": "Preguntas que podrían surgir", "headers": ["Pregunta", "Hechos disponibles", "Respuesta factual sugerida", "Fuentes"], "rows": [[q["question"], q["facts"], q["answer"], q["sources"]] for q in qa]})
    verification = data.get("verification_points") or []
    sections.append({"title": "Puntos que necesitan verificación", "headers": ["Elemento", "Motivo"], "rows": verification} if verification else
                     {"title": "Puntos que necesitan verificación", "text": "No se identificaron puntos adicionales que requieran verificación manual.", "headers": [], "rows": []})
    return sections


def thematic_sections(data):
    sections = [{"title": f"Necesidades — {data['theme_label']}", "headers": ["Necesidad", "Estado", "Prioridad"], "rows": [[n["title"], n["status"], n["priority"]] for n in data["needs"]]} if data.get("needs") else
                {"title": f"Necesidades — {data['theme_label']}", "text": "No hay necesidades registradas para este tema.", "headers": [], "rows": []}]
    sections.append({"title": f"Actividades — {data['theme_label']}", "headers": ["Actividad", "Fecha", "Estado"], "formats": [None, "date", None], "rows": [[a["title"], a["date"], a["status"]] for a in data["activities"]]} if data.get("activities") else
                     {"title": f"Actividades — {data['theme_label']}", "text": "No hay actividades registradas para este tema.", "headers": [], "rows": []})
    if data.get("studies"):
        sections.append({"title": "Encuestas relacionadas", "headers": ["Estudio", "Cierre de campo"], "rows": [[s["name"], s["fieldwork_end_date"]] for s in data["studies"]]})
    if data.get("public_items"):
        sections.append({"title": "Información pública relacionada", "headers": ["Título", "Publicador"], "rows": [[p["title"], p["publisher"]] for p in data["public_items"]]})
    if data.get("evidence"):
        sections.append({"title": "Evidencia relacionada", "headers": ["Título", "Tipo"], "rows": [[e["title"], e["evidence_type"]] for e in data["evidence"]]})
    return sections
