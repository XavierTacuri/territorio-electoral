# Territorio Electoral

Fases 1–10: plataforma FastAPI/PostgreSQL/PostGIS con frontend React/TypeScript, autenticación segura de navegador, módulos operativos, analítica, mapas, informes, alertas, auditoría y despliegue Nginx.

Inicio rápido: docker compose up --build -d inicia backend; docker compose --profile frontend up --build -d incluye la web en http://localhost:5173. Aplique docker compose exec api alembic upgrade head. Consulte frontend/README.md, DEPLOYMENT.md, SECURITY.md, OPERATIONS.md y E2E_TESTING.md.

Las credenciales de desarrollo se proporcionan solo mediante variables. Las fechas funcionales usan YYYY-MM-DD y se visualizan DD/MM/AAAA en America/Guayaquil. Solo se procesan datos territoriales y encuestas anónimas agregadas; no hay identificación, predicción, perfilamiento ni recomendaciones políticas.

Regla de interfaz: todo contenido visible al usuario debe estar en español. El código interno, los payloads de API y los enums persistidos pueden permanecer en inglés, pero la capa de presentación debe convertirlos en etiquetas y mensajes amigables. Los errores técnicos nunca deben mostrarse directamente y todo enum nuevo necesita un label en español antes de aparecer en la interfaz.

Backend de Territorio Electoral para gestión territorial de campañas cantonales de Ecuador. Esta fase incorpora usuarios, roles, autenticación JWT y administración básica; no incluye frontend ni módulos electorales.

## Requisitos y configuración

Requiere Docker con Compose v2. Para desarrollo local opcional, Python 3.12 o superior.

```bash
cp backend/.env.example backend/.env
```

En PowerShell: `Copy-Item backend/.env.example backend/.env`. Cambia `SECRET_KEY`, `POSTGRES_PASSWORD` e `INITIAL_ADMIN_PASSWORD` antes de usar un entorno real. Las variables nuevas son `ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_ALGORITHM` e `INITIAL_ADMIN_*`. `.env` está ignorado y excluido de la imagen Docker.

## Roles

- `ADMIN`: Administrador.
- `CANDIDATE`: Candidato.
- `CAMPAIGN_MANAGER`: Director de campaña.
- `TERRITORIAL_COORDINATOR`: Coordinador territorial.
- `ANALYST`: Analista.

Los códigos son estables, únicos y se normalizan a mayúsculas. La inicialización es idempotente y los roles inactivos no pueden asignarse.

## Guía de roles

Qué puede hacer cada rol en el producto actual (RBAC real es el backend; esto es una guía operativa):

- **CANDIDATE / CAMPAIGN_MANAGER** (roles ejecutivos de campaña): acceso completo a su(s) campaña(s) — Centro de Comando, Panorama, Inteligencia territorial, Encuestas, Territorio IA, Centro de Informes, Preparación para debate, Calendario, Actividades/Necesidades, y Jornada Electoral completa (activar/cerrar jornada, crear recintos/juntas, asignar y reemplazar personal, resolver incidencias). Ambos comparten el mismo alcance ejecutivo; `CAMPAIGN_MANAGER` además puede administrar miembros de campaña (`/campaigns/{id}/users`).
- **ANALYST**: lectura across todos los módulos de análisis de su(s) campaña(s) asignada(s), sin controles de escritura (no activa jornada, no reemplaza personal, no gestiona alertas salvo que el rol lo permita explícitamente). Puede generar informes y usar Territorio IA.
- **TERRITORIAL_COORDINATOR**: alcance limitado a su(s) parroquia(s) asignada(s) (`TerritorialAssignment`) o a los recintos donde tiene una asignación de Jornada Electoral propia. Usa la PWA de Operación de campo (actividades/necesidades offline), "Mi Jornada" (check-in, incidencias, documentos), y ve Informes/Territorio IA acotados a su parroquia. Nunca activa/cierra la jornada ni reemplaza personal.
- **ADMIN** (global/plataforma, `is_superuser` o rol `ADMIN`): acceso total a todas las organizaciones y campañas. Administra usuarios, roles, asignaciones, Data Hub (fuentes e importaciones), configuración de IA, auditoría de seguridad, calendario electoral oficial y organizaciones.
- **Organization Admin/Owner** (`OrganizationMembership.organization_role` en `OWNER`/`ADMIN`, independiente del rol de plataforma): administra su propia organización — miembros, suscripción/plan, campañas de su organización — sin necesitar una fila `CampaignUser` explícita por campaña (ver `CampaignAccessService.accessible_ids`). No accede a organizaciones ajenas.

## Mapa de producto (superficies actuales)

- **Inicio**: Centro de Comando (Dashboard); Operación de campo y Mi Jornada (solo Coordinator).
- **Análisis**: Panorama electoral, Inteligencia territorial, Encuestas y estudios, Territorio IA, Calendario de campaña, Centro de Informes, Centro de alertas, Preparación para debate, Jornada Electoral.
- **Operación**: Operación territorial, Actividades, Necesidades.
- **Administración** (según rol): Campañas, Mi organización, Centro de datos (Data Hub), Organizaciones, Usuarios, Roles, Asignaciones, Fuentes de datos, Licencia y funcionalidades, Importar CNE/INEC, Registro electoral, Límites territoriales, Importaciones, Plantillas de informes, Auditoría, Configuración de IA, Calendario electoral oficial.

`Seguimientos`/`Commitments` es dominio legacy: el backend conserva el endpoint por compatibilidad, pero no existe ninguna ruta de navegación ni enlace visible hacia él en el producto actual (0 superficie visible).

