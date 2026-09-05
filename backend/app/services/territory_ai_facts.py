from collections import Counter, defaultdict
from typing import Any


def format_integer(value: int | float) -> str:
    return f"{round(value):,}".replace(",", ".")


def format_percent(value: int | float) -> str:
    percent = float(value) * 100 if abs(float(value)) <= 1 else float(value)
    return f"{percent:.2f}".replace(".", ",") + " %"


def _citation(document: dict[str, Any]) -> dict[str, str]:
    return {"evidence_id": document["evidence_id"], "title": document["title"]}


def _aggregate(documents: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any] | None:
    if not documents:
        return None
    # Canton evidence is already aggregated by the retriever. Otherwise aggregate
    # the authorized parish rows so providers never need to perform arithmetic.
    data = {key: sum((doc.get("structured_data") or {}).get(key) or 0 for doc in documents) for key in keys}
    data["citation"] = _citation(documents[0])
    return data


def build_panorama_facts(documents: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        by_kind[document["source_kind"]].append(document)

    current_docs = [d for d in by_kind["CNE"] if (d.get("structured_data") or {}).get("registered_voters") is not None and (d.get("structured_data") or {}).get("year") is None]
    current_roll = _aggregate(current_docs, ("registered_voters",))

    turnout_docs = by_kind["TURNOUT_MODEL"]
    turnout = _aggregate(turnout_docs, ("registered_voters", "expected_voters_low", "expected_voters_central", "expected_voters_high"))
    if turnout:
        registered = turnout["registered_voters"]
        for scenario in ("low", "central", "high"):
            persisted_rates = [(d.get("structured_data") or {}).get(f"turnout_rate_{scenario}") for d in turnout_docs]
            # Preserve a persisted aggregate rate when present. For several scoped
            # parish rows the only correct canton rate is the authorized aggregate.
            turnout[f"turnout_rate_{scenario}"] = persisted_rates[0] if len(turnout_docs) == 1 else (turnout[f"expected_voters_{scenario}"] / registered if registered else None)

    historical = []
    historical_docs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for document in by_kind["CNE"]:
        year = (document.get("structured_data") or {}).get("year")
        if year is not None:
            historical_docs[int(year)].append(document)
    for year, rows in sorted(historical_docs.items()):
        item = _aggregate(rows, ("registered_voters", "ballots_cast"))
        if item:
            persisted = [(d.get("structured_data") or {}).get("turnout_rate") for d in rows]
            item.update(year=year, turnout_rate=persisted[0] if len(rows) == 1 else (item["ballots_cast"] / item["registered_voters"] if item["registered_voters"] else None))
            historical.append(item)

    demographics = []
    population_candidates = []
    for document in by_kind["INEC"]:
        data = document.get("structured_data") or {}
        item = {**data, "title": document["title"], "citation": _citation(document)}
        demographics.append(item)
        code = str(data.get("indicator_code") or "").upper()
        title = document["title"].casefold()
        if code in {"POP_TOTAL", "E2E_POP_TOTAL"} or "poblaci" in title:
            population_candidates.append(item)

    coded_population = [item for item in population_candidates if str(item.get("indicator_code") or "").upper() in {"POP_TOTAL", "E2E_POP_TOTAL"}]
    if coded_population:
        population_candidates = coded_population
    parish_population = [item for item in population_candidates if str(item.get("geography_level") or "").upper() == "PARISH"]
    if parish_population:
        latest_year = max(item.get("reference_year") or 0 for item in parish_population)
        latest = [item for item in parish_population if (item.get("reference_year") or 0) == latest_year]
        population = {**latest[0], "value": sum(item["value"] for item in latest)}
    else:
        population = next((item for item in population_candidates if str(item.get("geography_level") or "").upper() == "CANTON"), None)
    if population is None and population_candidates:
        latest_year = max(item.get("reference_year") or 0 for item in population_candidates)
        latest = [item for item in population_candidates if (item.get("reference_year") or 0) == latest_year]
        population = {**latest[0], "value": sum(item["value"] for item in latest)}

    def collection(kind: str) -> dict[str, Any]:
        rows = by_kind[kind]
        statuses = Counter(str((d.get("structured_data") or {}).get("status") or "SIN_ESTADO") for d in rows)
        demo = [d for d in rows if d.get("evidence_class") == "DEMO"]
        return {
            "count": len(rows),
            "items": [{"title": d["title"], **(d.get("structured_data") or {}), "citation": _citation(d)} for d in rows],
            "statuses": dict(statuses),
            "demo_count": len(demo),
        }

    return {
        "current_roll": current_roll,
        "turnout": turnout,
        "historical": historical,
        "demographics": {"population": population, "indicators": demographics},
        "studies": collection("SURVEY_STUDY"),
        "operations": collection("TERRITORIAL_ACTIVITY"),
        "needs": collection("CITIZEN_NEED"),
        "public_info": collection("PUBLIC_INTELLIGENCE"),
    }


def panorama_citation_ids(facts: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    def add(citation):
        if citation and citation.get("evidence_id") not in ids:
            ids.append(citation["evidence_id"])
    add((facts.get("current_roll") or {}).get("citation"))
    add((facts.get("turnout") or {}).get("citation"))
    for item in facts.get("historical", []): add(item.get("citation"))
    demographics = facts.get("demographics") or {}
    add((demographics.get("population") or {}).get("citation"))
    rendered_indicators = [item for item in demographics.get("indicators", [])
        if str(item.get("indicator_code") or "").upper() not in {"POP_TOTAL", "E2E_POP_TOTAL"}
        and "poblaci" not in item.get("title", "").casefold() and item.get("value") is not None]
    for item in rendered_indicators[:6]: add(item.get("citation"))
    # Preserve at least one citation from every rendered collection before
    # filling the remaining structured-output budget.
    for section in ("studies", "operations", "needs", "public_info"):
        items=(facts.get(section) or {}).get("items", [])
        if items:add(items[0].get("citation"))
    for section in ("studies", "operations", "needs", "public_info"):
        for item in (facts.get(section) or {}).get("items", [])[1:5]:add(item.get("citation"))
    # The structured provider contract accepts at most 30 citations.
    return ids[:30]


def render_historical_turnout(facts: dict[str, Any]) -> str:
    sections = ["Participación electoral histórica y proyección V1"]
    historical = facts.get("historical") or []
    if historical:
        sections.append("Históricos\n" + "\n".join(
            f"{item['year']}: {format_integer(item['ballots_cast'])} votos emitidos "
            f"({format_percent(item['turnout_rate'])}) sobre {format_integer(item['registered_voters'])} electores. "
            f"[{item['citation']['title']}]" for item in historical
        ))
    else:
        sections.append("Históricos\nNo hay antecedentes electorales disponibles.")
    turnout = facts.get("turnout")
    if turnout:
        lines = []
        for label, key in (("Bajo", "low"), ("Central", "central"), ("Alto", "high")):
            expected, rate = turnout.get(f"expected_voters_{key}"), turnout.get(f"turnout_rate_{key}")
            if expected is not None and rate is not None:
                lines.append(f"{label}: {format_integer(expected)} votantes ({format_percent(rate)}).")
        sections.append("Proyección de participación V1\n" + "\n".join(lines)
            + f"\n[{turnout['citation']['title']}]\nEs una estimación de participación, no de apoyo político.")
    else:
        sections.append("Proyección de participación V1\nNo hay una proyección V1 disponible.")
    sections.append("Limitaciones\nLos cambios entre procesos deben interpretarse considerando cortes y rupturas de serie. No constituye una predicción electoral.")
    return "\n\n".join(sections)


def render_panorama(facts: dict[str, Any]) -> str:
    sections = ["Panorama electoral"]
    current = facts.get("current_roll")
    sections.append("Padrón electoral\n" + (f"Padrón electoral actual: {format_integer(current['registered_voters'])} electores. [{current['citation']['title']}]" if current else "No hay información de padrón electoral actual disponible."))

    turnout = facts.get("turnout")
    if turnout:
        lines = []
        for label, key in (("Bajo", "low"), ("Central", "central"), ("Alto", "high")):
            expected, rate = turnout.get(f"expected_voters_{key}"), turnout.get(f"turnout_rate_{key}")
            if expected is not None and rate is not None:
                lines.append(f"{label}: {format_integer(expected)} votantes ({format_percent(rate)}).")
        sections.append("Participación\n" + "\n".join(lines) + f"\n[{turnout['citation']['title']}]\nEstimación de participación; no mide apoyo político.")
    else:
        sections.append("Participación\nNo hay una estimación de participación disponible.")

    historical = facts.get("historical") or []
    sections.append("Antecedentes\n" + ("\n".join(f"{item['year']}: {format_integer(item['ballots_cast'])} votos emitidos ({format_percent(item['turnout_rate'])}). [{item['citation']['title']}]" for item in historical) if historical else "No hay antecedentes electorales disponibles."))

    demographics = facts.get("demographics") or {}
    population = demographics.get("population")
    demo_lines = []
    if population:
        demo_lines.append(f"Población: {format_integer(population['value'])} habitantes ({population.get('reference_year', 'sin año de referencia')}). [{population['citation']['title']}]")
    for item in demographics.get("indicators", []):
        code = str(item.get("indicator_code") or "").upper()
        if code in {"POP_TOTAL", "E2E_POP_TOTAL"} or "poblaci" in item["title"].casefold() or item.get("value") is None:
            continue
        unit = str(item.get("unit") or "").upper()
        value = format_percent(item["value"]) if unit in {"PERCENT", "PERCENTAGE", "%"} else format_integer(item["value"])
        demo_lines.append(f"{item['title']}: {value}. [{item['citation']['title']}]")
    sections.append("Contexto demográfico\n" + ("\n".join(demo_lines[:6]) if demo_lines else "No hay información demográfica disponible."))

    labels = {
        "needs": ("Necesidades territoriales", "necesidades registradas"),
        "operations": ("Operación territorial", "actividades registradas"),
        "studies": ("Estudios", "estudios agregados disponibles"),
    }
    for key, (heading, noun) in labels.items():
        collection = facts.get(key) or {}
        if collection.get("count"):
            item_titles = "; ".join(f"{item['title']} [{item['citation']['title']}]" for item in collection["items"][:5])
            text = f"{format_integer(collection['count'])} {noun}. {item_titles}"
            if collection.get("demo_count"):
                text += "\nDatos simulados para demostración."
        else:
            text = f"No hay {noun}."
        sections.append(f"{heading}\n{text}")

    public = facts.get("public_info") or {}
    if public.get("count"):
        public_text = f"{format_integer(public['count'])} publicaciones o documentos recientes: " + "; ".join(f"{item['title']} [{item['citation']['title']}]" for item in public["items"][:5])
        if public.get("demo_count"):
            public_text += "\nDatos simulados para demostración."
    else:
        public_text = "No hay información pública reciente disponible."
    sections.append("Información pública\n" + public_text)
    sections.append("Limitaciones\nLa síntesis depende de la evidencia disponible y de sus fechas de corte. No constituye una predicción electoral.")
    return "\n\n".join(sections)


def render_election_day_operations(documents: list[dict[str, Any]]) -> str:
    if not documents:
        return "No hay una jornada electoral configurada para esta campaña."
    state = documents[0].get("structured_data") or {}
    status_labels = {"PREPARATION": "en preparación", "ACTIVE": "activa", "CLOSED": "cerrada"}
    sections = [
        "Estado operativo de la jornada\n"
        f"La jornada está {status_labels.get(state.get('status'), state.get('status'))}. "
        f"Cobertura de recintos: {state.get('covered_polling_places', 0)}/{state.get('total_polling_places', 0)}. "
        f"Cobertura de juntas: {state.get('covered_boards', 0)}/{state.get('total_boards', 0)}. "
        f"Personal confirmado: {state.get('personnel_confirmed', 0)}; presente: {state.get('personnel_checked_in', 0)}. "
        f"Documentación de junta recibida: {state.get('boards_with_document', 0)}/{state.get('total_boards', 0)} "
        f"(pendiente en {state.get('boards_missing_document', 0)} juntas). "
        f"[{documents[0]['title']}]"
    ]
    incidents = [d for d in documents[1:] if (d.get("structured_data") or {}).get("category")]
    if incidents:
        lines = [f"{d['title']}: {(d.get('structured_data') or {}).get('category')} ({(d.get('structured_data') or {}).get('status')}). [{d['title']}]" for d in incidents]
        sections.append("Incidencias abiertas\n" + "\n".join(lines))
    else:
        sections.append("Incidencias abiertas\nNo hay incidencias abiertas registradas.")
    missing_docs = [d for d in documents[1:] if (d.get("structured_data") or {}).get("document_status") == "MISSING"]
    if missing_docs:
        lines = [f"{d['title']}. [{d['title']}]" for d in missing_docs]
        sections.append("Documentación pendiente\n" + "\n".join(lines))
    sections.append("Limitaciones\nInformación estrictamente operativa: no incluye votos, resultados ni proyecciones electorales.")
    return "\n\n".join(sections)


def render_debate_brief(documents: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[document.get("evidence_class", "CAMPAIGN")].append(document)
    labels = {"OFFICIAL": "Evidencia oficial", "PUBLIC": "Evidencia pública", "CAMPAIGN": "Registros internos de campaña", "DEMO": "Datos simulados para demostración"}
    sections = ["Resumen factual para debate"]
    for evidence_class in ("OFFICIAL", "PUBLIC", "CAMPAIGN", "DEMO"):
        rows = groups.get(evidence_class) or []
        if not rows:
            continue
        lines = []
        for document in rows[:8]:
            data = document.get("structured_data") or {}
            values = []
            for key in ("registered_voters", "ballots_cast", "value", "mentions_count", "status", "parish_name"):
                if data.get(key) is not None:
                    value = format_integer(data[key]) if isinstance(data[key], (int, float)) else str(data[key])
                    values.append(f"{key.replace('_', ' ')}: {value}")
            excerpt = (document.get("excerpt") or "").strip()
            detail = "; ".join(values) or excerpt or "registro disponible sin detalle cuantitativo"
            lines.append(f"{document['title']}: {detail}. [{document['title']}]")
        sections.append(labels[evidence_class] + "\n" + "\n".join(lines))
    sections.append("Limitaciones\nNo incluye soluciones, promesas, predicciones ni afirmaciones sin respaldo.")
    return "\n\n".join(sections)
