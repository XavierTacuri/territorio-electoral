# Arquitectura de producción AWS — target (Fase 4B)

Este documento describe el **destino** de la infraestructura AWS para Territorio Electoral. Fase 4A (este ciclo) preparó la *aplicación* para poder desplegarse así — introdujo `ARTIFACT_STORAGE_PROVIDER=s3`, la subida directa de evidencia a S3 y las credenciales vía IAM — pero **no creó ningún recurso AWS real**. Nada aquí existe todavía. Todos los identificadores (ARNs, nombres de bucket, dominios) son placeholders.

Fase 4B provisiona los recursos descritos aquí (Terraform). Fase 4C mide carga real y decide si Redis/SQS/RDS Proxy hacen falta — no se anticipan sin evidencia (§51 Fase 4A).

## Diagrama de flujo objetivo

```
Internet
   │
   ▼
CloudFront + WAF  ──────────────► S3 (frontend estático, build de Vite)
   │
   │ /api/*
   ▼
ALB (HTTPS, certificado ACM)
   │
   ▼
ECS/Fargate — servicio "api" (>= 2 tasks, Auto Scaling)
   │                                   │
   │ SQL (RDS Proxy)                   │ S3 API (SDK boto3, vía IAM Task Role)
   ▼                                   ▼
RDS Proxy ──► RDS PostgreSQL/PostGIS   S3 privado (evidencia, actas, informes)
   (Multi-AZ)                             │
                                           │ GET/POST presigned
                                           ▼
                                      Navegador / PWA del Delegado

Secrets Manager ──► credenciales DB/JWT/HMAC inyectadas como variables de entorno del task
CloudWatch ──► logs (stdout JSON de cada task), métricas, alarms
```

`FastAPI`/navegador hablan con S3 de dos formas, ambas ya implementadas en Fase 4A:

- **Server-side** (`app/services/artifact_storage.py::S3ArtifactStorage`): la API escribe informes generados y evidencia subida vía proxy (`ActivityEvidence`, `ElectionDayDocument`) directamente al bucket con `put_object`, y autoriza descargas devolviendo un redirect 307 a una URL GET firmada de corta duración — nunca transporta los bytes.
- **Cliente directo** (actas electorales únicamente): el Delegado sube la fotografía del acta directo desde el navegador al bucket vía un POST firmado (`presigned POST`) que la API autoriza pero nunca intermedia — ver `docs del flujo` en `app/services/election_act_service.py::create_upload_intent`/`complete_upload`.

## Componentes (todos placeholder hasta Fase 4B)

| Componente | Rol | Notas |
|---|---|---|
| CloudFront + WAF | CDN + reglas de bloqueo (rate limiting, IP reputation) delante del frontend y del ALB | Certificado ACM, HSTS |
| S3 (frontend) | Build estático de `npm run build` | Bucket separado del bucket de artifacts; público solo vía CloudFront (OAC), nunca directo |
| ALB | Balanceo HTTPS hacia las tasks `api` | Health check contra `/api/v1/ready` |
| ECS/Fargate | Ejecuta el contenedor `api` (mismo `backend/Dockerfile` de hoy) | ≥2 tasks; ninguna task comparte filesystem — por eso `ARTIFACT_STORAGE_PROVIDER=s3` es obligatorio aquí |
| ECS release task | Corre `alembic upgrade head` una sola vez antes de que el servicio escale | Reemplaza el `CMD` actual del Dockerfile en este entorno (ver nota en `backend/Dockerfile`, §31) |
| RDS Proxy | Pooling de conexiones hacia RDS | Fase 4B; hoy la app ya usa `pool_pre_ping=True`/pool propio de SQLAlchemy sin asumir un proxy |
| RDS PostgreSQL/PostGIS Multi-AZ | Base de datos, única fuente de verdad de metadata (incluida la de cada artifact) | Igual esquema que hoy; Fase 4A no requirió migración |
| S3 (artifacts) | Bucket privado de evidencia/actas/informes | Ver detalle abajo |
| Secrets Manager | `SECRET_KEY`, `BROWSER_REFRESH_TOKEN_HMAC_SECRET`, `SURVEY_SUBMISSION_HMAC_SECRET`, credenciales DB | Inyectados como env vars del task, nunca en la imagen |
| CloudWatch | Logs (el JSON estructurado que ya emite `app.core.observability`), métricas, alarms | `request_id` por línea ya viaja en cada log hoy |

## Arquitectura del bucket S3 de artifacts

- **Privado**: Block Public Access activado en las 4 opciones, sin excepción. Ninguna ACL `public-read`, nunca.
- **Versioning**: activado — protege contra un `delete_object` erróneo; el ciclo de vida (ítem siguiente) gestiona el costo.
- **Encryption**: SSE-S3 (`AES256`) por defecto, o SSE-KMS con una CMK dedicada si el requisito de cumplimiento lo exige (`S3_SSE_MODE=aws:kms` + `S3_KMS_KEY_ID`). Bucket policy debe **denegar** cualquier `PutObject` sin el header de cifrado correspondiente.
- **Prefijos**: `evidence/`, `reports/` (configurables vía `S3_EVIDENCE_PREFIX`/`S3_REPORT_PREFIX`). Dentro de `evidence/`, la subida directa de actas usa `evidence/pending/` mientras el objeto no ha sido verificado por `/evidence/complete`, y `evidence/final/` una vez promovido — la promoción es un `copy_object` server-side seguido de `delete_object` del pendiente (nunca al revés).
- **Lifecycle (pendiente, Fase 4B)**: una regla de expiración sobre `evidence/pending/*` (por ejemplo, 24-48h) limpia objetos huérfanos de intents nunca completados — la separación de prefijo ya existe en Fase 4A precisamente para que esta regla sea trivial de añadir sin tocar código de aplicación.
- **Retention de reportes (pendiente, Fase 4B)**: una regla de expiración sobre `reports/*` alineada con `REPORT_ARTIFACT_RETENTION_DAYS` (hoy la retención la aplica la aplicación marcando `is_available=false`; una regla de bucket sería una segunda capa, no la fuente de verdad).
- **CORS**: exacto para el dominio de la app —
  ```json
  [{"AllowedOrigins": ["https://app.example.invalid"], "AllowedMethods": ["GET", "POST"], "AllowedHeaders": ["*"], "MaxAgeSeconds": 300}]
  ```
  Sin `"*"` en `AllowedOrigins` nunca en producción.