## Puesta en marcha

```bash
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scripts.create_admin
```

El script crea los cinco roles y el administrador configurado, o repara sus permisos si ya existe. Nunca modifica automáticamente una contraseña existente.

```bash
docker compose down
docker compose logs -f api
```

## Autenticación

Las contraseñas se validan (mínimo ocho caracteres, una letra y un número) y se almacenan exclusivamente como hashes Argon2. El login usa OAuth2 Password Flow y emite un JWT de acceso HS256 con `sub`, `iat`, `exp`, `type=access` y `jti`.

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=YOUR_PASSWORD"
```

El campo `username` acepta username o email. Ejemplo autenticado:

```bash
curl "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Swagger está en <http://localhost:8000/docs>. Presiona **Authorize**, introduce username y password y Swagger solicitará el token en `/api/v1/auth/login`. ReDoc está en <http://localhost:8000/redoc> y OpenAPI en <http://localhost:8000/openapi.json>.

## Usuarios

Los endpoints `/api/v1/users` requieren `ADMIN` o superusuario. Permiten crear, listar con paginación/filtros, consultar, actualizar y cambiar contraseña. Ninguna respuesta incluye hashes, contraseñas, tokens ajenos ni timestamps técnicos. `/api/v1/roles` requiere autenticación y lista roles activos.

Ejemplo de creación:

```bash
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"analista@example.com","username":"analista","first_name":"Ana","last_name":"Pérez","password":"Example123","role_codes":["ANALYST"]}'
```

## Migraciones y pruebas

```bash
docker compose exec api alembic revision --autogenerate -m "descripcion"
docker compose exec api alembic upgrade head
docker compose exec api alembic check
docker compose exec api pytest
```

La migración inicial activa PostGIS de forma segura y crea `roles`, `users` y `user_roles`. La API nunca ejecuta `create_all()`; las pruebas aisladas sí crean un esquema SQLite efímero.

## Regla de fechas

Toda fecha funcional visible se modelará como día, mes y año: `datetime.date` en Python, `Date` en SQLAlchemy, `DATE` en PostgreSQL, `date` en Pydantic y presentación futura `DD/MM/AAAA`. Solo campos técnicos internos de seguridad y auditoría, como `created_at`, `updated_at` y `last_login_at`, usan fecha y hora con zona horaria y no aparecen en respuestas visibles.

## URLs

- API: <http://localhost:8000/>
- Salud: <http://localhost:8000/api/v1/health>
- Swagger: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI: <http://localhost:8000/openapi.json>
## Fase 3: campañas, candidatos y territorio

La API incorpora los catálogos `provinces`, `cantons`, `parishes`, `communities` y `sectors`; campañas cantonales, un candidato principal por campaña, membresías de usuarios y asignaciones territoriales jerárquicas. La información territorial es agregada: no se almacenan preferencias políticas individuales, cédulas, padrones ni perfiles de probabilidad de voto.

### Territorio inicial de Gualaceo

El seed explícito crea Azuay (`01`), Gualaceo (`0103`) y estas parroquias, sin inventar comunidades o sectores:

| DPA | Parroquia | Tipo |
| --- | --- | --- |
| 010350 | Gualaceo | URBAN |
| 010352 | Daniel Córdova Toral | RURAL |
| 010353 | Jadán | RURAL |
| 010354 | Mariano Moreno | RURAL |
| 010356 | Remigio Crespo Toral | RURAL |
| 010357 | San Juan | RURAL |
| 010358 | Zhidmad | RURAL |
| 010359 | Luis Cordero Vega | RURAL |
| 010360 | Simón Bolívar | RURAL |

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scripts.seed_gualaceo
docker compose exec api python -m app.scripts.seed_gualaceo
docker compose exec api pytest
docker compose exec api alembic check
```

### Inteligencia Pública: fuentes y recuperación

Inteligencia Pública admite únicamente tres formas de incorporación de información:

1. ingreso manual;
2. RSS configurado explícitamente;
3. API configurada explícitamente.

`OFFICIAL_WEBSITE` describe el tipo institucional de una fuente; no implica scraping. Por ejemplo, `CNE_ECUADOR` usa `OFFICIAL_WEBSITE` con recuperación `MANUAL`. El producto no realiza crawling general de sitios web ni scraping HTML de redes sociales. Las integraciones futuras con redes sociales deberán usar sus APIs oficiales, OAuth y los permisos correspondientes.

### Campaña y candidato

Solo ADMIN crea o edita campañas y candidatos. Las listas y detalles verifican membresía, evitando acceso por sustitución de UUID. CANDIDATE consulta su campaña; CAMPAIGN_MANAGER gestiona membresías y asignaciones dentro de campañas asignadas; coordinadores y analistas consultan únicamente su alcance. ADMIN y superusuarios tienen alcance global.

Crear campaña:

```bash
curl -X POST http://localhost:8000/api/v1/campaigns \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Elecciones Seccionales 2027 - Gualaceo","slug":"seccionales-2027-gualaceo","canton_id":1,"office_type":"MAYOR","election_name":"Elecciones Seccionales 2027","election_date":"2027-02-14","status":"DRAFT","description":"Campaña cantonal piloto para Gualaceo"}'
```

Crear candidato principal:

```bash
curl -X POST http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/candidate \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"first_name":"Nombre","last_name":"Apellido","display_name":"Nombre Apellido","birth_date":"1980-01-01"}'
```

Asignar usuario y territorio:

```bash
curl -X POST http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/users \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":"USER_UUID"}'

