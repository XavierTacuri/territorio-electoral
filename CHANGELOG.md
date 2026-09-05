# Changelog

Formato libre por área funcional, no por commit. Este archivo resume el estado acumulado del branch `fix/user-creation` (nunca antes commiteado en este ciclo) hasta la preparación del release candidate.

## 3.0.0-rc.1

### SaaS / Organizations
Organizaciones, membresías, suscripciones (plan/límite de campañas y usuarios), selector de tenant, suspensión/reactivación, aislamiento cross-organización.

### Catálogo territorial Ecuador
Importación del catálogo nacional INEC 2026 (provincias/cantones/parroquias), desactivación de parroquias no vigentes, normalización de códigos DPA.

### Datos CNE/INEC (Data Hub)
`DataImportService` genérico con perfiles canónicos (turnout, candidaturas, organizaciones políticas, registro electoral, indicadores/observaciones demográficas), `DatasetVersion` (versionado administrativo con activación/reemplazo/diff), catálogo Centro de datos, plantillas CSV descargables, rechazo de microdatos por cabecera.

### Panorama Electoral / Expediente Territorial
Análisis descriptivo de participación histórica y proyección V1 (sin predicción), expediente territorial por parroquia, mapas (MapLibre) con boundaries reales.

### Territorio IA
Router de intents, planner, retriever por tipo de fuente, políticas de seguridad (bloquea predicción de ganador, microtargeting, persuasión, ataques personales), proveedor real (OpenAI) y `fake` determinista para pruebas — nunca `fake` en producción (fail-fast).

### Encuestas y estudios territoriales
Encuestas anónimas con HMAC/deduplicación, estudios agregados (`SurveyStudy`) con importación CSV, comparador de estudios, RBAC multicantón.

### Centro de Comando
Dashboard ejecutivo con KPIs, mapa, navegación a módulos, informe accesible desde ahí.

### PWA de campo y sincronización offline
IndexedDB (`drafts`/`syncQueue`/`pendingAttachments`), borrador-primero con sincronización explícita, resolución de conflictos (`REQUIRES_REVIEW`), evidencia con sniffing por firma de bytes + checksum + idempotencia por `client_generated_id`, banner de actualización de Service Worker sin recarga automática.

### Calendario de campaña
Agenda de actividades propias + hitos electorales oficiales (solo lectura, nunca mezclados con actividades de campaña).

### Centro de Informes
Plantillas (ejecutivo, territorial por parroquia, operación, temático, electoral descriptivo, brief de debate, jornada electoral), narrativa grounded con fallback determinista, exportación PDF/XLSX, historial y descarga protegida.

### Alertas inteligentes
Reglas explicables por módulo, deduplicación por fingerprint, ciclo de vida OPEN/ACKNOWLEDGED/RESOLVED/DISMISSED, paginación real con total expuesto (corregido en este ciclo — antes se perdían alertas más allá de la página 1), orden determinista (severidad, fecha, `created_at`).

### Asistente de Debate
Brief de debate con preguntas y fuentes factuales, verificación de afirmaciones (nivel de respaldo, nunca verdadero/falso binario), bloqueo de manipulación/ataques personales.

### Modo Jornada Electoral (V1)
Recintos electorales, juntas receptoras del voto, personal asignado (con reemplazo preservando historial de check-in), cobertura, check-in online/offline vía PWA, incidencias, documentación (nunca OCR, nunca comparada contra resultados — CNE sigue siendo la única fuente de resultados oficiales). Alcance territorial del Coordinator por asignación territorial permanente **o** por asignación propia de jornada.

### Data Hub — recintos y juntas
Importación masiva de recintos/juntas vía el mismo pipeline oficial (perfiles `CANONICAL_POLLING_PLACE`/`CANONICAL_ELECTORAL_BOARD`), validación de jerarquía DPA, idempotente por código oficial.

### Seguridad
JWT corto + refresh HttpOnly con rotación y detección de reutilización, CSRF de doble envío, CSP/X-Content-Type-Options/Referrer-Policy/X-Frame-Options/Permissions-Policy, validación fail-fast de configuración de producción (secretos, CORS, hosts, proveedor IA, cookies seguras).

### Producción y consolidación
Corrección de blocker real: `docker-compose.prod.yml` no montaba volumen persistente para `evidence_artifacts` (evidencia y documentos de Jornada Electoral se perdían al reiniciar el contenedor). Simulacro de backup/restore verificado. Dos flakes de Playwright diagnosticados y corregidos de raíz (no enmascarados con reintentos). `PRODUCTION_CHECKLIST.md` nuevo.

---

Sin versiones anteriores publicadas en este archivo: es la primera vez que este branch se documenta como changelog formal.
