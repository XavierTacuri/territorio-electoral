# Runbook operativo de producción — Territorio Electoral (Fase 4C.7)

Este documento es el manual operativo para preparar, desplegar, validar, operar y recuperar la infraestructura AWS de Territorio Electoral descrita en `infra/terraform/` (Fase 4C.1-4C.6). Complementa, sin duplicar, la documentación de arquitectura ya existente:

- [`TERRAFORM_FOUNDATION.md`](./TERRAFORM_FOUNDATION.md) — red y security groups.
- [`ECS_ALB_FOUNDATION.md`](./ECS_ALB_FOUNDATION.md) — ECS/Fargate + ALB, estrategia de migraciones.
- [`RDS_PROXY_FOUNDATION.md`](./RDS_PROXY_FOUNDATION.md) — RDS, RDS Proxy, separación de identidades, bootstrap.
- [`WAF_CLOUDWATCH_FOUNDATION.md`](./WAF_CLOUDWATCH_FOUNDATION.md) — WAF, alarmas, dashboard.
- [`BACKUP_DR_FOUNDATION.md`](./BACKUP_DR_FOUNDATION.md) — S3 lifecycle, backup/DR, matriz de incidentes, RPO/RTO.
- [`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md) — estado de preparación, matriz y blockers (léase junto con este documento antes de cualquier despliegue real).
- [`AWS_BOOTSTRAP.md`](./AWS_BOOTSTRAP.md) — remote state, ECR, modelo IAM y procedimiento de migración del backend (Fase 4D.1, precede a cualquier `apply` de este stack).
- [`../performance/PERFORMANCE_BASELINE.md`](../performance/PERFORMANCE_BASELINE.md) / [`../performance/LOAD_STRESS_TESTING.md`](../performance/LOAD_STRESS_TESTING.md) — evidencia detrás del dimensionamiento.

**Estado de esta infraestructura al momento de escribir este runbook: ningún recurso de AWS existe todavía.** Todo lo de abajo se ha validado mediante `terraform fmt`/`init -backend=false`/`validate`, Docker Compose local y CI — nunca contra AWS real (ver `PRODUCTION_READINESS.md`, "Qué significa 'validado' en este documento"). Los procedimientos que requieren `terraform plan`/`apply`/`destroy` o el AWS CLI contra recursos reales están marcados explícitamente como **no ejecutados todavía** — este runbook describe el procedimiento a seguir cuando se autorice el primer despliegue real, no confirma que ya ocurrió.

### IAM — quién puede hacer qué (referencia rápida)

- **Backend runtime** (`aws_ecs_service.backend`) → Task Role `backend_task` → S3 mínimo privilegio (`evidence/*`, `reports/*` del bucket de artifacts) — nunca más.
- **`backend_migrate`/`backend_bootstrap`** (tasks de un solo uso, §6) → mismo Task Role `backend_task` + Execution Role `backend` con acceso a los secretos maestro/aplicación de DB.
- **Frontend runtime** (`aws_ecs_service.frontend`) → **sin Task Role** (nginx estático, cero permisos AWS de aplicación) y Execution Role propio (`frontend_execution`) sin acceso a ningún secreto de DB.

Detalle completo y tabla de roles en `PRODUCTION_READINESS.md`, "Arquitectura de Task Roles".

---

## 1. Prerrequisitos previos a producción (Pre-Production Prerequisites)

Checklist explícito, correspondiente a **BEFORE FIRST PRODUCTION STACK APPLY** — el `terraform apply` de `infra/terraform/environments/prod/`, que presupone que el `apply` del bootstrap (`infra/terraform/bootstrap/`, distinto y anterior) ya se ejecutó y verificó. Ver `AWS_BOOTSTRAP.md` §25 para la lista separada de prerrequisitos **BEFORE AWS BOOTSTRAP APPLY** — no se repite aquí. Nada de esta lista está marcado como completado salvo que exista evidencia verificable en el repositorio — ver `PRODUCTION_READINESS.md`, "Blockers reales — tres momentos distintos", para el estado real y exhaustivo de cada ítem.

| # | Prerrequisito | Cómo se verifica |
| --- | --- | --- |
| 1 | Cuenta AWS lista, con billing/soporte configurado | Fuera del repositorio — confirmación operativa externa |
| 2 | Región AWS decidida | `aws_region` en `terraform.tfvars` (default `us-east-1`, `terraform.tfvars.example`) |
| 3 | Permisos IAM del operador que ejecutará `plan`/`apply` | Rol/usuario IAM con permisos suficientes sobre VPC/ECS/RDS/WAF/CloudWatch/Secrets Manager — no documentado como policy en este repo (es el operador, no la aplicación) |
| 4 | Terraform compatible instalado | `>= 1.11.0` (piso real, ver `RDS_PROXY_FOUNDATION.md` — requerido por `ephemeral`/`secret_string_wo`) |
| 5 | Remote Terraform state resuelto | **NO resuelto — BLOCKER**, ver §2 |
| 6 | Dominio decidido | No configurado — `frontend_origins`/`browser_allowed_origins`/`trusted_hosts` sin valor en `terraform.tfvars.example` |
| 7 | Certificado ACM disponible | No configurado — `certificate_arn = ""` por defecto → solo HTTP (ver §16 de la auditoría, PRE-PRODUCTION REQUIREMENT) |
| 8 | Imágenes de contenedor inmutables disponibles en un registry | `backend_image`/`frontend_image` sin default — deben apuntar a un tag/digest real antes de cualquier `apply` |
| 9 | Bucket de artifacts S3 confirmado | `s3_artifact_bucket` sin default — obligatorio con `artifact_storage_provider = "s3"` |
| 10 | Ownership del bucket confirmado | Las 3 variables de `modules/s3_lifecycle` (`s3_lifecycle_management_enabled`, `s3_bucket_configuration_managed_by_this_stack`, `s3_bucket_dedicated_to_project`) en `false` por defecto — deben confirmarse explícitamente antes de activarlas |
| 11 | Secrets Manager preparado | `secrets_manager_secret_arns` (SECRET_KEY, HMAC secrets) vacío por defecto — deben crearse y referenciarse antes de `apply` |
| 12 | Parámetros de producción revisados | Ver §12 de la auditoría (ECS sizing) — perfil RECOMMENDED de Fase 4C.6 ya aplicado en `terraform.tfvars.example` |
| 13 | Decisión de RDS Multi-AZ tomada | `db_multi_az = false` por defecto — decisión de costo/disponibilidad explícita, pendiente de confirmación de negocio |
| 14 | Destino de alertas (SNS) decidido | `create_alarm_sns_topic = false`, `alarm_sns_topic_arn = ""` — sin notificación real configurada |
| 15 | Modo WAF revisado | `waf_managed_rules_count_mode = true` (Count, no bloquea) — revisar antes de Enforce, ver §6 |
| 16 | Estrategia de backups revisada | `db_backup_retention_period = 7`, `db_skip_final_snapshot = false` — revisar si el negocio requiere otra ventana |
| 17 | Costos aprobados | Ver tablas de costo en cada `docs/aws/*_FOUNDATION.md` — sin aprobación registrada en este repositorio (decisión externa) |

No se marca ningún ítem como "completado" en este documento salvo los que tienen evidencia de código citada arriba — el resto requiere una decisión humana externa al repositorio.

---

## 2. Remote Terraform state — BLOCKER BEFORE REAL PRODUCTION APPLY

**Fase 4D.1 ya preparó, en código, la solución descrita en esta sección** — ver [`AWS_BOOTSTRAP.md`](./AWS_BOOTSTRAP.md) para el detalle completo (bucket S3 dedicado, versioning, SSE-S3, Public Access Block, `SecureTransport`, `prevent_destroy`, locking nativo `use_lockfile`, backend parcial `backend "s3" {}` ya en `environments/prod/versions.tf`). **Nada de eso existe todavía en AWS** — el punto sigue siendo blocker hasta que el bootstrap se aplique y se verifique, y hasta que la migración descrita en `AWS_BOOTSTRAP.md` (§9) se ejecute.

**Estado actual: el state es local.** No existe ningún bloque `backend` en `infra/terraform/environments/prod/versions.tf` ni en ningún otro `.tf` del repositorio — confirmado por búsqueda explícita. Esto es deliberado durante la fase de validación (permite `terraform init -backend=false` sin credenciales AWS), pero es un **bloqueador real antes de cualquier `apply` contra AWS**: producción no debe depender de un `terraform.tfstate` en la máquina de una sola persona.

**Requisitos mínimos del backend remoto a implementar antes del primer `apply` real** (la decisión del proveedor/recurso concreto queda pendiente — no se inventa aquí):

- **Almacenamiento remoto** — el state debe vivir fuera de cualquier máquina individual.
- **Cifrado** — en reposo, como mínimo con las claves gestionadas por el proveedor de almacenamiento elegido.
- **Versionado** — para poder recuperar una versión anterior del state ante una corrupción o un `apply` erróneo.
- **Locking** — para evitar dos `apply` concurrentes sobre el mismo state (condición de carrera real, no hipotética — ver la corrupción de `node_modules` documentada en este mismo ciclo de auditoría como ejemplo de lo que pasa cuando dos procesos escriben sobre el mismo estado compartido sin coordinación).
- **Control de acceso** — restringido a quienes deban ejecutar `plan`/`apply`, nunca abierto al mismo nivel que el bucket de artifacts de usuarios (`BACKUP_DR_FOUNDATION.md`, §3, "no mezclar buckets").
- **Backup/recuperación propios** — el state remoto es en sí mismo un activo crítico; debe tener su propia estrategia de recuperación, independiente de la de la aplicación.

`docs/aws/TERRAFORM_FOUNDATION.md` ("Terraform state") ya documenta una recomendación (`backend "s3"` con `use_lockfile = true`, sin necesidad de una tabla DynamoDB adicional en versiones recientes de Terraform) como referencia, no como decisión tomada. Este runbook no elige el proveedor definitivo por la misma razón: es una decisión operativa explícita, no una que deba tomar una fase de auditoría.

**Consecuencia práctica**: hasta que este punto se resuelva, cualquier `terraform apply` real debe considerarse de un solo operador, con el archivo de state respaldado manualmente antes y después de cada operación — no un proceso de equipo seguro.

---

## 3. Cómo se prepara la infraestructura

1. Confirmar que todos los prerrequisitos de §1 están resueltos (especialmente remote state, §2).
2. Clonar/actualizar el repositorio en la máquina/pipeline que ejecutará Terraform.
3. `cd infra/terraform/environments/prod`.
4. `cp terraform.tfvars.example terraform.tfvars` y completar los valores obligatorios sin default (`backend_image`, `frontend_image`, `frontend_origins`, `browser_allowed_origins`, `trusted_hosts`, `s3_artifact_bucket`, `secrets_manager_secret_arns`, `certificate_arn` si aplica).
5. Confirmar que `terraform.tfvars` **nunca** se commitea (contiene nombres reales de bucket/dominio, aunque no secretos — ver `TERRAFORM_FOUNDATION.md`).
6. Verificar identidad AWS del operador: credenciales configuradas (perfil/rol), región correcta.
7. Continuar con el preflight de Terraform (§5) antes de cualquier `plan`.

---

## 4. Procedimiento de build / release de imágenes

1. Confirmar que la suite de tests está en verde (backend, frontend, e2e, compose — ver `.github/workflows/ci.yml`).
2. Build de la imagen backend: `docker build -t <registry>/territorio-electoral-api:<tag> backend/`.
3. Build de la imagen frontend: `docker build -t <registry>/territorio-electoral-frontend:<tag> frontend/`.
4. Etiquetar con un identificador **inmutable** — por digest de contenido o por SHA de commit de Git. **Nunca usar `:latest` como mecanismo de despliegue en producción** (`ECS_ALB_FOUNDATION.md`, "Estrategia de imágenes") — `:latest` impide un rollback determinista porque no identifica una versión concreta.
5. `docker push` de ambas imágenes al registry elegido (no hay un registry ECR provisionado por este Terraform — debe existir externamente).
6. Registrar el tag/digest exacto usado en un lugar rastreable (changelog de despliegue, tag de Git, o el pipeline de CI/CD) — es el valor que se usará en `backend_image`/`frontend_image` del siguiente paso.
7. Actualizar `backend_image`/`frontend_image` en `terraform.tfvars` (o el mecanismo de inputs del pipeline) con el tag/digest nuevo.

---

## 5. Terraform pre-flight (antes de cualquier `plan`/`apply` real)

Procedimiento ya validado en este ciclo de auditoría, sin AWS real:

```bash
cd infra/terraform/environments/prod
terraform fmt -check -recursive ../../..
terraform init -backend=false   # o "terraform init" si el backend remoto (§2) ya está configurado
terraform validate
```

Cuando AWS real esté autorizado y el backend remoto (§2) esté resuelto:

```bash
terraform init            # con backend remoto configurado
terraform plan -out=tfplan
```

**PLAN REVIEW REQUIRED**: el `plan` debe ser revisado por una persona distinta de quien lo generó (o, como mínimo, revisado deliberadamente antes de continuar) antes de cualquier `apply`. Prestar atención especial a: recursos destruidos inesperadamente, cambios en `db_instance_class`/`multi_az` (recrean o interrumpen la base de datos), cambios en security groups, y cualquier diff en el bucket de artifacts si `s3_lifecycle_management_enabled = true`.

```bash
terraform apply tfplan
```

**Nada de `plan`/`apply`/`destroy` se ha ejecutado en el marco de esta auditoría (Fase 4C.7)** — ver la confirmación explícita en `PRODUCTION_READINESS.md`.

---

## 6. Procedimiento de migración de base de datos

Orden estricto, derivado de `RDS_PROXY_FOUNDATION.md` ("Secuencia completa de bootstrap") y `ECS_ALB_FOUNDATION.md` ("Estrategia de migraciones"):

1. **Confirmar punto de backup/recuperación**: verificar que el `backup_retention_period` de RDS está activo (default 7 días) y, si es la primera vez que se migra una base con datos reales, considerar un snapshot manual previo.
2. **Bootstrap administrativo** (solo necesario la primera vez, o tras rotar la contraseña de aplicación — es idempotente):

   ```bash
   aws ecs run-task \
     --cluster "$(terraform output -raw ecs_cluster_name)" \
     --task-definition "$(terraform output -raw backend_bootstrap_task_definition_arn)" \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[$(terraform output -json app_subnet_ids | jq -r 'join(",")')],securityGroups=[\"$(terraform output -raw ecs_tasks_security_group_id)\"],assignPublicIp=DISABLED}"
   ```

   Confirmar exit code 0 (`aws ecs describe-tasks ... --query 'tasks[0].containers[0].exitCode'`) antes de continuar.
3. **Ejecutar la migration task** (Alembic, identidad maestra):

   ```bash
   aws ecs run-task \
     --cluster "$(terraform output -raw ecs_cluster_name)" \
     --task-definition "$(terraform output -raw backend_migrate_task_definition_arn)" \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[$(terraform output -json app_subnet_ids | jq -r 'join(",")')],securityGroups=[\"$(terraform output -raw ecs_tasks_security_group_id)\"],assignPublicIp=DISABLED}"
   ```

4. **Esperar exit code 0** de esa task (`command` usa `exec`, así que el exit code del contenedor es el exit code real de `alembic upgrade head` — visible en `aws ecs describe-tasks` y en el log group `backend-migrate`).
5. **Confirmar Alembic head**: revisar el log de la task (debe mostrar la cadena completa de migraciones hasta la última revisión del repositorio, sin errores) — no existe un comando remoto de un paso para "alembic current" sin ejecutar otra task; usar el log de la migration task como fuente de verdad de qué revisión quedó aplicada.
6. **Confirmar PostGIS**: la primera migración del historial (`20260803_0001`) ejecuta `CREATE EXTENSION IF NOT EXISTS postgis` — si la migration task completó sin error en una base nueva, PostGIS quedó habilitado. Ante cualquier duda, verificar manualmente con `SELECT extname, extversion FROM pg_extension WHERE extname = 'postgis';` contra el endpoint administrativo de RDS.
7. **Solo entonces** actualizar/desplegar el ECS Service del backend (§7) con la nueva imagen — nunca antes de confirmar el paso 4.

**Alembic nunca corre desde cada réplica**: el `command` del ECS Service del backend arranca únicamente `uvicorn` (sin `alembic upgrade head`) — la migración es exclusivamente responsabilidad de la migration task de un solo uso, invocada manualmente como se describe arriba, nunca automáticamente por el Service.

### Rollback de migraciones

**No asumir que todas las migraciones son automáticamente reversibles.** Antes de un rollback de esquema:

1. Revisar si la migración concreta que se quiere revertir tiene un `downgrade()` implementado y seguro (algunas migraciones de este historial son aditivas y sin pérdida de datos; otras pueden implicar `DROP COLUMN`/backfills que un `downgrade()` no puede deshacer sin pérdida de datos).
2. Si el `downgrade()` es seguro: ejecutar una variante de la migration task con `command` apuntando a `alembic downgrade <revision>` en vez de `head` (task ad-hoc, no una nueva task definition permanente).
3. Si no es seguro o no existe: el rollback real es restaurar desde backup/PITR a un punto anterior a la migración (ver §11) — nunca forzar un `downgrade()` que pueda corromper datos.
4. En cualquier caso, el rollback del **código de aplicación** (task definition anterior) y el rollback del **esquema de base de datos** son operaciones independientes — revertir la imagen del backend no revierte una migración ya aplicada.

---

## 7. Procedimiento de despliegue de aplicación

1. Actualizar la task definition del servicio afectado (`backend` o `frontend`) con la nueva imagen (`terraform apply` si el cambio se gestiona vía Terraform, o `aws ecs register-task-definition` + `update-service` para un despliegue fuera de banda).
2. Actualizar el ECS Service correspondiente para usar la nueva revisión de task definition.
3. El deployment usa `deployment_minimum_healthy_percent = 100` / `deployment_maximum_percent = 200`: ECS levanta tasks nuevas en paralelo a las existentes antes de retirar las antiguas — sin downtime forzado.
4. `deployment_circuit_breaker { enable = true, rollback = true }` está activo: si el nuevo deployment no logra estabilizarse, ECS revierte automáticamente a la revisión anterior — monitorear el evento de deployment en la consola/CLI de ECS para confirmar si esto ocurrió.
5. Esperar a que el ALB reporte los nuevos targets como `healthy` (`aws elbv2 describe-target-health`).
6. Revisar CloudWatch: el dashboard operativo (`terraform output -raw cloudwatch_dashboard_name`) y las alarmas de ALB/ECS relevantes — ningún 5xx/latencia anómala en los minutos posteriores al despliegue.
7. Validar `/health` del backend (liveness).
8. Validar `/ready` del backend (readiness, toca la DB).
9. Validar al menos un endpoint funcional real (ver checklist de smoke, §8).
10. Validar el frontend (health check `/health` del contenedor, y una carga real de la SPA a través del ALB).
11. Observar error rate/latencia durante una ventana razonable (mínimo 15-30 minutos) antes de considerar el despliegue estable.

---

## 8. Checklist de smoke post-despliegue

Rutas reales, obtenidas del código (`backend/app/api/routes/`) — ninguna inventada:

- [ ] **Backend health** — `GET /api/v1/health` → `200 {"status":"ok"}` (nunca toca la DB; si falla, el proceso no arrancó).
- [ ] **Backend readiness** — `GET /api/v1/ready` → `200 {"status":"READY"}` (toca la DB vía `SELECT 1`; `503` si la DB no responde).
- [ ] **Frontend health** — `GET /health` contra el contenedor frontend (mismo endpoint que su `HEALTHCHECK` de Docker).
- [ ] **Login** — `POST /api/v1/auth/login` (o el flujo de login de la SPA) con un usuario de prueba válido, confirma emisión de token.
- [ ] **Endpoint de lectura real de Election Day** — `GET /api/v1/campaigns/{campaign_id}/election-day/control-center` (Centro de Control, `backend/app/api/routes/election_day.py`) responde `200` con datos coherentes.
- [ ] **Endpoint de escritura segura y verificable** — `POST /api/v1/campaigns/{campaign_id}/election-day/incidents` con un incidente de prueba controlado (o revertible), confirmando `201` y que el incidente aparece luego en `GET .../incidents`.
- [ ] **Dashboard / Data Hub** — `GET /api/v1/campaigns/{campaign_id}/dashboard` responde `200`.
- [ ] **Acceso a artifact storage** — descargar un artifact existente (evidencia o informe) y confirmar que el backend devuelve un redirect 307 a una URL S3 firmada (no que intente transportar el archivo él mismo) cuando `ARTIFACT_STORAGE_PROVIDER=s3`.
- [ ] **Conectividad a DB** — implícita en `/ready` (arriba); adicionalmente, revisar `DatabaseConnections` en el dashboard de CloudWatch para confirmar que las tasks nuevas están conectando.
- [ ] **Logs** — confirmar que el log group `backend` en CloudWatch recibe líneas JSON estructuradas nuevas (`request_id`, `status_code`) tras el tráfico de smoke.
- [ ] **Alarmas** — confirmar que ninguna alarma de ALB/ECS/RDS pasó a estado `ALARM` durante o inmediatamente después del despliegue.

---

## 9. Rollback

### Imagen de aplicación

Revertir el ECS Service a la revisión de task definition anterior (`aws ecs update-service --task-definition <arn-revision-anterior>`) — posible únicamente si la imagen referenciada por esa revisión anterior todavía existe en el registry (ver §4, punto 4 — nunca usar `:latest`).

### Infraestructura Terraform

`git revert` del commit que introdujo el cambio (o una corrección directa) + `terraform plan` revisado (§5) + `apply` controlado. Nunca un `terraform apply` directo sobre un commit no revisado en un rollback de infraestructura — el mismo proceso de revisión de plan aplica en un rollback que en un cambio hacia adelante.

### Base de datos

**El rollback de código ≠ rollback de base de datos.** Revertir la imagen del backend a una versión anterior no revierte cambios de esquema ya aplicados por Alembic. Si el despliegue defectuoso incluyó una migración:

- Evaluar primero si el `downgrade()` de esa migración es seguro (ver §6, "Rollback de migraciones").
- Si no lo es, el rollback real de datos es una restauración PITR/snapshot (§11) a un punto anterior a la migración — con la pérdida de datos que eso implique entre ese punto y el momento del incidente.

### Datos (PITR/snapshot)

Ver §11 — usar cuando el rollback de código/esquema no es suficiente porque los datos mismos quedaron en un estado incorrecto.

### S3

Recuperar la versión anterior del objeto (ver §12, "Incidente S3") — nunca asumir que un objeto sobrescrito/borrado es irrecuperable sin antes revisar versiones anteriores.

---

## 10. Respuesta a incidentes

Niveles prácticos, sin burocracia excesiva — para cada escenario: **detectar → triage → mitigar → recuperar → verificar**.

| Incidente | Detectar | Triage | Mitigar | Recuperar | Verificar |
| --- | --- | --- | --- | --- | --- |
| Backend unhealthy | Alarmas `alb-unhealthy-hosts-backend`, ALB deja de enrutar tráfico | Revisar logs del backend (CloudWatch) y el evento de deployment más reciente | Si es un despliegue reciente, dejar que el circuit breaker revierta o forzar rollback (§9) | Confirmar que las tasks nuevas pasan el health check | `/health`/`/ready` en verde, alarma vuelve a `OK` |
| 5xx elevado | Alarmas `alb-5xx`/`alb-target-5xx-backend` | Revisar `backend_error_log_count` (log-based metric) y logs por `request_id` | Identificar si es un endpoint específico (rollback parcial no es posible — es todo el Service) o un problema de DB (ver fila siguiente) | Rollback de imagen si es del código; escalar a incidente de DB si el error viene de ahí | 5xx vuelve a baseline, alarma en `OK` |
| Latencia alta | Alarma `alb-response-time-backend` (> 2s promedio) | Revisar CPU/memoria de ECS (`ecs-backend-cpu-high`/`memory-high`), y `DatabaseConnections` de RDS | Si CPU/memoria saturados: esperar a que autoscaling reaccione (target tracking 70% CPU) o forzar un aumento manual de `desired_count` dentro de `max_capacity` | Confirmar que la latencia baja tras el escalado | p95/p99 vuelven a rango esperado |
| Agotamiento de conexiones DB | Alarma `rds-database-connections-high` (> 80) | Revisar cuántas tasks backend están corriendo (`WEB_CONCURRENCY × (DB_POOL_SIZE+DB_MAX_OVERFLOW) × tasks`, ver §"Capacity checklist") vs. `db_proxy_max_connections_percent` | Reducir `desired_count`/`max_capacity` temporalmente si hay un escalado descontrolado, o investigar una fuga de conexiones en el código | Confirmar que las conexiones bajan tras la mitigación | Conexiones vuelven bajo el umbral |
| RDS no disponible | Alarma `rds-cpu-high`/ausencia de métricas (`treat_missing_data=breaching`), `/ready` en 503 masivo | Confirmar en la consola de RDS si es un evento de mantenimiento, un failover Multi-AZ en curso, o una falla real | Si `multi_az=true`, esperar el failover automático (minutos); si no, evaluar restore desde snapshot | Ver §11 (incidente de DB) | `/ready` vuelve a 200, alarma en `OK` |
| WAF bloqueando tráfico válido | Reportes de usuarios/soporte, métricas de regla WAF en CloudWatch | Identificar la regla específica que coincide (ver §12) | Cambiar esa regla a Count temporalmente si es un managed rule group, o ajustar `waf_rate_limit_requests` si es el rate limit | Confirmar que el tráfico legítimo pasa | Métricas de bloqueo bajan a lo esperado |
| Falla de S3 | Errores 5xx en subida/descarga de artifacts, logs de `S3ArtifactStorage` | Revisar si es un problema de permisos IAM, de red (NAT/VPC endpoint), o del bucket mismo | Ver §13 (incidente S3) | — | Subida/descarga de artifacts vuelve a funcionar |
| Migración fallida | Exit code ≠ 0 de la migration task | Revisar el log de la task (`backend-migrate` log group) para el error real de Alembic | **No desplegar el nuevo backend** hasta resolver — el schema puede haber quedado a mitad de camino | Corregir la migración o restaurar desde backup si dejó el schema inconsistente; reintentar | Migration task vuelve a terminar con exit code 0 |
| Secreto comprometido | Alerta externa (no hay detección automática de esto en este stack) | Identificar qué secreto (aplicación DB, SECRET_KEY, HMAC) y su alcance de impacto | Rotar inmediatamente (ver §14) | Confirmar que las conexiones/tokens viejos dejan de ser válidos tras la rotación | Nueva versión del secreto en uso, sin errores de autenticación |
| Datos corruptos | Reportes de usuario, checks manuales, discrepancias en informes | Determinar el punto aproximado en el tiempo en que ocurrió la corrupción | Congelar escrituras si es posible (mantenimiento) | PITR a un punto anterior (§11) | Validación funcional contra los datos restaurados antes de reabrir escrituras |
| Pico de tráfico (Election Day) | CloudWatch dashboard, autoscaling activo | Confirmar que el autoscaling está reaccionando dentro de `max_capacity` | Evitar despliegues no esenciales durante el pico (ver §16) | — | Latencia/error rate se mantienen dentro de lo observado en `PERFORMANCE_BASELINE.md` |

---

## 11. Incidente de base de datos

- **Agotamiento de conexiones**: ver tabla de §10. No asumir que reiniciar el backend resuelve un agotamiento de conexiones de forma duradera si la causa es un pool mal dimensionado frente al tráfico real — revisar el connection budget (§"Capacity checklist").
- **DB lenta**: revisar CPU/memoria/IOPS de RDS en CloudWatch antes de escalar la instancia — un cambio de `db_instance_class` es un cambio de Terraform revisado (§5), no una acción de emergencia sin `plan`.
- **RDS no disponible**: ver tabla de §10. Con `multi_az=false` (default actual), no hay failover automático — la recuperación depende de que AWS reemplace la instancia, o de un restore desde snapshot/PITR.
- **Migración fallida**: ver §6, "Rollback de migraciones" y la fila correspondiente de §10.
- **Corrupción lógica**: restaurar mediante PITR (procedimiento completo en `BACKUP_DR_FOUNDATION.md`, §26):
  1. Identificar el punto de recuperación (timestamp UTC anterior al incidente, dentro de la ventana de `backup_retention_period`).
  2. Restaurar a una instancia RDS **nueva** (`aws rds restore-db-instance-to-point-in-time`) — nunca sobrescribe la original.
  3. Validar PostGIS (`SELECT extname, extversion FROM pg_extension WHERE extname = 'postgis';`) y el schema (Alembic) contra la instancia restaurada.
  4. Reapuntar el target de RDS Proxy a la instancia restaurada (`BACKUP_DR_FOUNDATION.md`, §28) — el backend nunca se conecta directo a RDS.
  5. Validar la aplicación contra la instancia restaurada en un entorno aislado antes de mover tráfico de producción.
  6. Conservar la instancia original para investigación post-incidente.
- **No asumir que un restart siempre es la solución** — un restart de las tasks ECS no corrige datos corruptos, una migración fallida a medias, ni una fuga real de conexiones en el código.

---

## 12. Incidente WAF

Preferencia explícita: **no deshabilitar el WAF completo.**

1. Identificar la regla específica que generó el falso positivo — revisar las métricas por regla en CloudWatch (`${name_prefix}-common-rule-set`, `${name_prefix}-known-bad-inputs`, `${name_prefix}-ip-reputation`, o la regla de rate limit).
2. Si `waf_logging_enabled = true`, revisar los logs de solicitudes bloqueadas reales (`aws-waf-logs-<prefijo>`) para confirmar el patrón exacto que coincidió.
3. Cambiar la regla específica afectada a `waf_managed_rules_count_mode = true` (esto afecta a los 3 managed rule groups como conjunto — no hay un mecanismo granular por regla individual en esta implementación, ver `WAF_CLOUDWATCH_FOUNDATION.md`, "Rollout"), o ajustar `waf_rate_limit_requests` si el problema es el rate limit.
4. Aplicar el cambio vía Terraform (§5 — sigue siendo un `plan`/`apply` revisado, no un cambio directo en la consola que luego diverja del código).
5. Validar que el tráfico legítimo pasa.
6. Documentar la excepción (qué regla, por qué, durante cuánto tiempo) — para no perder el contexto cuando se reactive el enforcement.
7. Reactivar el enforcement (`waf_managed_rules_count_mode = false`, o el `rate_limit_requests` original) en cuanto se confirme que el patrón de tráfico legítimo está identificado y no volverá a coincidir.

---

## 13. Incidente S3

Basado en `BACKUP_DR_FOUNDATION.md`, §25:

- **Objeto faltante / eliminado**: `aws s3api list-object-versions --bucket <bucket> --prefix <key>` para ubicar el delete marker o la versión anterior; revivir eliminando el delete marker más reciente (`aws s3api delete-object --version-id <delete-marker-version-id>`).
- **Objeto sobrescrito**: recuperar la versión noncurrent anterior con `aws s3api get-object --version-id <version-id>`, y si corresponde restaurarla como versión actual con `copy-object` sobre sí misma.
- **Pending huérfano** (`evidence/pending/*` nunca completado): no requiere acción — la regla de lifecycle `pending-cleanup` lo limpia automáticamente (2 días current + 7 días noncurrent, si `s3_lifecycle_management_enabled=true`).
- **Permission denied**: confirmar que la IAM Task Role del backend tiene los permisos esperados (`s3:GetObject`/`PutObject`/`DeleteObject` sobre `evidence/*` y `reports/*`, ver `ECS_ALB_FOUNDATION.md`) y que el bucket policy externo (si existe) no está denegando explícitamente.
- **Problema de credenciales**: el backend nunca usa claves estáticas — revisar que la IAM Task Role esté correctamente asociada a la task definition, y que no haya expirado ningún rol asumido si el operador está probando manualmente con AWS CLI.

---

## 14. Rotación de secretos

Procedimiento conceptual, documentado — **no ejecutado en esta fase**:

### Secreto de aplicación (DB)

1. Incrementar `db_app_secret_version` en `terraform.tfvars`.
2. `terraform apply` (revisado, §5) — como `ephemeral.random_password` se reevalúa en cada operación, esto escribe un valor nuevo en Secrets Manager.
3. **Inmediatamente después**, reinvocar la bootstrap task (`aws ecs run-task` sobre `backend_bootstrap_task_definition_arn`, §6) — su `ALTER ROLE ... WITH LOGIN PASSWORD` sincroniza la contraseña real del rol de PostgreSQL con el nuevo valor del secreto.

**Orden importante**: el secreto nuevo en Secrets Manager y la contraseña real dentro de PostgreSQL deben coordinarse — si el ECS Service del backend recicla una task entre el paso 2 y el paso 3, esa task fallará a conectar hasta que el paso 3 se complete. Considerar ejecutar esto en una ventana de mantenimiento o inmediatamente antes de un despliegue que reinicie las tasks de todas formas.

### Secreto maestro (RDS)

Gestionado nativamente por AWS (`manage_master_user_password = true`) — la rotación es responsabilidad de RDS/Secrets Manager, no de este Terraform.

### SECRET_KEY / HMAC secrets de la aplicación

Rotar el valor en Secrets Manager directamente (fuera de Terraform, ya que estos secretos no se generan vía `ephemeral` en este stack) y forzar un nuevo despliegue del backend para que las tasks recojan el valor nuevo — invalidará tokens/sesiones firmados con el valor anterior (comportamiento esperado de una rotación de este tipo).

---

## 15. Checklist de observabilidad (qué mirar durante Election Day)

**ALB**:
- 5xx totales (`alb-5xx`) y 5xx de target backend (`alb-target-5xx-backend`).
- Latencia (`alb-response-time-backend`, umbral 2s).
- Hosts no saludables (`alb-unhealthy-hosts-backend`/`-frontend`).

**ECS**:
- CPU/memoria de ambos servicios (`ecs-backend-cpu-high`/`memory-high`, `ecs-frontend-*`, umbral 85%).
- Salud de tasks deseadas vs. corriendo — vía hosts saludables del ALB (no hay métrica directa de running task count sin Container Insights, ver `WAF_CLOUDWATCH_FOUNDATION.md`, "limitación documentada").

**RDS**:
- CPU (`rds-cpu-high`, > 80%).
- Conexiones (`rds-database-connections-high`, > 80 — recordar que cuenta conexiones de RDS Proxy, no 1:1 de aplicación).
- Memoria libre (`rds-freeable-memory-low`, < 256 MiB).
- Storage libre (`rds-free-storage-low`, < 20% de `db_allocated_storage`).

**Aplicación**:
- Logs JSON estructurados por `request_id` (CloudWatch Logs Insights sobre los log groups `backend`/`frontend`).
- `backend_error_log_count` (log-based metric, `level=ERROR`, umbral > 10/5min).
- Métricas Prometheus de negocio (`territorio_events_total{event=...}`) en `/api/v1/metrics` — **no** ingeridas por CloudWatch sin un exporter adicional (ver `WAF_CLOUDWATCH_FOUNDATION.md`, "Application metrics") — revisar directamente ese endpoint si se necesita esa señal durante la jornada.

**WAF**:
- Tráfico bloqueado/contado por regla (por managed rule group y por la regla de rate limit).
- Tasa de bloqueo de la regla de rate limit (`/api/*`, 2000 req/IP/5min) — un salto brusco puede indicar tráfico legítimo masivo (jornada electoral) chocando con el baseline.

**Dashboard**: `terraform output -raw cloudwatch_dashboard_name` — 9 widgets (ALB, ECS backend/frontend, RDS, errores backend) en un solo lugar.

---

## 16. Election Day pre-flight

### T-24h

- [ ] CI verde (backend, frontend, e2e, compose) en la última versión a desplegar.
- [ ] Backups de RDS activos y recientes (`backup_retention_period` cubriendo la ventana esperada).
- [ ] Salud de RDS (CPU/conexiones/storage dentro de rango normal).
- [ ] Salud de ECS (tasks deseadas = tasks corriendo, sin alarmas activas).
- [ ] Alarmas de CloudWatch revisadas, ninguna en estado `ALARM` sin explicación.
- [ ] Modo WAF confirmado (Count vs. Enforce) y consciente de cuál es — no cambiarlo el mismo día sin necesidad.
- [ ] Capacidad revisada — `desired_count`/`max_capacity` de backend y frontend según el perfil RECOMMENDED (§"Capacity checklist").
- [ ] Versión de imagen confirmada como la que se quiere en producción (tag/digest exacto documentado).
- [ ] Sin migraciones pendientes (última migration task ejecutada con exit code 0, sin cambios de esquema sin desplegar).
- [ ] Acceso a Secrets Manager verificado (el equipo de guardia puede rotar un secreto si hace falta).
- [ ] S3 — bucket de artifacts accesible, sin alarmas de permisos.

### T-1h

- [ ] `/health` y `/ready` del backend en verde.
- [ ] Conexiones de DB dentro de lo esperado (no cerca del umbral de 80).
- [ ] Conteo de tasks backend/frontend en el mínimo esperado (`desired_count`).
- [ ] Salud de targets del ALB — todos `healthy`.
- [ ] Dashboard de CloudWatch abierto y monitoreado por al menos una persona.
- [ ] Ningún incidente activo sin resolver de las horas previas.

### Durante la jornada

- [ ] Monitorear métricas continuamente (dashboard + alarmas) — no solo reactivamente.
- [ ] Evitar despliegues no esenciales durante la ventana de mayor tráfico — cualquier cambio de infraestructura/aplicación debe esperar a una ventana de menor riesgo salvo que sea la mitigación de un incidente activo.
- [ ] Escalar incidentes según la tabla de §10 — no improvisar un procedimiento nuevo bajo presión si ya existe uno documentado.

### Después

- [ ] Preservar logs relevantes del período (CloudWatch Logs tiene su propia retención — considerar exportar si se necesita un análisis posterior más allá de `log_retention_days`).
- [ ] Confirmar el último backup/checkpoint de RDS posterior a la jornada.
- [ ] Reportar cualquier incidente ocurrido, aunque se haya mitigado sin impacto visible.
- [ ] Revisión post-evento: qué funcionó, qué no, qué umbral/alarma resultó ruidoso o insuficiente — alimentar ajustes futuros de `terraform.tfvars` (nunca cambios impulsivos en producción sin pasar por `plan` revisado).

No se inventan horarios operativos de personas específicas — la asignación de guardia/turnos es una decisión operativa externa a este documento.

---

## 17. Checklist de capacidad

Perfil RECOMMENDED aplicado en Fase 4C.6 (`terraform.tfvars.example`):

| | Backend | Frontend |
| --- | --- | --- |
| CPU (Fargate units) | 1024 | 256 |
| Memoria | 2048 MiB | 512 MiB |
| `desired_count` | 2 | 2 |
| `min_capacity` | 2 | 2 |
| `max_capacity` | 4 | 4 |
| `WEB_CONCURRENCY` | 1 | n/a |

Justificación: `docs/performance/PERFORMANCE_BASELINE.md` (§26/§32/§44/§52) y `loadtests/results/SUMMARY.md` — Profile A (256/512) descartado con evidencia directa (satura con 10 VUs, p99 21s, memoria al 99.97%); Profile C (1024/2048) midió 34.19 RPS, p95 427ms, p99 823ms, 0% error, con margen de memoria amplio.

**Connection budget SQLAlchemy → RDS Proxy** (`db_pool_size=5` + `db_max_overflow=10` = 15 conexiones máx. por worker, `WEB_CONCURRENCY=1`):

- Con 2 tasks (`desired_count`): **hasta 30 conexiones** hacia RDS Proxy.
- Con 4 tasks (`max_capacity`): **hasta 60 conexiones** hacia RDS Proxy.

**Requieren validación con AWS real antes de considerar el capacity planning definitivo**:

- RDS Proxy — multiplexing y comportamiento real de `max_connections_percent=100`/`max_idle_connections_percent=50` bajo carga real.
- `db_instance_class` (`db.t4g.micro`) — nunca validado por benchmark local (los benchmarks corrieron contra Docker/Postgres local, no contra esa clase de instancia real).
- Fargate cold start / CPU credits reales — los benchmarks de `PERFORMANCE_BASELINE.md` corrieron con límites de CPU/memoria simulados en Docker Desktop, no en Fargate real.
- ALB — comportamiento real de LCU bajo el tráfico de un Election Day real.
- WAF — el rate limit de 2000 req/IP/5min es un baseline conservador sin tráfico real que lo confirme.

---

## 18. GO / NO-GO checklist

**GO únicamente si TODO lo siguiente es cierto:**

- [ ] CI verde (backend, frontend salvo la anomalía preexistente documentada de `format:check`, e2e, compose).
- [ ] `terraform validate` verde.
- [ ] Remote Terraform state resuelto (§2) — **actualmente NO cumplido**.
- [ ] Dominio/certificado ACM resueltos si se requiere HTTPS real — **actualmente NO cumplido** (`certificate_arn` vacío).
- [ ] Secrets de producción configurados en Secrets Manager (`SECRET_KEY`, HMAC secrets, referenciados en `secrets_manager_secret_arns`).
- [ ] Imágenes inmutables disponibles en un registry real.
- [ ] Estrategia de backup de DB activa (`backup_retention_period` > 0, ya `CONFIGURED` por defecto).
- [ ] Migración validada (migration task ejecutada con exit code 0 contra la base objetivo).
- [ ] Health checks en verde (`/health`, `/ready`, target groups del ALB).
- [ ] Alertas configuradas (al menos un destino SNS con `enable_alarm_actions=true`) — **actualmente NO cumplido** (ambos en `false`/vacío por defecto).
- [ ] Capacidad revisada (§17).
- [ ] Ownership del bucket de artifacts confirmado (las 3 variables de `modules/s3_lifecycle` en `true` simultáneamente, si se desea que Terraform administre su configuración).
- [ ] Procedimiento de DR disponible (este documento + `BACKUP_DR_FOUNDATION.md`) — cumplido a nivel de documentación; **sin ejercicio de DR real ejecutado todavía**.
- [ ] Ninguna vulnerabilidad crítica conocida sin resolver (ver auditoría de seguridad, `PRODUCTION_READINESS.md`).

**NO-GO si cualquiera de los bloqueadores críticos de `PRODUCTION_READINESS.md` (remote state, dominio/TLS, secrets de producción, primer `terraform plan`/`apply` real nunca ejecutado) sigue pendiente.**

Este checklist no dispara ningún despliegue automático — es una lista de verificación humana antes de autorizar el primer `apply` real.