curl -X POST http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/territorial-assignments \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":"USER_UUID","parish_id":1}'
```

Las columnas geográficas son opcionales: MULTIPOLYGON/POINT SRID 4326 con índices GiST. No se implementan mapas ni operaciones espaciales avanzadas. `election_date`, `start_date`, `end_date` y `birth_date` son `DATE`, se serializan `YYYY-MM-DD` y nunca contienen hora. Los timestamps técnicos permanecen fuera de schemas visibles.

## Fase 4: operación territorial

Esta fase incorpora catálogos operativos, actividades territoriales, participantes únicamente agregados, necesidades ciudadanas agregadas, compromisos, evidencias por URL y un resumen operativo determinista. No registra asistentes nominales, cédulas, contactos, preferencias políticas individuales ni perfiles de voto.

### Catálogos

Los 11 tipos de actividad son `TOUR`, `COMMUNITY_MEETING`, `DOOR_TO_DOOR`, `ASSEMBLY`, `INTERVIEW`, `PUBLIC_EVENT`, `ORGANIZATION_VISIT`, `BRIGADE`, `TRAINING`, `PRESS_EVENT` y `OTHER`.

Las 17 categorías de necesidad son `DRINKING_WATER`, `SEWERAGE`, `ROADS`, `SECURITY`, `EMPLOYMENT`, `TOURISM`, `AGRICULTURE_PRODUCTION`, `HEALTH`, `EDUCATION`, `SPORTS`, `TRANSPORT`, `SOCIAL_CARE`, `ENVIRONMENT`, `PUBLIC_SPACES`, `CONNECTIVITY`, `WASTE_MANAGEMENT` y `OTHER`.

El seed es explícito e idempotente:

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scripts.seed_gualaceo
docker compose exec api python -m app.scripts.seed_operational_catalogs
docker compose exec api python -m app.scripts.seed_operational_catalogs
docker compose exec api pytest
docker compose exec api alembic check
```

### Actividades, necesidades, compromisos y evidencias

Las rutas se anidan bajo `/api/v1/campaigns/{campaign_id}`. ADMIN opera globalmente; CAMPAIGN_MANAGER opera únicamente en campañas asignadas; TERRITORIAL_COORDINATOR solo dentro de sus asignaciones; CANDIDATE y ANALYST tienen lectura. Cada acceso valida campaña, membresía, territorio y pertenencia del recurso para evitar IDOR.

Crear una actividad:

```bash
curl -X POST "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/activities" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"activity_type_code":"COMMUNITY_MEETING","title":"Reunión comunitaria en Jadán","activity_date":"2026-08-10","status":"PLANNED","parish_id":3,"location_name":"Casa comunal"}'
```

Registrar participantes agregados:

```bash
curl -X PUT "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/activities/ACTIVITY_ID/participant-summary" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"estimated_attendees":45,"organizations_count":3,"community_leaders_count":5,"campaign_team_count":8}'
```

Registrar una necesidad; su territorio se deriva de la actividad:

```bash
curl -X POST "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/activities/ACTIVITY_ID/needs" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"need_category_code":"ROADS","title":"Mejoramiento de la vía principal","mentions_count":12,"priority":"HIGH","status":"IDENTIFIED"}'
```

Crear un compromiso y una evidencia URL:

```bash
curl -X POST "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/commitments" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Revisar propuesta vial","priority":"HIGH","status":"PENDING","due_date":"2026-08-20","parish_id":3}'

curl -X POST "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/activities/ACTIVITY_ID/evidence" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"evidence_type":"PHOTO","title":"Registro general","url":"https://example.com/evidencia.jpg","evidence_date":"2026-08-10"}'
```

El sistema solo conserva la URL y metadatos: no descarga, procesa ni almacena el archivo binario. Las bajas son lógicas.

### Resumen operativo

`GET /api/v1/campaigns/{campaign_id}/operational-summary` agrega actividades por estado, tipo y parroquia, asistentes estimados, necesidades por menciones, compromisos por estado y vencidos, y parroquias sin cobertura. Sin fechas usa el lunes de la semana actual hasta hoy. El texto descriptivo se genera mediante una plantilla determinista, sin IA, predicciones ni recomendaciones políticas.

Todas las fechas funcionales (`activity_date`, `evidence_date`, `due_date`, `completed_date`) son `DATE`/`date`, se serializan como `YYYY-MM-DD` y no incluyen hora. Los timestamps técnicos no forman parte de los schemas públicos.

## Fase 5: encuestas territoriales anónimas

La Fase 5 incorpora encuestas por campaña, secciones, preguntas configurables, opciones, publicación/cierre, respuestas anónimas y resultados agregados. No existe una entidad de encuestado y no se almacenan nombres, cédulas, teléfonos, correos, direcciones, IP, User-Agent, cookies, fingerprints, coordenadas domiciliarias ni preferencias políticas individuales identificables.

### Estados y tipos de pregunta

Las transiciones permitidas son `DRAFT -> PUBLISHED`, `DRAFT -> ARCHIVED`, `PUBLISHED -> CLOSED`, `PUBLISHED -> ARCHIVED` y `CLOSED -> ARCHIVED`. Solo un borrador permite cambios estructurales. Una encuesta publicada acepta respuestas dentro de su período; una cerrada o archivada no.

Tipos: `SINGLE_CHOICE`, `MULTIPLE_CHOICE`, `YES_NO`, `SHORT_TEXT`, `LONG_TEXT`, `INTEGER`, `DECIMAL` y `RATING`. La publicación valida secciones, preguntas, opciones, rangos y configuraciones. Los textos se tratan como texto plano, respetan longitudes y rechazan patrones evidentes de correo, teléfono o cédula antes de persistirlos.