- **IAM least privilege — ECS Task Role**: solo `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:CopyObject`, `s3:HeadObject` sobre `arn:aws:s3:::<bucket>/evidence/*` y `arn:aws:s3:::<bucket>/reports/*` (placeholder — sustituir por el ARN real). Nunca `s3:*`, nunca `Resource: "*"`.
- **CloudTrail data events (opcional, Fase 4B+)**: si se habilita auditoría a nivel de objeto, filtrar por el bucket de artifacts; evaluar el costo contra el valor real antes de activarlo — no se activa por defecto.

## Lo que Fase 4A ya deja listo para este target — IMPLEMENTADO

- `ARTIFACT_STORAGE_PROVIDER=s3` + `AWS_REGION`/`S3_ARTIFACT_BUCKET`/prefijos/timeouts/SSE — toda la configuración de este documento tiene ya un `Settings` validado (`backend/app/core/config.py`) y una fábrica (`app/services/artifact_storage_factory.py`) que la aplica sin tocar el código de los servicios.
- Credenciales exclusivamente vía el credential provider chain estándar de boto3 (`app/services/s3_client.py`) — en ECS, la IAM Task Role de la tabla anterior es lo único que hace falta configurar; la aplicación no tiene ningún campo para una access key estática.
- El flujo de subida directa de actas (`upload-intent` → POST firmado → `complete`) ya implementa exactamente el prefijo `pending/`→`final/` que la regla de lifecycle de arriba necesita.
- Los cuatro endpoints de descarga de artifacts (evidencia de actividad, documento de jornada, evidencia de acta, informe) ya devuelven un redirect a URL firmada cuando `provider=s3`, nunca transportan el archivo por FastAPI.
- **Integridad real del objeto subido**: el POST firmado exige `x-amz-checksum-sha256` (el checksum aditivo nativo de S3, no metadata declarativa) — S3 calcula el hash de los bytes que realmente recibe y rechaza el upload si no coincide con lo declarado, antes de almacenar nada. `complete()` vuelve a leer ese checksum vía `HEAD ... ChecksumMode=ENABLED` y lo compara contra el token — nunca confía en un valor que el cliente pueda afirmar independientemente de los bytes que subió, y nunca descarga el objeto completo para re-hashearlo.
- **Estado de la evidencia sin columna nueva**: `ElectionActEvidence` no tiene (ni necesita) un estado `PENDING`/`READY` explícito — la fila solo se crea dentro de `complete()`, después de validar el checksum y promover `pending/`→`final/`. Un objeto en `evidence/pending/` nunca cuenta como evidencia (no hay fila que lo referencie), y `submit_revision` exige al menos una `ElectionActEvidence` persistida — por construcción, nunca puede enviarse una revisión respaldada solo por un objeto pendiente sin confirmar. No se agregó migración por este motivo.

## Alcance real de los tests "multi-instancia" de Fase 4A

`test_artifact_storage_multi_instance.py` prueba que dos objetos `S3ArtifactStorage` construidos de forma completamente independiente (cliente boto3 propio, Stubber propio) pueden operar sobre el mismo `storage_key` sin compartir nada más que el nombre del bucket — es decir, que la arquitectura **no asume** filesystem compartido a nivel de la clase de storage. `test_election_act_evidence_race_postgres.py` va un paso más allá y prueba la resolución de la carrera de `complete()` contra PostgreSQL real (no SQLite), con dos conexiones/hilos genuinamente concurrentes.

Ninguno de los dos es el multi-instancia real de Fase 4B: no se levantaron dos procesos FastAPI distintos, no hay ALB, no hay dos tasks ECS reales sirviendo tráfico. Son evidencia de que el diseño es compatible con esa topología, no una prueba de la topología en sí — eso corresponde a Fase 4B, con recursos AWS reales.

## Lo que Fase 4B debe hacer (no incluido en este ciclo)

- Terraform para cada recurso de la tabla anterior.
- La ECS release task que separa `alembic upgrade head` del arranque de cada réplica (ver nota en `backend/Dockerfile`).
- Las reglas de lifecycle de S3 descritas arriba.
- RDS Proxy y la migración de `docker-compose.prod.yml`/Render hacia ECS.
- Terminación TLS real (ACM) y HSTS delante del ALB/CloudFront — hoy `frontend/nginx.conf` asume que esto lo añade un terminador externo, igual que en Render.

## Lo que Fase 4C decide, no antes

Redis, SQS, y cualquier infraestructura de colas/cache: el dominio ya usa constraints/locks de base de datos para la concurrencia crítica (por ejemplo, el `UNIQUE` de `(operation, board, contest)` en actas). No se introduce infraestructura adicional por anticipación — primero se mide carga real contra el target de arriba.
