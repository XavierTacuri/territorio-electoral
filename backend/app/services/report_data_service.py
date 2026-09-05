from datetime import date
from app.schemas.dashboard import DashboardFilters
from app.services.dashboard_service import DashboardService
from app.models.historical import ParticipationProjectionRun, ParticipationProjectionResult, ElectoralRollSnapshot, ElectoralProcess, DataSource, DemographicObservation
from app.models.campaign import Campaign
from app.models.territory import Canton
from app.models.operational import ActivityEvidence
from app.reports.theme_catalog import THEME_LABELS, theme_match as _theme_match
from sqlalchemy import select


def _is_demo(text: str | None) -> bool:
    return bool(text) and text.startswith("[DEMO]")


def _citation(source_type, id_, title, source_name, evidence_class, url=None, deep_link=None, record_date=None):
    return {"id": str(id_), "source_type": source_type, "title": title, "source_name": source_name,
            "source_url": str(url) if url else None, "deep_link": deep_link, "evidence_class": evidence_class,
            "record_date": record_date}


def _evidence_for_activities(db, activity_ids, limit=100):
    if not activity_ids:
        return []
    return list(db.scalars(select(ActivityEvidence).where(ActivityEvidence.activity_id.in_(activity_ids), ActivityEvidence.is_active.is_(True)).order_by(ActivityEvidence.created_at.desc()).limit(limit)))