### Anonimato, HMAC y deduplicación

`anonymous_only` permanece siempre en `true`. Una clave aleatoria opcional enviada por el cliente se procesa mediante HMAC-SHA256 y nunca se almacena en claro. Cuando `allow_multiple_submissions=false`, el hash se usa únicamente para detectar duplicados dentro de la misma encuesta. Sin clave no se promete deduplicación, evitando mecanismos invasivos como IP, User-Agent o fingerprinting.

```env
SURVEY_SUBMISSION_HMAC_SECRET=replace-with-secure-random-secret
SURVEY_MIN_AGGREGATE_RESPONSES=5
```

En producción debe reemplazarse el secreto de ejemplo. El umbral debe ser al menos 3; el valor recomendado es 5. En comparaciones territoriales, grupos por debajo del umbral devuelven `suppressed=true` y no incluyen la distribución detallada.

### Acceso

ADMIN administra cualquier campaña; CAMPAIGN_MANAGER administra encuestas de campañas asignadas; TERRITORIAL_COORDINATOR registra respuestas y consulta agregados solamente en sus territorios; ANALYST tiene lectura; CANDIDATE consulta únicamente resultados agregados. No hay endpoint público en esta fase. Todas las rutas verifican campaña, membresía, territorio y pertenencia del recurso para impedir IDOR.

### Ejemplos

Crear encuesta:

```bash
curl -X POST "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/surveys" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Encuesta de necesidades cantonales","slug":"necesidades-agosto-2026","start_date":"2026-08-10","end_date":"2026-08-31","target_scope":"CANTON","anonymous_only":true}'
```

Enviar respuesta anónima:

```bash
curl -X POST "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/surveys/SURVEY_ID/responses" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"response_date":"2026-08-15","parish_id":3,"source_channel":"FIELD","age_range":"AGE_35_44","submission_key":"random-client-generated-value","answers":[{"question_code":"MAIN_PROBLEM","selected_option_codes":["ROADS"]}]}'
```

Resultados, participación, comparación y exportación JSON:

```bash
curl "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/surveys/SURVEY_ID/results" -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
curl "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/surveys/SURVEY_ID/participation-summary" -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
curl "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/surveys/SURVEY_ID/territorial-comparison?level=PARISH&question_code=MAIN_PROBLEM" -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
curl "http://localhost:8000/api/v1/campaigns/CAMPAIGN_ID/surveys/SURVEY_ID/export-data" -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

La exportación es JSON estructurado; CSV, Excel, PDF e informes se reservan para fases futuras. Las fechas `start_date`, `end_date`, `published_date`, `closed_date` y `response_date` son exclusivamente `DATE` y se serializan como `YYYY-MM-DD`. Los timestamps técnicos y hashes nunca forman parte de los schemas visibles.

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose exec api alembic check
```

## Fase 6: datos oficiales históricos y demográficos

La Fase 6 incorpora fuentes oficiales trazables, importaciones CSV de dos pasadas, procesos y contiendas electorales, organizaciones, candidaturas públicas históricas, geografías electorales, participación, resultados por candidatura e indicadores demográficos agregados. No importa padrones, microdatos censales ni registros nominales de electores.

### Fuentes, privacidad y trazabilidad

Cada importación exige una fuente registrada con institución, conjunto, tipo, URL oficial opcional y fechas de referencia. La URL se conserva solo como referencia: el sistema nunca descarga archivos. Cada trabajo registra nombre original normalizado, tamaño, SHA-256, perfil, codificación, delimitador, conteos y usuario ejecutor. No se persiste el archivo ni su contenido completo.

Se rechazan cabeceras como `cedula`, `identificacion`, `nombres`, `apellidos`, `telefono`, `correo`, `email`, `direccion`, `fecha_nacimiento`, `persona_id`, `hogar_id` o `ip_address`. Los errores conservan únicamente una vista previa corta y enmascarada. No se admiten padrón electoral, microdatos censales, historial de voto, direcciones, contactos ni información biométrica.

### Seguridad del CSV

Solo se acepta `.csv`, hasta el tamaño configurado. Se admite UTF-8, UTF-8 con BOM y Latin-1 únicamente cuando se solicita explícitamente. Los delimitadores válidos son coma y punto y coma. El archivo se guarda bajo un nombre aleatorio en el directorio temporal del sistema y se elimina tanto al finalizar como ante error.

```env
DATA_IMPORT_MAX_FILE_MB=100
DATA_IMPORT_MAX_ERRORS=1000
DATA_IMPORT_BATCH_SIZE=1000
```

El pipeline ejecuta dos pasadas: primero valida cabeceras, tipos, fechas, territorios y consistencia; después realiza el upsert transaccional. Un error revierte todos los cambios de dominio. El checksum evita reimportaciones; `--force` repite el upsert sin duplicar filas.

### Plantillas y perfiles

Perfiles disponibles:

- `CANONICAL_ELECTORAL_PROCESS`
- `CANONICAL_POLITICAL_ORGANIZATION`
- `CANONICAL_ELECTORAL_CANDIDATE`
- `CANONICAL_ELECTORAL_TURNOUT`
- `CANONICAL_ELECTORAL_CANDIDATE_RESULT`
- `CANONICAL_DEMOGRAPHIC_INDICATOR`
- `CANONICAL_DEMOGRAPHIC_OBSERVATION`

Cabeceras canónicas:

```text
process_code,name,process_type,election_date,status,is_final
organization_code,name,short_name,organization_type,list_number,scope
process_code,office_type,contest_code,candidate_code,full_name,organization_code,list_number,ballot_order
process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final
process_code,contest_code,geography_level,geography_code,candidate_code,votes,is_final
indicator_code,name,description,category,unit,value_type
indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator
```

`column_mapping_json` o `--mapping-json` permite relacionar nombres oficiales distintos con columnas canónicas, sin inventar columnas ausentes.

### CLI

El archivo debe estar previamente descomprimido:

```bash
docker compose exec api python -m app.scripts.import_dataset \
  --dataset-type CNE_TURNOUT \
  --source-code TEST_CNE_SOURCE \
  --file /tmp/test_turnout.csv \
  --mapping-profile CANONICAL_ELECTORAL_TURNOUT \
  --validate-only
```

Para importar, retire `--validate-only`. Opciones adicionales: `--encoding`, `--delimiter`, `--mapping-json` y `--force`.

### API y analítica

Los endpoints `/api/v1/data-sources` y `/api/v1/data-imports` administran fuentes, validación, ejecución, jobs y errores. Procesos, contiendas, participación y resultados están bajo `/api/v1/electoral-processes`. Los indicadores y perfiles están en `/api/v1/demographic-indicators`, `/api/v1/demographic-observations` y `/api/v1/territories/demographic-profile`.

Los cálculos usan `Decimal` y dos decimales: participación, ausentismo, válidos, blancos, nulos, cuota compatible de candidatura y margen. Nunca se mezclan niveles en una consulta. `historical-electoral-context` cruza únicamente procesos del mismo cantón y dignidad; no genera predicciones, recomendaciones, persuadibilidad ni microsegmentación.

Las comparaciones requieren procesos, dignidad y nivel equivalentes. Geografías sin mapeo se conservan como tales: no se inventan códigos ni correspondencias.

Las fechas funcionales `publication_date`, `reference_date` y `election_date` son `DATE`; timestamps de jobs y auditoría no aparecen en respuestas normales.

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose exec api alembic check
```

## Fase 7: capa analítica para dashboard

La API consolida, sin tablas de métricas ni cachés duplicadas, la operación territorial, necesidades, compromisos, encuestas anónimas, historia electoral oficial, demografía agregada y calidad de datos. No incluye frontend, mapas, IA, predicciones, rankings políticos ni recomendaciones.

### Endpoints

Todos requieren Bearer token y acceso a la campaña:

- `GET /api/v1/campaigns/{campaign_id}/dashboard/filter-options`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/overview`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/territories`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/activity-trends`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/needs`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/commitments`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/surveys`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/electoral-history`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/demographics`
- `GET /api/v1/campaigns/{campaign_id}/dashboard/data-quality`
- `GET /api/v1/campaigns/{campaign_id}/dashboard`

### Períodos y filtros

`period` acepta `THIS_WEEK`, `LAST_7_DAYS`, `LAST_30_DAYS`, `CAMPAIGN_TO_DATE` y `CUSTOM`. El valor predeterminado es `LAST_30_DAYS`; la semana comienza el lunes. `CUSTOM` exige `date_from` y `date_to`. Todos los filtros funcionales usan `DATE` y JSON `YYYY-MM-DD`, sin horas. `compare_previous_period=true` construye el intervalo inclusivo inmediatamente anterior con igual cantidad de días.

Los filtros territoriales respetan parroquia, comunidad y sector, validan la jerarquía y aplican automáticamente las asignaciones del coordinador. Los límites son 20 encuestas, 10 procesos históricos y 50 indicadores demográficos por solicitud.

### Fórmulas

- Cobertura operativa = parroquias accesibles con actividad `COMPLETED` / parroquias activas accesibles × 100.
- Cambio porcentual = (valor actual - valor anterior) / valor anterior × 100; si el anterior es cero, el porcentaje es `null`.
- Tasa de cumplimiento = completados / (pendientes + en progreso + completados + cancelados) × 100.
- Un compromiso vence cuando está activo, tiene fecha límite anterior a la fecha de corte y permanece pendiente o en progreso.

Los porcentajes usan `Decimal`, se redondean a dos decimales y controlan división por cero. La ausencia real de datos se distingue de cero mediante estados `AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `SUPPRESSED` y `NOT_APPLICABLE`.

### Privacidad y límites

El dashboard de encuestas reutiliza `SURVEY_MIN_AGGREGATE_RESPONSES`, suprime segmentos pequeños y nunca devuelve respuestas individuales, texto abierto, hashes, IP, User-Agent o identificadores personales. Demografía e historia electoral son descriptivas y agregadas: no se correlacionan para perfilar personas o territorios, no predicen votos y no generan recomendaciones.

La calidad se expresa mediante incidencias verificables (`OK`, `WARNING`, `INCOMPLETE`, `UNAVAILABLE`, `SUPPRESSED`), nunca mediante un puntaje opaco. Las acciones sugeridas se limitan a completar o revisar datos.