class ReportDataService:
    def __init__(self, db):
        self.db = db
        self.dashboard = DashboardService(db)

    def _filters(self, request):
        return DashboardFilters(date_from=request.date_from, date_to=request.date_to, period=request.period,
                                 parish_id=request.parish_id, community_id=request.community_id, sector_id=request.sector_id,
                                 compare_previous_period=request.include_comparisons, survey_ids=request.survey_ids or None,
                                 electoral_process_ids=request.electoral_process_ids or None,
                                 demographic_indicator_codes=request.demographic_indicator_codes or None)

    def _territorial_activity_documents(self, campaign_id, activities, citations, narrative_documents):
        for a in activities:
            demo = _is_demo(a.title)
            citations.append(_citation("TERRITORIAL_ACTIVITY", a.id, a.title, "Territorio Electoral", "DEMO" if demo else "CAMPAIGN",
                                        deep_link=f"/app/campaigns/{campaign_id}/activities/{a.id}", record_date=a.activity_date))
            narrative_documents.append({"evidence_id": str(a.id), "source_kind": "TERRITORIAL_ACTIVITY", "title": a.title,
                                         "structured_data": {"status": a.status, "activity_date": str(a.activity_date)}})

    def _need_documents(self, campaign_id, needs, citations, narrative_documents):
        for n in needs:
            demo = _is_demo(n.title)
            citations.append(_citation("CITIZEN_NEED", n.id, n.title, "Territorio Electoral", "DEMO" if demo else "CAMPAIGN",
                                        deep_link=f"/app/campaigns/{campaign_id}/needs/{n.id}", record_date=n.reported_date))
            narrative_documents.append({"evidence_id": str(n.id), "source_kind": "CITIZEN_NEED", "title": n.title,
                                         "structured_data": {"status": n.status, "priority": n.priority, "description": getattr(n, "description", None)}})

    def _evidence_documents(self, campaign_id, evidence, citations):
        for e in evidence:
            citations.append(_citation("ACTIVITY_EVIDENCE", e.id, e.title, "Territorio Electoral", "CAMPAIGN", url=e.url,
                                        deep_link=f"/app/campaigns/{campaign_id}/activities/{e.activity_id}", record_date=e.evidence_date))

    def _study_documents(self, campaign_id, studies, citations, narrative_documents):
        for s in studies:
            demo = _is_demo(s.name)
            citations.append(_citation("SURVEY_STUDY", s.id, s.name, s.pollster_name or "Encuesta", "DEMO" if demo else "CAMPAIGN",
                                        url=s.source_url, deep_link=f"/app/campaigns/{campaign_id}/survey-studies/{s.id}",
                                        record_date=s.publication_date or s.fieldwork_end_date))
            narrative_documents.append({"evidence_id": str(s.id), "source_kind": "SURVEY_STUDY", "title": s.name,
                                         "structured_data": {"sample_size": s.sample_size_total, "fieldwork_end": str(s.fieldwork_end_date)}})

    def _public_item_documents(self, campaign_id, items, citations, narrative_documents):
        for p in items:
            demo = _is_demo(p.title)
            citations.append(_citation("PUBLIC_INTELLIGENCE", p.id, p.title, p.publisher, "DEMO" if demo else "PUBLIC", url=p.url,
                                        deep_link=f"/app/campaigns/{campaign_id}/public-intelligence/{p.id}",
                                        record_date=p.published_at.date() if p.published_at else None))
            narrative_documents.append({"evidence_id": str(p.id), "source_kind": "PUBLIC_INTELLIGENCE", "title": p.title,
                                         "structured_data": {"publisher": p.publisher}})

    def _parish_enrichment(self, campaign_id, user, request, parish_row):
        from app.services.operational_service import OperationalService
        from app.services.survey_study_service import SurveyStudyService
        from app.services.public_intelligence_service import PublicIntelligenceService
        parish_id = parish_row["parish_id"]
        ops = OperationalService(self.db)
        activities = [a for a in ops.list_activities(campaign_id, user, 1, 100, parish_id=parish_id, date_from=request.date_from, date_to=request.date_to, include_inactive=False).items if a.approval_status == "APPROVED"]
        needs = ops.needs(campaign_id, user, 1, 100, parish_id=parish_id, date_from=request.date_from, date_to=request.date_to).items
        if not request.include_demo:
            activities = [a for a in activities if not _is_demo(a.title)]
            needs = [n for n in needs if not _is_demo(n.title)]
        evidence = _evidence_for_activities(self.db, [a.id for a in activities]) if request.include_evidence else []
        studies = []
        if request.include_surveys:
            studies = SurveyStudyService(self.db).list(campaign_id, user, 1, 20, status="PUBLISHED", parish_id=parish_id).items
            if not request.include_demo:
                studies = [s for s in studies if not _is_demo(s.name)]
        public_items = []
        if request.include_public_intelligence:
            public_items = PublicIntelligenceService(self.db).items(campaign_id, user, 1, 10, parish_id=parish_id).items
            if not request.include_demo:
                public_items = [p for p in public_items if not _is_demo(p.title)]
        is_demo = any(_is_demo(a.title) for a in activities) or any(_is_demo(n.title) for n in needs) or any(_is_demo(s.name) for s in studies) or any(_is_demo(p.title) for p in public_items)
        citations, narrative_documents = [], []
        self._territorial_activity_documents(campaign_id, activities, citations, narrative_documents)
        self._need_documents(campaign_id, needs, citations, narrative_documents)
        self._evidence_documents(campaign_id, evidence, citations)
        self._study_documents(campaign_id, studies, citations, narrative_documents)
        self._public_item_documents(campaign_id, public_items, citations, narrative_documents)
        bullets = [f"{len(activities)} actividades de campaña registradas en {parish_row['name']}.",
                   f"{len(needs)} necesidades territoriales registradas.",
                   f"{len(evidence)} evidencias disponibles." if request.include_evidence else "Evidencias excluidas por filtro.",
                   f"{len(studies)} estudios con cobertura parroquial." if request.include_surveys else "Encuestas excluidas por filtro."]
        return {
            "activities": [{"title": a.title, "date": a.activity_date, "status": a.status} for a in activities],
            "needs": [{"title": n.title, "status": n.status, "priority": n.priority, "reported_date": n.reported_date} for n in needs],
            "evidence": [{"title": e.title, "evidence_type": e.evidence_type, "date": e.evidence_date} for e in evidence],
            "studies": [{"name": s.name, "status": s.status, "fieldwork_end_date": s.fieldwork_end_date, "sample_size_total": s.sample_size_total} for s in studies],
            "public_items": [{"title": p.title, "publisher": p.publisher, "published_at": p.published_at.date().isoformat() if p.published_at else None} for p in public_items],
            "citations": citations, "narrative_documents": narrative_documents, "is_demo": is_demo,
            "report_kind_label": f"Informe territorial · {parish_row['name']}", "fallback_bullets": bullets, "_report_center": True,
        }

    def _electoral_descriptive_enrichment(self, campaign_id, user, request):
        studies = []
        if request.include_surveys:
            from app.services.survey_study_service import SurveyStudyService
            studies = SurveyStudyService(self.db).list(campaign_id, user, 1, 10, status="PUBLISHED").items
            if not request.include_demo:
                studies = [s for s in studies if not _is_demo(s.name)]
        is_demo = any(_is_demo(s.name) for s in studies)
        citations, narrative_documents = [], []
        self._study_documents(campaign_id, studies, citations, narrative_documents)
        bullets = [f"{len(studies)} estudios publicados disponibles como contexto." if request.include_surveys else "Encuestas excluidas por filtro.",
                   "El informe es descriptivo: no constituye predicción electoral."]
        return {"studies": [{"name": s.name, "status": s.status, "fieldwork_end_date": s.fieldwork_end_date, "sample_size_total": s.sample_size_total} for s in studies],
                "citations": citations, "narrative_documents": narrative_documents, "is_demo": is_demo,
                "report_kind_label": "Informe electoral descriptivo", "fallback_bullets": bullets, "_report_center": True}

    def _executive_report(self, campaign_id, user, request):
        from app.api.routes.participation import current_election_analysis
        campaign = self.db.get(Campaign, campaign_id)
        overview = self.dashboard.overview(campaign_id, user, self._filters(request))
        try:
            analysis = current_election_analysis(campaign_id, user, self.db)
        except Exception:
            analysis = None
        studies, public_items = [], []
        if request.include_surveys:
            from app.services.survey_study_service import SurveyStudyService
            studies = SurveyStudyService(self.db).list(campaign_id, user, 1, 5, status="PUBLISHED").items
            if not request.include_demo:
                studies = [s for s in studies if not _is_demo(s.name)]
        if request.include_public_intelligence:
            from app.services.public_intelligence_service import PublicIntelligenceService
            public_items = PublicIntelligenceService(self.db).items(campaign_id, user, 1, 5).items
            if not request.include_demo:
                public_items = [p for p in public_items if not _is_demo(p.title)]
        is_demo = any(_is_demo(s.name) for s in studies) or any(_is_demo(p.title) for p in public_items)
        citations, narrative_documents = [], []
        self._study_documents(campaign_id, studies, citations, narrative_documents)
        self._public_item_documents(campaign_id, public_items, citations, narrative_documents)
        narrative_documents.insert(0, {"evidence_id": "overview", "source_kind": "OPERATIONS_OVERVIEW", "title": "Resumen operativo de campaña", "structured_data": {"summary_text": overview.get("summary_text")}})
        bullets = [overview.get("summary_text") or "Sin resumen operativo disponible.",
                   f"{overview['territorial_coverage']['covered_parishes']} de {overview['territorial_coverage']['accessible_parishes']} parroquias con actividades completadas.",
                   f"{overview['survey_summary']['published']} encuestas publicadas." if request.include_surveys else "Encuestas excluidas por filtro."]
        return {"overview": overview, "current_election": analysis,
                "studies": [{"name": s.name, "status": s.status, "fieldwork_end_date": s.fieldwork_end_date} for s in studies],
                "public_items": [{"title": p.title, "publisher": p.publisher, "published_at": p.published_at.date().isoformat() if p.published_at else None} for p in public_items],
                "campaign_context": {"name": campaign.name, "election_name": campaign.election_name, "election_date": campaign.election_date},
                "citations": citations, "narrative_documents": narrative_documents, "is_demo": is_demo,
                "report_kind_label": "Informe ejecutivo de campaña", "fallback_bullets": bullets, "_report_center": True}

    def _operation_report(self, campaign_id, user, request):
        from app.services.operational_service import OperationalService
        ops = OperationalService(self.db)
        parish_id = request.parish_id
        activities = ops.list_activities(campaign_id, user, 1, 200, parish_id=parish_id, date_from=request.date_from, date_to=request.date_to, include_inactive=False).items
        activities = [a for a in activities if a.approval_status == "APPROVED"]
        if not request.include_demo:
            activities = [a for a in activities if not _is_demo(a.title)]
        completed = [a for a in activities if a.status == "COMPLETED"]
        upcoming = [a for a in activities if a.status in {"PLANNED", "IN_PROGRESS"}]
        needs = ops.needs(campaign_id, user, 1, 200, parish_id=parish_id, date_from=request.date_from, date_to=request.date_to).items
        if not request.include_demo:
            needs = [n for n in needs if not _is_demo(n.title)]
        needs_by_activity = {}
        for n in needs:
            needs_by_activity.setdefault(n.activity_id, 0)
            needs_by_activity[n.activity_id] += 1
        evidence = _evidence_for_activities(self.db, [a.id for a in activities]) if request.include_evidence else []
        covered_parishes = len({a.parish_id for a in activities})
        is_demo = any(_is_demo(a.title) for a in activities) or any(_is_demo(n.title) for n in needs)
        citations, narrative_documents = [], []
        self._territorial_activity_documents(campaign_id, activities, citations, narrative_documents)
        self._need_documents(campaign_id, needs, citations, narrative_documents)
        self._evidence_documents(campaign_id, evidence, citations)
        chronology = sorted([{"date": a.activity_date, "title": a.title, "status": a.status} for a in activities], key=lambda x: x["date"])
        bullets = [f"{len(completed)} actividades realizadas y {len(upcoming)} próximas en el período.",
                   f"Cobertura de {covered_parishes} parroquias.",
                   f"{len(needs)} necesidades detectadas durante la operación.",
                   f"{len(evidence)} evidencias disponibles." if request.include_evidence else "Evidencias excluidas por filtro."]
        return {"activities": [{"title": a.title, "date": a.activity_date, "status": a.status, "needs_detected": needs_by_activity.get(a.id, 0)} for a in activities],
                "completed_count": len(completed), "upcoming_count": len(upcoming), "covered_parishes": covered_parishes,
                "needs": [{"title": n.title, "status": n.status, "priority": n.priority} for n in needs],
                "evidence": [{"title": e.title, "evidence_type": e.evidence_type} for e in evidence],
                "chronology": chronology, "citations": citations, "narrative_documents": narrative_documents, "is_demo": is_demo,
                "report_kind_label": "Informe de operación territorial", "fallback_bullets": bullets, "_report_center": True}

    def _theme_evidence(self, campaign_id, user, request, theme):
        from app.services.operational_service import OperationalService
        from app.services.survey_study_service import SurveyStudyService
        from app.services.public_intelligence_service import PublicIntelligenceService
        ops = OperationalService(self.db)
        parish_id = request.parish_id
        all_needs = ops.needs(campaign_id, user, 1, 300, parish_id=parish_id, date_from=request.date_from, date_to=request.date_to).items
        needs = [n for n in all_needs if _theme_match(theme, n.title, getattr(n, "description", None))]
        all_activities = ops.list_activities(campaign_id, user, 1, 300, parish_id=parish_id, date_from=request.date_from, date_to=request.date_to, include_inactive=False).items
        activities = [a for a in all_activities if a.approval_status == "APPROVED" and _theme_match(theme, a.title, getattr(a, "description", None))]
        if not request.include_demo:
            needs = [n for n in needs if not _is_demo(n.title)]
            activities = [a for a in activities if not _is_demo(a.title)]
        evidence = _evidence_for_activities(self.db, [a.id for a in activities]) if request.include_evidence else []
        studies = []
        if request.include_surveys:
            candidates = SurveyStudyService(self.db).list(campaign_id, user, 1, 30, status="PUBLISHED", parish_id=parish_id).items
            studies = [s for s in candidates if _theme_match(theme, s.name)]
            if not request.include_demo:
                studies = [s for s in studies if not _is_demo(s.name)]
        public_items = []
        if request.include_public_intelligence:
            candidates = PublicIntelligenceService(self.db).items(campaign_id, user, 1, 30, parish_id=parish_id).items
            public_items = [p for p in candidates if _theme_match(theme, p.title, getattr(p, "summary", None))]
            if not request.include_demo:
                public_items = [p for p in public_items if not _is_demo(p.title)]
        is_demo = any(_is_demo(n.title) for n in needs) or any(_is_demo(a.title) for a in activities) or any(_is_demo(s.name) for s in studies) or any(_is_demo(p.title) for p in public_items)
        citations, narrative_documents = [], []
        self._need_documents(campaign_id, needs, citations, narrative_documents)
        self._territorial_activity_documents(campaign_id, activities, citations, narrative_documents)
        self._evidence_documents(campaign_id, evidence, citations)
        self._study_documents(campaign_id, studies, citations, narrative_documents)
        self._public_item_documents(campaign_id, public_items, citations, narrative_documents)
        return {"needs": needs, "activities": activities, "evidence": evidence, "studies": studies, "public_items": public_items,
                "is_demo": is_demo, "citations": citations, "narrative_documents": narrative_documents}

    def _thematic_report(self, campaign_id, user, request):
        theme = request.theme
        ev = self._theme_evidence(campaign_id, user, request, theme)
        needs, activities, evidence, studies, public_items = ev["needs"], ev["activities"], ev["evidence"], ev["studies"], ev["public_items"]
        label = THEME_LABELS.get(theme, theme)
        bullets = [f"{len(needs)} necesidades relacionadas con {label.lower()}.",
                   f"{len(activities)} actividades relacionadas con {label.lower()}.",
                   f"{len(studies)} estudios con contenido relacionado." if request.include_surveys else "Encuestas excluidas por filtro.",
                   f"{len(public_items)} publicaciones públicas relacionadas." if request.include_public_intelligence else "Información pública excluida por filtro."]
        return {"theme": theme, "theme_label": label,
                "needs": [{"title": n.title, "status": n.status, "priority": n.priority} for n in needs],
                "activities": [{"title": a.title, "date": a.activity_date, "status": a.status} for a in activities],
                "evidence": [{"title": e.title, "evidence_type": e.evidence_type} for e in evidence],
                "studies": [{"name": s.name, "fieldwork_end_date": s.fieldwork_end_date} for s in studies],
                "public_items": [{"title": p.title, "publisher": p.publisher} for p in public_items],
                "citations": ev["citations"], "narrative_documents": ev["narrative_documents"], "is_demo": ev["is_demo"],
                "report_kind_label": f"Informe temático · {label}", "fallback_bullets": bullets, "_report_center": True}

    def _debate_official_facts(self, campaign_id, user, request):
        from app.schemas.territory_ai import TerritoryAIIntent
        from app.services.territory_ai_facts import build_panorama_facts, format_integer, format_percent
        from app.services.territory_ai_planner import TerritoryAIQueryPlanner
        from app.services.territory_ai_prompt import provider_documents
        from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
        from app.services.territory_ai_territory import TerritoryAIResolver, TerritoryAmbiguousError
        try:
            territory = TerritoryAIResolver(self.db).resolve(campaign_id, "", request.parish_id)
        except TerritoryAmbiguousError:
            territory = None
        plan = TerritoryAIQueryPlanner().plan(TerritoryAIIntent.ELECTORAL_PANORAMA, territory)
        evidence = TerritoryAIEvidenceRetriever(self.db).retrieve(campaign_id, user, plan, "")
        panorama = build_panorama_facts(provider_documents(evidence))
        rows = []
        current_roll = panorama.get("current_roll")
        if current_roll:
            rows.append(["Padrón electoral actual", format_integer(current_roll["registered_voters"]), current_roll["citation"]["title"]])
        population = (panorama.get("demographics") or {}).get("population")
        if population:
            rows.append([f"Población ({population.get('reference_year', 'sin año de referencia')})", format_integer(population["value"]), population["citation"]["title"]])
        turnout = panorama.get("turnout")
        if turnout and turnout.get("turnout_rate_central") is not None:
            rows.append(["Participación proyectada (central)", format_percent(turnout["turnout_rate_central"]), turnout["citation"]["title"]])
        return rows

    def _debate_qa_pairs(self, label, needs, activities, evidence, studies, official_rows):
        no_evidence = "No existe información suficiente en el sistema para responder esta afirmación."
        pairs = []

        def add(question, facts, answer, sources):
            pairs.append({"question": question, "facts": facts, "answer": answer, "sources": sources})

        if activities or evidence:
            add(f"¿Qué evidencia existe sobre el estado de {label.lower()}?",
                "; ".join([a.title for a in activities[:5]] + [e.title for e in evidence[:5]]),
                f"Existen {len(activities)} actividades y {len(evidence)} evidencias registradas relacionadas con {label.lower()}.",
                "; ".join(a.title for a in activities[:3]))
        else:
            add(f"¿Qué evidencia existe sobre el estado de {label.lower()}?", "", no_evidence, "")
        if needs:
            add(f"¿Qué necesidades se han registrado en relación a {label.lower()}?", "; ".join(n.title for n in needs[:5]),
                f"Se registraron {len(needs)} necesidades territoriales relacionadas con {label.lower()}.", "; ".join(n.title for n in needs[:3]))
        else:
            add(f"¿Qué necesidades se han registrado en relación a {label.lower()}?", "", no_evidence, "")
        if official_rows:
            facts = "; ".join(f"{row[0]}: {row[1]}" for row in official_rows)
            add("¿Qué información oficial respalda estas cifras?", facts, f"Las cifras oficiales disponibles son: {facts}.",
                "; ".join(row[2] for row in official_rows))
        else:
            add("¿Qué información oficial respalda estas cifras?", "", no_evidence, "")
        if studies:
            add("¿Qué muestran los estudios o encuestas disponibles?", "; ".join(s.name for s in studies[:3]),
                f"Existen {len(studies)} estudios publicados con contenido relacionado con {label.lower()}. Los resultados son descriptivos y no constituyen predicción electoral.",
                "; ".join(s.name for s in studies[:3]))
        else:
            add("¿Qué muestran los estudios o encuestas disponibles?", "", no_evidence, "")
        return pairs

    def _debate_verification_points(self, citations):
        points = []
        for c in citations:
            if c.get("evidence_class") == "DEMO":
                points.append([c["title"], "Dato simulado para demostración; verificar antes de usar en debate."])
            elif not c.get("source_url") and not c.get("deep_link"):
                points.append([c["title"], "Sin enlace de referencia directo; verificar la fuente antes de citar."])
        return points

    def _debate_brief_report(self, campaign_id, user, request):
        theme = request.theme
        label = THEME_LABELS.get(theme, theme)
        ev = self._theme_evidence(campaign_id, user, request, theme)
        needs, activities, evidence, studies, public_items = ev["needs"], ev["activities"], ev["evidence"], ev["studies"], ev["public_items"]
        official_rows = self._debate_official_facts(campaign_id, user, request)
        qa_pairs = self._debate_qa_pairs(label, needs, activities, evidence, studies, official_rows)
        verification_points = self._debate_verification_points(ev["citations"])
        bullets = [f"{len(needs)} necesidades relacionadas con {label.lower()}.",
                   f"{len(activities)} actividades relacionadas con {label.lower()}.",
                   f"{len(studies)} estudios con contenido relacionado." if request.include_surveys else "Encuestas excluidas por filtro.",
                   "Preparación para debate: contenido estrictamente factual, sin argumentos, promesas ni predicciones."]
        return {"theme": theme, "theme_label": label, "official_rows": official_rows, "qa_pairs": qa_pairs, "verification_points": verification_points,
                "needs": [{"title": n.title, "status": n.status, "priority": n.priority} for n in needs],
                "activities": [{"title": a.title, "date": a.activity_date, "status": a.status} for a in activities],
                "evidence": [{"title": e.title, "evidence_type": e.evidence_type} for e in evidence],
                "studies": [{"name": s.name, "fieldwork_end_date": s.fieldwork_end_date} for s in studies],
                "public_items": [{"title": p.title, "publisher": p.publisher} for p in public_items],
                "citations": ev["citations"], "narrative_documents": ev["narrative_documents"], "is_demo": ev["is_demo"],
                "report_kind_label": f"Preparación para debate · {label}", "fallback_bullets": bullets, "_report_center": True, "_debate_brief": True}

    def _election_day_report(self, campaign_id, user, request):
        from app.services.election_day_service import ElectionDayService
        from app.services.exceptions import NotFoundError
        ed_service = ElectionDayService(self.db)
        try:
            op = ed_service.get_operation(campaign_id, user)
        except NotFoundError as exc:
            raise ValueError("No existe una jornada configurada para esta campaña") from exc
        coverage = ed_service.coverage(campaign_id, user)
        places = {p.id: p for p in ed_service.list_polling_places(campaign_id, user)}
        assignments = ed_service.list_assignments(campaign_id, user)
        incidents = ed_service.list_incidents(campaign_id, user)
        documents = ed_service.list_documents(campaign_id, user)
        citations, narrative_documents, chronology = [], [{"evidence_id": "coverage", "source_kind": "ELECTION_DAY", "title": "Cobertura de jornada", "structured_data": coverage}], []
        for a in assignments:
            place = places.get(a.polling_place_id)
            citations.append(_citation("ELECTION_DAY_ASSIGNMENT", a.id, f"Asignación — {place.name if place else 'recinto'}", "Territorio Electoral", "CAMPAIGN", deep_link=f"/app/campaigns/{campaign_id}/election-day/polling-places/{a.polling_place_id}"))
        incident_rows = []
        for i in incidents:
            place = places.get(i.polling_place_id)
            citations.append(_citation("ELECTION_DAY_INCIDENT", i.id, f"Incidencia — {place.name if place else 'recinto'}", "Territorio Electoral", "CAMPAIGN", record_date=i.reported_at.date() if i.reported_at else None, deep_link=f"/app/campaigns/{campaign_id}/election-day/polling-places/{i.polling_place_id}"))
            incident_rows.append({"polling_place_name": place.name if place else None, "category": i.category, "status": i.status})
            chronology.append({"date": i.reported_at.date() if i.reported_at else None, "title": f"Incidencia — {i.category}", "status": i.status})
        document_rows = []
        for d in documents:
            place = places.get(d.polling_place_id)
            citations.append(_citation("ELECTION_DAY_DOCUMENT", d.id, f"Documento — {place.name if place else 'recinto'}", "Territorio Electoral", "CAMPAIGN", deep_link=f"/app/campaigns/{campaign_id}/election-day/polling-places/{d.polling_place_id}"))
            document_rows.append({"polling_place_name": place.name if place else None, "document_type": d.document_type, "status": d.status})
        bullets = [
            f"Cobertura de recintos: {coverage['covered_polling_places']}/{coverage['total_polling_places']}.",
            f"Cobertura de juntas: {coverage['covered_boards']}/{coverage['total_boards']}.",
            f"Personal presente: {coverage['personnel_checked_in']} de {coverage['personnel_confirmed']} confirmados.",
            f"Incidencias abiertas: {coverage['open_incidents']}.",
            f"Documentos recibidos: {coverage['documents_received']}/{coverage['expected_documents']}.",
        ]
        return {
            "election_day_status": op.status, "coverage": coverage, "incidents": incident_rows, "documents": document_rows,
            "chronology": sorted(chronology, key=lambda c: c["date"] or date.min),
            "citations": citations, "narrative_documents": narrative_documents, "is_demo": False,
            "report_kind_label": "Informe de jornada electoral", "fallback_bullets": bullets, "_report_center": True, "_election_day_report": True,
        }

    def collect(self, campaign_id, user, report_type, request, template_code=None):
        if template_code == "ELECTION_DAY_REPORT":
            return self._election_day_report(campaign_id, user, request)
        if template_code == "PUBLIC_INTELLIGENCE_REPORT":
            from app.services.public_intelligence_service import PublicIntelligenceService
            service = PublicIntelligenceService(self.db)
            return {"public_intelligence": {"summary": service.summary(campaign_id, user).model_dump(mode="json"), "sources": [{"name": x.name, "publisher": x.publisher, "source_type": x.source_type, "official": x.official, "base_url": x.base_url, "last_success_at": x.last_success_at} for x in service.sources(campaign_id, user)], "publications": [x.model_dump(mode="json") for x in service.items(campaign_id, user, 1, 500, date_from=request.date_from, date_to=request.date_to).items], "methodology": "Monitoreo descriptivo con provenance; no mide favorabilidad, persuasión ni impacto electoral."}}
        if template_code == "SURVEY_STUDY_REPORT":
            from app.services.survey_study_service import SurveyStudyService
            if len(request.survey_ids) != 1: raise ValueError("El informe requiere exactamente un estudio")
            service = SurveyStudyService(self.db); study = service.get(request.survey_ids[0], user)
            if study.campaign_id != campaign_id: raise ValueError("Estudio fuera de la campaña")
            return {"survey_study": service.read(study, True).model_dump(mode="python")}
        if template_code == "CAMPAIGN_EXECUTIVE_REPORT":
            return self._executive_report(campaign_id, user, request)
        if template_code == "OPERATION_TERRITORIAL_REPORT":
            return self._operation_report(campaign_id, user, request)
        if template_code == "THEMATIC_REPORT":
            return self._thematic_report(campaign_id, user, request)
        if template_code == "DEBATE_BRIEF_REPORT":
            return self._debate_brief_report(campaign_id, user, request)
        if template_code in {"CURRENT_ELECTION_EXECUTIVE", "PARISH_TERRITORIAL_PROFILE"}:
            from app.api.routes.participation import current_election_analysis
            analysis = current_election_analysis(campaign_id, user, self.db)
            campaign = self.db.get(Campaign, campaign_id)
            run = self.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id == campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
            snapshot = self.db.get(ElectoralRollSnapshot, run.snapshot_id) if run else None
            process = self.db.get(ElectoralProcess, run.electoral_process_id) if run else None
            source_ids = set(run.historical_process_ids if run else [])
            historical_processes = list(self.db.scalars(select(ElectoralProcess).where(ElectoralProcess.id.in_(source_ids)))) if source_ids else []
            ids = {p.source_id for p in historical_processes}
            if snapshot: ids.add(snapshot.source_id)
            ids.update(self.db.scalars(select(DemographicObservation.source_id).where(DemographicObservation.is_official.is_(True)).distinct()))
            sources = list(self.db.scalars(select(DataSource).where(DataSource.id.in_(ids)))) if ids else []
            analysis["report_context"] = {
                "campaign_name": campaign.name if campaign else None,
                "canton_name": self.db.get(Canton, campaign.canton_id).name if campaign else None,
                "election_name": campaign.election_name if campaign else (process.name if process else None),
                "sources": [{"institution": s.institution, "dataset": s.dataset_name, "reference_date": s.reference_date, "reference_year": s.reference_year, "publication_date": s.publication_date, "official_url": s.official_url} for s in sources],
            }
            if template_code == "PARISH_TERRITORIAL_PROFILE":
                if request.parish_id is None: raise ValueError("La ficha territorial requiere parroquia")
                parish = next((p for p in analysis["parishes"] if p["parish_id"] == request.parish_id), None)
                if parish is None: raise ValueError("Parroquia sin análisis disponible")
                analysis["parishes"] = [parish]
                analysis["snapshot"].update({"registered_voters":parish["registered_voters_current"],"male_voters":parish["male_voters"],"female_voters":parish["female_voters"],"juntas":parish["juntas"]})
                analysis["historical"] = {year: parish.get(f"historical_{year}") or {} for year in ("2019","2023")}
                projection=parish.get("projection") or {};analysis["projection"].update({key:projection.get(key) for key in ("expected_voters_low","expected_voters_central","expected_voters_high")})
                analysis["report_context"]["parish_name"] = parish["name"];analysis["report_context"]["dpa_code"] = parish["dpa_code"]
                enrichment = self._parish_enrichment(campaign_id, user, request, parish)
                return {"current_election": analysis, **enrichment}
            enrichment = self._electoral_descriptive_enrichment(campaign_id, user, request)
            return {"current_election": analysis, **enrichment}
        filters=self._filters(request)
        overview=self.dashboard.overview(campaign_id,user,filters)
        data={"overview":overview}
        calls={"OPERATIONAL_ACTIVITY":"activity_trends","TERRITORIAL_COVERAGE":"territories","NEEDS":"needs","COMMITMENTS":"commitments","SURVEY_RESULTS":"surveys","ELECTORAL_HISTORY":"electoral_history","DEMOGRAPHIC_PROFILE":"demographics","DATA_QUALITY":"data_quality","GEOGRAPHIC_AVAILABILITY":"data_quality"}
        if report_type == "PARTICIPATION_PROJECTION":
            run=self.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
            if run:
                snapshot=self.db.get(ElectoralRollSnapshot,run.snapshot_id)
                results=list(self.db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id==run.id)))
                data["detail"]={"model_code":run.model_code,"model_version":run.model_version,"parameters":run.parameters,"snapshot_date":snapshot.snapshot_date.isoformat() if snapshot else None,"warning":"Estimación estadística de participación. No constituye pronóstico de resultados electorales ni intención de voto.","results":[{"parish_id":r.parish_id,"registered_voters":r.registered_voters,"turnout_rate_low":str(r.turnout_rate_low),"turnout_rate_central":str(r.turnout_rate_central),"turnout_rate_high":str(r.turnout_rate_high),"expected_voters_central":r.expected_voters_central,"quality":r.data_quality_status} for r in results]}
        method=calls.get(report_type)
        if method:
            fn=getattr(self.dashboard,method)
            if method=="activity_trends":data["detail"]=fn(campaign_id,user,filters,"DAY",False,None,None)
            elif method=="territories":data["detail"]=fn(campaign_id,user,filters,"PARISH",1,100,"name","asc")
            else:data["detail"]=fn(campaign_id,user,filters)
            if report_type == "ELECTORAL_HISTORY":
                run=self.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
                if run:
                    snapshot=self.db.get(ElectoralRollSnapshot,run.snapshot_id)
                    results=list(self.db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id==run.id)))
                    data["detail"]["participation_projection"]={"model_code":run.model_code,"model_version":run.model_version,"parameters":run.parameters,"snapshot_date":snapshot.snapshot_date.isoformat() if snapshot else None,"warning":"Estimación estadística de participación. No constituye pronóstico de resultados electorales ni intención de voto.","results":[{"parish_id":r.parish_id,"registered_voters":r.registered_voters,"turnout_rate_central":str(r.turnout_rate_central),"expected_voters_central":r.expected_voters_central,"quality":r.data_quality_status} for r in results]}
        else:
            data.update({"needs":self.dashboard.needs(campaign_id,user,filters),"commitments":self.dashboard.commitments(campaign_id,user,filters),"surveys":self.dashboard.surveys(campaign_id,user,filters),"quality":self.dashboard.data_quality(campaign_id,user,filters)})
        return data