### Ejecución y verificación

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose exec api alembic check
```

No se creó migración en esta fase: la auditoría confirmó índices existentes para campaña/fecha, campaña/parroquia, encuesta/fecha, contienda/geografía e indicadores territoriales.

## Fase 8: servicios geoespaciales y GeoJSON

La API incorpora capas territoriales autenticadas para futuros mapas, sin implementar frontend ni estilos visuales. Todas las geometrías utilizan WGS84 (`EPSG:4326`), con longitud antes de latitud, y se consultan mediante PostGIS. GeoJSON no incluye el objeto obsoleto `crs`.

### Capas y endpoints

- `GET /api/v1/campaigns/{campaign_id}/map/layers`
- `GET /api/v1/campaigns/{campaign_id}/map/bounds`
- `GET /api/v1/campaigns/{campaign_id}/map/boundaries`
- `GET /api/v1/campaigns/{campaign_id}/map/communities`
- `GET /api/v1/campaigns/{campaign_id}/map/sectors`
- `GET /api/v1/campaigns/{campaign_id}/map/activities`
- `GET /api/v1/campaigns/{campaign_id}/map/operational-coverage`
- `GET /api/v1/campaigns/{campaign_id}/map/needs`
- `GET /api/v1/campaigns/{campaign_id}/map/commitments`
- `GET /api/v1/campaigns/{campaign_id}/map/surveys`
- `GET /api/v1/campaigns/{campaign_id}/map/electoral-history`
- `GET /api/v1/campaigns/{campaign_id}/map/demographics`
- `GET /api/v1/campaigns/{campaign_id}/map/features/{resource_type}/{resource_id}`
- `GET /api/v1/campaigns/{campaign_id}/map/data-quality`

El catálogo informa disponibilidad real. Los límites ausentes producen `features=[]`, `data_status=MISSING` y un conteo de recursos sin geometría; nunca se inventan centroides o coordenadas.

### Bbox, simplificación y clustering

`bbox` usa `min_lon,min_lat,max_lon,max_lat` y se aplica en PostgreSQL con `ST_MakeEnvelope` y `ST_Intersects`. Los polígonos pueden simplificarse en consulta mediante `ST_SimplifyPreserveTopology`; la geometría almacenada no se modifica. El límite predeterminado se controla mediante variables de entorno.

Las actividades se agrupan determinísticamente en zoom bajo mediante `ST_GeoHash`, `ST_Collect` y `ST_Centroid`. Los clústeres contienen únicamente conteos, estados y asistentes agregados. Al superar el umbral sin clustering, la API solicita reducir el área o usar clustering.

### Capas agregadas y privacidad

Cobertura, necesidades y compromisos se agregan por parroquia con nombres neutrales. Las encuestas reutilizan `SURVEY_MIN_AGGREGATE_RESPONSES`: muestras pequeñas quedan suprimidas y nunca se convierten respuestas en puntos. No se devuelven textos abiertos, hashes, IP, User-Agent ni ubicación de encuestados. Historia electoral y demografía permanecen descriptivas; no producen predicciones, perfiles políticos o recomendaciones.

### Importación territorial GeoJSON

Se aceptan solamente `.geojson` y `.json` con un `FeatureCollection`, sin `crs`, geometrías 3D, `GeometryCollection` ni URLs remotas. Shapefile, KML, GPX y archivos comprimidos deben convertirse previamente a GeoJSON EPSG:4326 fuera del sistema.

```bash
python -m app.scripts.import_territorial_geojson \
  --source-code INEC_GUALACEO_GEOMETRY \
  --file /data/gualaceo_parishes.geojson \
  --territory-level PARISH \
  --dpa-code-property dpa_code \
  --validate-only
```

API administrativa:

- `POST /api/v1/geometry-imports/validate`
- `POST /api/v1/geometry-imports/execute`
- `GET /api/v1/geometry-imports`
- `GET /api/v1/geometry-imports/{job_id}`
- `GET /api/v1/geometry-imports/{job_id}/errors`

La importación reutiliza fuentes, jobs, errores y SHA-256. Primero valida todas las features y luego actualiza geometrías en una transacción. No crea territorios. Los temporales usan nombres aleatorios y se eliminan en `finally`. `allow_make_valid` es explícito y utiliza `ST_MakeValid` solo si el tipo final sigue siendo válido.

### Variables geográficas

```env
MAP_MAX_FEATURES=5000
MAP_MAX_POINT_FEATURES_WITHOUT_CLUSTERING=500
MAP_DEFAULT_SIMPLIFY_TOLERANCE=0.0001
MAP_MAX_SIMPLIFY_TOLERANCE=0.01
MAP_MAX_GEOJSON_BYTES=10000000
MAP_GEOMETRY_IMPORT_MAX_FILE_MB=100
MAP_CLUSTER_MIN_ZOOM=0
MAP_CLUSTER_MAX_ZOOM=22
```

Las respuestas GeoJSON mayores a 1 KB admiten GZip. Las respuestas autenticadas usan `Cache-Control: private`.

### Verificación

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose exec api alembic check
docker compose exec api alembic current
```

No fue necesaria una migración: las cinco columnas espaciales ya tenían tipo, SRID 4326 e índice GiST correctos.

## Fase 9: informes y alertas operativas explicables

La Fase 9 incorpora generación síncrona de informes agregados en PDF (ReportLab) y XLSX (OpenPyXL), almacenamiento local privado de artefactos, descargas autenticadas, expiración controlada y alertas operativas deterministas. No incorpora frontend, mensajería, tareas en segundo plano, IA, predicciones, perfilamiento ni recomendaciones políticas.

### Informes disponibles

Las plantillas del sistema cubren resumen ejecutivo, actividad operativa, cobertura territorial, necesidades, compromisos, resultados agregados de encuestas, historial electoral, perfil demográfico y calidad de datos. Los constructores reutilizan el dashboard y los servicios analíticos existentes. Las fechas funcionales usan `DATE`/`date`; PDF y XLSX las presentan como `DD/MM/AAAA`.

Los informes de encuestas respetan `SURVEY_MIN_AGGREGATE_RESPONSES`: no contienen respuestas individuales, textos abiertos, hashes, claves de envío, IP, User-Agent ni ubicación de encuestados. Los informes electorales son históricos y descriptivos; no generan predicciones ni recomendaciones.

Excel se genera únicamente como `.xlsx`, sin macros, hojas ocultas, conexiones externas ni fórmulas. Todo texto que comienza con `=`, `+`, `-` o `@` se neutraliza mediante `sanitize_excel_text` antes de escribirlo.

### Almacenamiento, descarga y limpieza

Los binarios no se guardan en PostgreSQL. `LocalReportStorage` usa nombres internos aleatorios dentro de `REPORT_OUTPUT_DIR`, rechaza traversal y enlaces simbólicos, calcula SHA-256 y aplica el límite de tamaño. `storage_key` y la ruta real nunca aparecen en la API. La descarga pasa por autorización y responde con `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`. Un artefacto expirado o desactivado responde `410` y conserva sus metadatos.

```bash
docker compose exec api python -m app.scripts.cleanup_generated_reports --dry-run
docker compose exec api python -m app.scripts.cleanup_generated_reports
```

### Alertas

Las 21 reglas iniciales detectan condiciones técnicas en operaciones, compromisos, encuestas, importaciones, datos electorales, demografía, geometría y calidad. La evaluación es manual, síncrona y explicable. Cada alerta usa un fingerprint SHA-256 estable para deduplicar; una condición repetida actualiza `last_seen_date`, una condición desaparecida se resuelve y una condición reaparecida se reabre. Los estados son `OPEN`, `ACKNOWLEDGED`, `RESOLVED` y `DISMISSED`; cada acción conserva historial con fecha funcional.

Las alertas contienen evidencia agregada y mensajes neutrales. No existen expresiones SQL/Python configurables, puntajes opacos, recomendaciones políticas ni clasificación electoral. ADMIN y CAMPAIGN_MANAGER pueden descartar; ANALYST puede evaluar y reconocer; CANDIDATE solo consulta; TERRITORIAL_COORDINATOR queda limitado a sus territorios.

### API principal

```text
GET   /api/v1/report-templates
POST  /api/v1/campaigns/{campaign_id}/reports/generate
GET   /api/v1/campaigns/{campaign_id}/reports
GET   /api/v1/campaigns/{campaign_id}/reports/{report_run_id}/download
DELETE /api/v1/campaigns/{campaign_id}/reports/{report_run_id}
POST  /api/v1/campaigns/{campaign_id}/alerts/evaluate
GET   /api/v1/campaigns/{campaign_id}/alerts
GET   /api/v1/campaigns/{campaign_id}/alerts/summary
POST  /api/v1/campaigns/{campaign_id}/alerts/{alert_id}/acknowledge
POST  /api/v1/campaigns/{campaign_id}/alerts/{alert_id}/resolve
POST  /api/v1/campaigns/{campaign_id}/alerts/{alert_id}/dismiss
```

### Configuración

```env
REPORT_OUTPUT_DIR=/app/generated-reports
REPORT_MAX_FILE_MB=50
REPORT_MAX_ROWS=50000
REPORT_ARTIFACT_RETENTION_DAYS=30
REPORT_MAX_ACTIVE_ARTIFACTS_PER_CAMPAIGN=100
REPORT_MAX_SELECTED_SURVEYS=20
REPORT_MAX_SELECTED_PROCESSES=10
REPORT_MAX_SELECTED_INDICATORS=50
REPORT_PDF_MAX_TABLE_ROWS=5000
ALERT_MAX_OPEN_PER_CAMPAIGN=1000
ALERT_DEFAULT_INACTIVITY_DAYS=14
ALERT_DEFAULT_DATA_STALE_DAYS=365
```

### Migración, seed, CLI y pruebas

La revisión `88caa938c6b8` depende de `12cff41d3836` y crea las seis tablas de informes y alertas. El seed es transaccional e idempotente.

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scripts.seed_reports_and_alerts
docker compose exec api python -m app.scripts.seed_reports_and_alerts
docker compose exec api python -m app.scripts.generate_report --campaign-id CAMPAIGN_UUID --template-code CAMPAIGN_EXECUTIVE_SUMMARY --format PDF --report-date 2026-08-03 --date-from 2026-07-05 --date-to 2026-08-03
docker compose exec api python -m app.scripts.evaluate_alerts --campaign-id CAMPAIGN_UUID --as-of-date 2026-08-03
docker compose exec api pytest
docker compose exec api alembic check
```

No se programan automáticamente informes, alertas ni limpieza. Esa orquestación queda fuera de esta fase.

## Fase final: SaaS, Centro de Comando, Expediente Territorial, PWA, Centro de Informes y Asistente de Debate

Fases construidas después de Fase 9 y nunca documentadas en este README hasta esta consolidación (todas ya cubiertas por la suite de pruebas):

- **SaaS / Organizations**: `Organization`, `OrganizationMembership` (`OWNER`/`ADMIN`/`MEMBER`), `OrganizationSubscription` (plan, límite de campañas/usuarios), selector de tenant en la UI, suspensión/reactivación de organización. Un Org Admin/Owner accede a todas las campañas de su organización sin necesitar una fila `CampaignUser` explícita (`CampaignAccessService.accessible_ids`).
- **Catálogo territorial Ecuador**: importación del catálogo nacional INEC 2026 (`import_territorial_catalog.py`, `territorial_catalog_service.py`), desactivación idempotente de parroquias ya no vigentes.
- **Centro de Comando** (`/app/campaigns/{id}/dashboard`): KPIs ejecutivos, mapa (`CommandCenterMap.tsx`, coropletas por parroquia), accesos directos a los demás módulos.
- **Expediente Territorial** (`/app/campaigns/{id}/territories` → detalle por parroquia): ficha narrativa combinando participación histórica, demografía, encuestas y actividad de campaña para una parroquia.
- **PWA de campo** (`/app/campaigns/{id}/field`, rol `TERRITORIAL_COORDINATOR`): registro de actividades/necesidades sin conexión, evidencia fotográfica (sniffing por firma + checksum + idempotencia por `client_generated_id`), cola de sincronización explícita (nunca automática ni oculta), resolución de conflictos `REQUIRES_REVIEW`. Cierre estructurado de actividades con motivo de suspensión.
- **Centro de Informes** (`/app/campaigns/{id}/reports`): plantillas ejecutiva, territorial por parroquia, operación territorial, temática, electoral descriptiva, brief de debate y jornada electoral; narrativa "grounded" con fallback determinista sin proveedor de IA; exportación PDF/XLSX con almacenamiento y descarga protegida (`nosniff`, sin URL pública).
- **Asistente de Debate** (`/app/campaigns/{id}/debate`): brief de preguntas con fuentes factuales y verificación de afirmaciones devolviendo un nivel de respaldo (nunca verdadero/falso binario); bloquea solicitudes de manipulación o ataques personales.
- **Configuración de IA** (`/app/admin/ai-configuration`, solo `ADMIN`): selección de proveedor (`unavailable`/`fake`/`openai`), prueba con `FakeProvider`; `fake` está bloqueado en producción por validación de arranque (`Settings.__init__` falla rápido).

## Modo Jornada Electoral

Centro operativo del día de la elección: recintos electorales, juntas receptoras del voto, personal asignado, cobertura, check-in (online y offline vía PWA), incidencias y documentación recibida (nunca OCR'ed, nunca comparada contra resultados). **Nunca es un sistema de conteo de votos**: los resultados oficiales siguen viniendo exclusivamente de CNE/Ecuador Data Hub.

- Modelo: `ElectionDayOperation` (una fila mutable por campaña+proceso, transiciona `PREPARATION → ACTIVE → CLOSED`), `PollingPlace`/`ElectoralBoard` (llave por `electoral_process_id`, no por campaña — infraestructura compartida entre campañas del mismo cantón/proceso), `ElectionDayAssignment` (check-in vive en la misma fila; un reemplazo marca la fila original `REPLACED` preservando su check-in), `ElectionDayIncident`, `ElectionDayDocument`.
- UI: `/app/campaigns/{id}/election-day` (Command Center: KPIs, mapa operativo, activar/cerrar jornada), `/election-day/polling-places/{id}` (detalle: juntas, personal, reemplazo, incidencias, documentos), `/election-day/my` (PWA "Mi Jornada" para el Coordinator asignado — check-in, incidencia, documento, siempre borrador-primero con sincronización explícita).
- RBAC: activar/cerrar jornada y reemplazar personal requieren rol ejecutivo (`CANDIDATE`/`CAMPAIGN_MANAGER`) o `ADMIN`. El alcance territorial del Coordinator se calcula por `TerritorialAssignment` **o** por sus propias asignaciones de jornada (`ElectionDayAssignment`) — un delegado asignado solo para el día opera su propio recinto sin necesitar una asignación territorial permanente.
- Alertas: `ELECTION_PLACE_UNCOVERED`, `BOARD_UNCOVERED`, `ASSIGNED_PERSON_NOT_CHECKED_IN`, `OPEN_ELECTION_INCIDENT`, `BOARD_DOCUMENT_MISSING`, `OFFLINE_SYNC_FAILURE`. Territorio IA: intent `ELECTION_DAY_OPERATIONS`, estrictamente factual (nunca predicción/ventaja). Centro de Informes: plantilla `ELECTION_DAY_REPORT` ("Informe de jornada electoral").
- Migración `20260908_0001` crea las tablas; `20260908_0002` añade `ELECTION_DAY` a `report_templates.report_type`.

### Data Hub — recintos y juntas

Los recintos/juntas pueden cargarse en masa vía el mismo pipeline de importación oficial (`DataImportService`), no un importador aparte:

- Dataset types: `CNE_POLLING_PLACES` (perfil `CANONICAL_POLLING_PLACE`), `CNE_ELECTORAL_BOARDS` (perfil `CANONICAL_ELECTORAL_BOARD`). Migración `20260909_0001` los agrega al `CHECK` de `data_sources.dataset_type`.
- Columnas CSV de recintos: `process_code,province_dpa,canton_dpa,parish_dpa,polling_place_code,polling_place_name,polling_place_address,polling_place_latitude,polling_place_longitude` (address/lat/lng llevan el prefijo `polling_place_` para no colisionar con `FORBIDDEN_HEADERS`, que ya bloquea `address`/`latitude`/`longitude` a secas por microdatos). Columnas de juntas: `process_code,polling_place_code,board_code,board_number,sex_category,registered_voters`.
- Validación: jerarquía provincia⊃cantón⊃parroquia, coordenadas en rango, códigos duplicados dentro del archivo, junta requiere un recinto ya importado para el mismo proceso. Idempotente por código oficial (upsert), checksum de archivo bloquea reimportar el mismo CSV sin `force`.
- UI: Administración → Centro de datos → catálogo → "Recintos electorales"/"Juntas receptoras del voto" → Nueva importación (`/app/admin/official-data/election-day/polling-places` y `.../boards`), reutilizando el mismo componente de importación simple (fuente → CSV → validar → ejecutar → plantilla descargable) que el resto de perfiles CNE/INEC.

```bash
docker compose exec api alembic upgrade head
docker compose exec api pytest tests/test_election_day.py tests/test_data_hub_polling_places.py -q
```
