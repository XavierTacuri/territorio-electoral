# Production Readiness — Territorio Electoral (Fase 4C.7)

Estado de preparación para producción de la infraestructura AWS de Territorio Electoral, al cierre de Fase 4C.7 (actualizado en Fase 4D.1 con el estado del bootstrap). Complementa el [`PRODUCTION_RUNBOOK.md`](./PRODUCTION_RUNBOOK.md) (procedimientos operativos) y [`AWS_BOOTSTRAP.md`](./AWS_BOOTSTRAP.md) (remote state, ECR, modelo IAM — Fase 4D.1) sin duplicarlos — este documento condensa **qué está listo, qué está validado localmente, qué requiere AWS real, y qué bloquea el primer despliegue**.

## Qué significa "validado" en este documento

Toda la Fase 4C (4C.1-4C.6) se validó mediante:

- `terraform fmt -check -recursive` / `terraform init -backend=false` / `terraform validate` — sintaxis y tipos correctos, **no** que los recursos existan o funcionen en AWS real.
- Docker Compose local (`docker-compose.yml`, `docker-compose.e2e.yml`, `docker-compose.multi-instance.yml`) — comportamiento de la aplicación, no de la infraestructura AWS.
- Benchmarks de carga (`k6`) contra contenedores locales con límites de CPU/memoria simulados — no contra Fargate/RDS reales.
- CI (GitHub Actions) — backend, frontend, e2e, compose, todos verdes en la rama `feature/election-day-v2-resilience`.

**Infrastructure as Code validado localmente. Validación de runtime en AWS pendiente.** Ningún `terraform plan`/`apply`/`destroy` se ha ejecutado nunca contra una cuenta AWS real, en ninguna fase de este proyecto hasta la fecha de este documento. Ninguna afirmación de este documento debe leerse como "probado en AWS" salvo que diga explícitamente lo contrario — y ninguna sección lo dice, porque no ocurrió.

---

## Resumen de estado por fase

| Fase | Contenido | Estado de código/IaC |
| --- | --- | --- |
| 4C.1 | Red, security groups | Completa, validada localmente |
| 4C.2 | ECS/Fargate, ALB | Completa, validada localmente |
| 4C.3 | RDS, RDS Proxy | Completa, validada localmente |
| 4C.4 | WAF, CloudWatch | Completa, validada localmente |
| 4C.5 | S3 lifecycle, Backup/DR (documentación) | Completa, validada localmente |
| 4C.6 | Load/stress testing, dimensionamiento | Completa — perfil RECOMMENDED aplicado |
| 4C.7 | Runbook, auditoría integral, readiness | Este ciclo — ver hallazgos abajo |

**Toda la Fase 4C está completa a nivel de código/IaC.** Esto no equivale a "production-ready" — ver Matriz de Producción y Blockers abajo.

---

## Matriz de preparación para producción

| Área | Estado | Evidencia | ¿Blocker? | ¿Requiere validación AWS? | Owner/acción |
| --- | --- | --- | --- | --- | --- |
| Networking | Completo | `modules/network`, `modules/security_groups` — flujo Internet→WAF→ALB→ECS→RDS Proxy→RDS confirmado por código, cero SG abierto indebidamente | No | Sí — confirmar rutas/NAT/endpoints reales tras el primer `apply` de producción | Platform |
| ECS | Completo, sizing aplicado | `modules/ecs`, perfil RECOMMENDED 4C.6 en `terraform.tfvars.example` | No | Sí — CPU credits/cold start de Fargate real | Platform |
| ALB | Completo, sin TLS | `modules/alb` — HTTP siempre, HTTPS condicional a `certificate_arn` (vacío hoy) | **Sí — antes de go-live** (HTTPS) | Sí — LCU real bajo carga | Platform / Operations (dominio) |
| RDS | Completo, sizing conservador | `modules/database` — `db.t4g.micro`, Multi-AZ=false por defecto | **Decisión obligatoria antes de go-live** (Multi-AZ, ver nota abajo) | Sí — instance class nunca validada contra AWS real | Platform |
| RDS Proxy | Completo | `modules/database` — TLS, 2 auth blocks, pool config conservador | No | Sí — multiplexing/conexiones reales, métricas de RDS Proxy no incluidas en CloudWatch (namespace no verificable sin AWS) | Platform |
| S3 | Completo, opcional | `modules/s3_lifecycle` — triple gate de ownership, todo en `false` por defecto | **Sí — antes del production apply** (ownership; no bloquea el bootstrap apply) | No (lógica ya validada) | Operations (confirmar ownership del bucket real) |
| Secrets | Completo | Master gestionado por RDS, aplicación `ephemeral`/write-only, frontend sin secretos DB | **Sí — antes del production apply** (`secrets_manager_secret_arns` vacío; no bloquea el bootstrap apply) | No | Operations |
| WAF | Completo, modo Count | `modules/waf` — 3 managed rule groups + rate limit 2000/300s/IP | **Sí — antes de go-live** (validar modo Enforce) | Sí — falsos positivos y rate limit solo se confirman con tráfico real | Platform |
| CloudWatch | Completo, sin alertas activas | `modules/observability` — 14 alarmas, dashboard, SNS opcional | **Sí — antes de go-live** (`enable_alarm_actions=false` hoy) | Sí — todos los thresholds son baseline sin tráfico real | Operations |
| Backup/DR | Documentado, no ejercitado | `BACKUP_DR_FOUNDATION.md` — PITR, snapshots, matriz de incidentes | **Sí — antes de go-live** (ejercicio de restore real) | Sí — ningún restore real ejecutado nunca | Platform |
| Performance | Medido localmente | `PERFORMANCE_BASELINE.md`, `LOAD_STRESS_TESTING.md` — perfil RECOMMENDED coincide con Terraform | No | Sí — nunca medido contra Fargate/RDS Proxy reales | Application / Platform |
| Terraform state | **Local — implementation prepared, not provisioned** | `environments/prod/versions.tf` ya declara `backend "s3" {}` (config parcial); `infra/terraform/bootstrap/` define el state bucket (versioning/encryption/public access block/SecureTransport/`prevent_destroy`), validado con `fmt`/`init -backend=false`/`validate` — ver `AWS_BOOTSTRAP.md`. Ningún bucket existe todavía en AWS; el state real sigue siendo local | **Sí — antes del production apply** (el state bucket lo crea el bootstrap apply, un evento distinto — ver "Blockers reales" abajo) | Sí — el bucket debe crearse y verificarse en AWS antes de migrar | Operations |
| Domain/TLS | No configurado | `certificate_arn=""`, sin `frontend_origins`/`trusted_hosts` reales | **Sí — antes de go-live** (no bloquea el production apply: `certificate_arn=""` es una configuración válida hoy, ver nota de comportamiento abajo) | No aplica hasta tener dominio | Operations |
| Images/registry | **Repositories prepared in IaC, not provisioned** | `infra/terraform/bootstrap/ecr.tf` define ECR backend/frontend (`IMMUTABLE`, `scan_on_push`, cifrado) — ver `AWS_BOOTSTRAP.md`. `backend_image`/`frontend_image` de `environments/prod` siguen sin default; ningún repositorio existe todavía en AWS | **Sí — antes del production apply** (los repositorios los crea el bootstrap apply, un evento distinto) | No aplica | Platform |
| CI/CD | Backend/frontend/e2e/compose verdes; sin Terraform ni performance en CI | `.github/workflows/ci.yml` | No (mejora recomendada) | No | Platform |
| Runbook | Completo | `PRODUCTION_RUNBOOK.md` (este ciclo) | No | No | — |

---

## Blockers reales — tres momentos distintos

No se mezcla "IaC completo" con "runtime AWS validado", y a partir de Fase 4D.1 tampoco se mezclan dos despliegues que son eventos distintos contra AWS: **(A) el `apply` del bootstrap** (`infra/terraform/bootstrap/` — crea únicamente el state bucket, ECR y las policies IAM de alcance conocido) y **(B) el `apply` del stack productivo** (`infra/terraform/environments/prod/` — VPC, ECS, RDS, ALB, WAF, CloudWatch). Resolver (A) es prerequisito de (B), pero son dos `terraform apply` distintos, en dos directorios distintos, con dos listas de requisitos distintas — nunca el mismo evento. Una tercera lista, sin relación con ningún `apply` en sí, cubre lo necesario antes de exponer el sistema a tráfico público real.

### BEFORE AWS BOOTSTRAP APPLY

Deben resolverse antes de que `terraform apply` en `infra/terraform/bootstrap/` pueda ejecutarse — es, en sí mismo, **el primer contacto real de este proyecto con AWS**:

1. **Cuenta AWS disponible.**
2. **Método seguro de autenticación de corta duración** para la identidad de bootstrap (AWS SSO/rol asumido — nunca `access_key`/`secret_key` estáticas, ver `AWS_BOOTSTRAP.md` §17).
3. **Región AWS elegida** — debe ser la misma que usará después `environments/prod`.
4. **Nombre globalmente único del state bucket** (`state_bucket_name`) decidido.
5. **Nombres ECR confirmados**, o aceptación explícita de los defaults documentados (`<project>-<environment>-backend`/`-frontend`).
6. **Identidad de bootstrap con permisos suficientes para crear exactamente los recursos de `infra/terraform/bootstrap/`** — S3 (bucket, versioning, encryption, public access block, bucket policy), ECR (dos repositorios) e IAM (`CreatePolicy` para las dos policies de alcance conocido). No requiere, y no debe usarse, `AdministratorAccess`/`PowerUserAccess` como atajo.
7. **`terraform.tfvars` real del bootstrap preparado localmente** (copiado de `terraform.tfvars.example`) y **no versionado** (ya cubierto por `.gitignore`).
8. **Revisión humana del primer `terraform plan` del bootstrap** antes de cualquier `apply` — mismo criterio de revisión que cualquier otro `plan` real contra AWS (`PRODUCTION_RUNBOOK.md` §5).

**NO forman parte de esta lista** — no bloquean el `apply` del bootstrap, aunque bloqueen el del stack productivo o el go-live: ownership del bucket de artifacts, dominio, ACM, secrets de aplicación, decisión de Multi-AZ, `db_instance_class`, rollout de WAF. El bootstrap no crea, ni depende de, ninguno de esos recursos.

**Ningún `terraform plan`/`apply` del bootstrap se ha ejecutado nunca** — solo `fmt`/`init -backend=false`/`validate` (sintáctico/local).

### BEFORE FIRST PRODUCTION STACK APPLY

Deben resolverse antes de que el primer `terraform apply` en `infra/terraform/environments/prod/` pueda siquiera completarse sin error — presupone que el bootstrap (lista anterior) ya se aplicó:

1. **Remote Terraform state ya creado mediante el bootstrap, y `environments/prod` migrado/inicializado contra ese backend remoto** — el bucket debe existir y estar verificado en AWS (versioning/encryption/public access block/policy), y `terraform init` de `environments/prod` debe haberse ejecutado con los `-backend-config` reales (`AWS_BOOTSTRAP.md` §7/§9). Hoy: bucket sin crear, `environments/prod` sigue en state local.
2. **Cuenta AWS y permisos para el Terraform de producción** — un "deployment role"/identidad con permisos suficientes sobre VPC/ECS/RDS/WAF/CloudWatch/Secrets Manager. **Ese role todavía no existe** (ver "Estado del deployment role" abajo) — es, en sí mismo, parte de este blocker, no una decisión ya resuelta.
3. **Ownership del bucket de artifacts confirmado** — `s3_artifact_bucket` sin valor real, y las tres variables de confirmación de ownership de `modules/s3_lifecycle` en `false`. Sin esto, `artifact_storage_provider="s3"` (el único valor productivo) no puede desplegarse. Blocker deliberadamente NO resuelto por el bootstrap (`AWS_BOOTSTRAP.md`, "Qué NO crea").
4. **Imágenes backend/frontend disponibles en el ECR ya creado por el bootstrap** — construidas, etiquetadas con un identificador inmutable (SHA de commit) y publicadas (`docker push`) en los repositorios que el bootstrap crea; `backend_image`/`frontend_image` sin valor real hoy.
5. **Configuración/secrets de producción definidos** — `frontend_origins`, `browser_allowed_origins`, `trusted_hosts` con el dominio o valor real que corresponda, y `SECRET_KEY`/`BROWSER_REFRESH_TOKEN_HMAC_SECRET`/`SURVEY_SUBMISSION_HMAC_SECRET` como secretos reales en Secrets Manager, referenciados en `secrets_manager_secret_arns`.
6. **Región consistente entre bootstrap y producción** — el `aws_region` usado al aplicar el bootstrap debe coincidir con el de `environments/prod`.
7. **Modelo IAM de deployment resuelto lo suficiente para ejecutar `plan`/`apply`** — ver "Estado del deployment role" abajo: no exige el role definitivo de mínimo privilegio ya terminado, pero sí una identidad autorizada explícitamente para este `plan`/`apply` concreto, nunca `AdministratorAccess`/`PowerUserAccess` de forma permanente.
8. **Revisión humana del `terraform plan` de producción** antes de cualquier `apply` (`PRODUCTION_RUNBOOK.md` §5).

**Dominio/ACM — comportamiento real del Terraform actual**: `modules/alb` crea el listener HTTP **siempre**, y el listener HTTPS **condicionalmente**, solo si `var.certificate_arn` no está vacío. `certificate_arn=""` (el default actual) es una configuración **válida** para `environments/prod` — el `apply` no falla por falta de certificado. Por eso dominio/ACM **no** aparecen en esta lista: con la arquitectura actual (HTTPS opcional, HTTP siempre disponible), ese punto se clasifica exclusivamente en BEFORE PUBLIC GO-LIVE, abajo — nunca sería así si el diseño exigiera HTTPS obligatorio desde el primer `apply`.

**Ningún `terraform plan`/`apply` real de `environments/prod` se ha ejecutado nunca** — todo lo validado hasta ahora es sintáctico/local (`fmt`/`init -backend=false`/`validate`).

### BEFORE PUBLIC GO-LIVE

No bloquean ningún `apply` en sí (ni el del bootstrap ni el de producción), pero deben resolverse antes de exponer el sistema a tráfico público/de campañas real — ninguno de estos se confirma con Terraform local, todos requieren el stack productivo ya aplicado:

1. **Dominio configurado** — `frontend_origins`/`browser_allowed_origins`/`trusted_hosts` con el dominio real (si no se completó ya como parte de BEFORE FIRST PRODUCTION STACK APPLY).
2. **ACM/HTTPS configurado** — `certificate_arn` real; hoy solo hay HTTP (`certificate_arn=""`), inaceptable para producción real con datos de campañas/usuarios — ver nota de comportamiento arriba.
3. **Despliegue AWS exitoso** — el primer `apply` de producción completado, health checks del ALB en verde, smoke test (`PRODUCTION_RUNBOOK.md`, §8) pasado.
4. **RDS/RDS Proxy validados con tráfico real** — `db_instance_class` (`db.t4g.micro`) nunca validado por benchmark local; RDS Proxy nunca probado con multiplexing/conexiones reales.
5. **PostGIS validado en RDS real** — qué versión exacta empaqueta RDS PostgreSQL 16 no se puede verificar sin una instancia real (`RDS_PROXY_FOUNDATION.md`, "Auditoría de PostGIS").
6. **WAF validado y pasado de Count a Enforce cuando corresponda** — falsos positivos de los managed rule groups (hoy en modo Count) y el rate limit de 2000 req/IP/5min, ambos sin confirmar contra tráfico real; transición a Enforce pendiente (`PRODUCTION_RUNBOOK.md`, §12).
7. **Alarms/SNS operativos** — `enable_alarm_actions=false`/`create_alarm_sns_topic=false` hoy; sin un destino de alerta real, nadie es notificado cuando una alarma dispara.
8. **Backups reales comprobados** — confirmar que los backups automatizados de RDS efectivamente corren contra la instancia real (no solo que la configuración lo declare).
9. **Ejercicio de restore realizado o aceptado explícitamente** — ningún restore real (PITR/snapshot) se ha ejecutado nunca; si no se hace antes de go-live, debe ser una decisión consciente y documentada, no un olvido.
10. **Capacity validation en AWS** — el perfil RECOMMENDED (`PRODUCTION_RUNBOOK.md`, §17) se validó con benchmarks locales/Docker, nunca contra Fargate/RDS Proxy reales.
11. **Decisión de Multi-AZ tomada explícitamente** — `db_multi_az=false` es el default actual, pero es una decisión de disponibilidad/costo que el negocio debe tomar conscientemente antes de go-live, no dejarla como default implícito: sin Multi-AZ, un fallo de instancia/AZ implica downtime hasta que AWS reemplace la instancia o se restaure desde backup (RTO "por validar", `BACKUP_DR_FOUNDATION.md` §23); con Multi-AZ, el costo de cómputo/storage aproximadamente se duplica. Esta decisión no debe quedar disuelta dentro de "requiere validación AWS" — es una decisión de negocio, independiente de que además su comportamiento técnico (tiempo real de failover) solo pueda confirmarse en AWS.
12. **GO/NO-GO aprobado** — checklist completo de `PRODUCTION_RUNBOOK.md`, §18, revisado por una persona antes de autorizar tráfico real.

### Estado del deployment role (aclaración explícita)

**El "Terraform deployment role" de producción NO está creado ni es operativo hoy.** Lo único que existe en código son las dos policies de alcance ya conocido del bootstrap (`terraform_state_access`, `ecr_push`, ver `AWS_BOOTSTRAP.md` §16), sin adjuntar a ningún role. El flujo previsto: la identidad de bootstrap puede usarse **temporalmente**, y solo si se autoriza explícitamente, para ejecutar el bootstrap y para obtener el primer `terraform plan` de producción (evidencia de qué recursos/acciones toca realmente ese plan); a partir de esa evidencia se crea o ajusta una identidad de deployment de mínimo privilegio, específica para `environments/prod`. **En ningún punto de este flujo se crea o se usa `AdministratorAccess`/`PowerUserAccess` como solución permanente.**

### Validación requerida en AWS que no aparece arriba

- Todos los thresholds de las 14 alarmas de CloudWatch — baseline razonado, no calibrado con tráfico real (cubierto también por "Alarms/SNS operativos" arriba).
- Fargate — cold start real, CPU credits/throttling bajo el perfil 1024/2048 elegido (cubierto también por "Capacity validation" arriba).
- **Versión exacta de PostGIS en RDS PostgreSQL 16** — la migración inicial (`CREATE EXTENSION IF NOT EXISTS postgis`) habilita la extensión automáticamente, pero qué versión exacta empaqueta RDS para esa engine version no se puede verificar sin una instancia real (`RDS_PROXY_FOUNDATION.md`, "Auditoría de PostGIS"). **AWS runtime validation required** antes de cualquier migración real de datos geoespaciales — no se cambia ninguna migración por esto (ya listado como punto 5 de BEFORE PUBLIC GO-LIVE arriba).

## Mejoras opcionales (OPTIONAL IMPROVEMENT)

- **Terraform en CI**: `.github/workflows/ci.yml` no ejecuta `terraform fmt -check`/`init -backend=false`/`validate` — se hizo manualmente en esta auditoría. Incorporarlo como job de CI evitaría depender de que cada persona lo recuerde.
- **Restringir el egress HTTPS `0.0.0.0/0` de ECS** a prefix lists administradas de AWS, una vez identificados con evidencia real todos los hosts públicos que la aplicación necesita alcanzar.
- **AWS Backup / cross-region DR**: deliberadamente diferido (ver `BACKUP_DR_FOUNDATION.md`, §19-20) hasta que exista una necesidad concreta de negocio.
- **Execution Role de `backend_migrate`/`backend_bootstrap` sigue compartido con `backend`** (los tres usan `aws_iam_role.execution`, con acceso a los secretos maestro/aplicación de DB — todos ellos ya necesitan uno u otro por diseño, ver `RDS_PROXY_FOUNDATION.md`). Separar un Execution Role por task dentro de la propia familia backend sería una reestructuración de policies mayor sin una brecha real que lo justifique hoy (las tres tasks ya son de la misma familia de confianza administrativa/aplicación) — documentado como hardening posible, no aplicado en esta ronda.

## Limitaciones conocidas (KNOWN LIMITATION)

- **Arquitectura single-region**: sin estrategia cross-region. Un fallo regional completo no tiene recuperación automatizada — RTO indefinido (`BACKUP_DR_FOUNDATION.md`, §20).
- **`db_multi_az=false` por defecto**: sin failover automático ante fallo de instancia/AZ salvo que se active explícitamente.
- **Sin ejercicio de DR real**: todos los RTO de `BACKUP_DR_FOUNDATION.md` están marcados "por validar", no medidos.
- **RDS Proxy sin observabilidad propia en CloudWatch**: namespace/métricas no verificables sin acceso a AWS real (documentado explícitamente en `WAF_CLOUDWATCH_FOUNDATION.md`).
- **`format:check` del frontend reporta 35 archivos con diferencias de formato** — anomalía local preexistente (probablemente diferencias de terminador de línea/entorno Windows vs. el entorno donde se generaron), confirmada en este ciclo como **no atribuible a ningún cambio de Fase 4C** (`git status`/`git diff --stat` sobre esos archivos no muestra ninguna modificación pendiente). No bloquea CI (`.github/workflows/ci.yml` sí ejecuta `format:check`, y el pipeline reporta verde según el historial de GitHub Actions de la rama) — ver nota de entorno en la sección de resultados de tests de este ciclo.

---

## Hallazgos de esta auditoría (Fase 4C.7)

Ningún hallazgo de esta auditoría califica como defecto crítico bloqueante de seguridad. Los hallazgos concretos:

1. **Task Role compartido backend/frontend — CORREGIDO en esta ronda**: el frontend usaba `aws_iam_role.task` (renombrado a `aws_iam_role.backend_task`), heredando formalmente los permisos S3 del backend aunque nunca los invocaba (nginx no ejecuta AWS SDK). Ahora el frontend no declara `task_role_arn` en absoluto — sin ningún permiso runtime de AWS. El Execution Role también se separó: el frontend usa `aws_iam_role.frontend_execution` (solo `AmazonECSTaskExecutionRolePolicy`), sin acceso a `secretsmanager:GetSecretValue` sobre los secretos de DB que sí tiene el Execution Role de la familia backend. Ver "Arquitectura de Task Roles" abajo.
2. **`cleanup_generated_reports.py` no respetaba `ARTIFACT_STORAGE_PROVIDER`** — defecto real, ya corregido en un commit de Fase 4C.5 (`6fa5308`), confirmado con 4 tests dedicados (`tests/test_cleanup_generated_reports.py`).
3. **`.env.production.example` trae `ARTIFACT_STORAGE_PROVIDER=local` — ACLARADO en esta ronda**: se confirmó que este archivo es el ejemplo del despliegue de un solo contenedor vía `docker-compose.prod.yml` (topología actual de Render, filesystem compartido) — `local` es correcto ahí. **Nunca se usa como fuente de configuración en ECS/Fargate**: ahí las variables se inyectan directamente desde Terraform (`modules/ecs/main.tf`), donde `artifact_storage_provider="s3"` ya es el default (`terraform.tfvars.example`) y un `precondition` bloquea `plan`/`apply` si se combina `local` con más de una réplica. Se agregó un aviso explícito al inicio del archivo para que ningún operador confunda ese default de Compose con la recomendación de AWS. Como defensa adicional ya existente en código (`backend/app/main.py:19-26`), la aplicación emite el warning estructurado `artifact_storage_local_in_production` al arrancar si `APP_ENV=production` y `ARTIFACT_STORAGE_PROVIDER=local` coinciden — intencional en Render, una señal observable (no silenciosa) de mala configuración en cualquier otro contexto.
4. **Cero secretos reales, cero credenciales AWS estáticas, cero PostgreSQL público** en todo el repositorio — confirmado por grep exhaustivo (AWS access keys, JWTs reales, private keys, account IDs de 12 dígitos, DB URLs con credenciales). El único JWT encontrado es un ejemplo público de jwt.io usado en un test de redacción de logs. Confirmado de nuevo tras esta ronda de cambios — sin credenciales estáticas introducidas.

### Arquitectura de Task Roles (post-corrección)

| Task Definition | Execution Role | Task Role |
| --- | --- | --- |
| `backend` (ECS Service) | `aws_iam_role.execution` (`ecs-backend-execution`) — pull de imagen, logs, `secretsmanager:GetSecretValue` sobre el secreto de aplicación | `aws_iam_role.backend_task` (`ecs-backend-task`) — S3 mínimo privilegio sobre `evidence/*`/`reports/*` |
| `backend_migrate` | `aws_iam_role.execution` (mismo — necesita el secreto maestro para Alembic) | `aws_iam_role.backend_task` (mismo — sin uso real de S3 en esta task, pero misma familia de confianza administrativa) |
| `backend_bootstrap` | `aws_iam_role.execution` (mismo — necesita el secreto maestro y el de aplicación) | `aws_iam_role.backend_task` (mismo, igual que arriba) |
| `frontend` | `aws_iam_role.frontend_execution` (`ecs-frontend-execution`) — **solo** `AmazonECSTaskExecutionRolePolicy`, sin acceso a ningún secreto | **Ninguno** — `task_role_arn` omitido; el contenedor no tiene ninguna credencial de AWS disponible |

**Frontend runtime**: cero permisos S3, cero permisos DB, cero permisos Secrets Manager de aplicación — ni siquiera indirectamente, porque no declara `secrets` en su Task Definition ni tiene Task Role. Su Execution Role solo puede usarse para las operaciones que ECS necesita para arrancar el contenedor (pull de imagen, logs) — esas credenciales nunca son expuestas al proceso de la aplicación dentro del contenedor (a diferencia del Task Role, el Execution Role lo usa el agente ECS, no el endpoint de metadata de la task).

---

## GO / NO-GO actual

**NO-GO para el `apply` del bootstrap** (`infra/terraform/bootstrap/`), por los 8 puntos de "BEFORE AWS BOOTSTRAP APPLY" arriba (cuenta AWS, credenciales de corta duración, región, nombre de state bucket, nombres ECR, identidad de bootstrap con permisos acotados, `terraform.tfvars` real preparado, revisión humana del plan) — ninguno es un defecto de código: son decisiones/recursos operativos externos al repositorio.

**NO-GO para el primer `terraform apply` del stack productivo** (`infra/terraform/environments/prod/`), por los 8 puntos de "BEFORE FIRST PRODUCTION STACK APPLY" arriba (remote state ya creado y migrado, cuenta/permisos de deployment para producción, ownership del bucket S3, imágenes en el ECR del bootstrap, configuración/secrets de producción, región consistente con el bootstrap, modelo IAM de deployment resuelto lo suficiente, revisión humana del plan) — presupone el bootstrap ya aplicado y verificado.

**Incluso después de resolver ambas listas y aplicar producción por primera vez, el sistema seguiría en NO-GO para tráfico público real** hasta resolver, además, los 12 puntos de "BEFORE PUBLIC GO-LIVE" (dominio/TLS, despliegue AWS exitoso, RDS/RDS Proxy validado con tráfico real, PostGIS validado en RDS real, WAF pasado de Count a Enforce cuando corresponda, alarmas con destino real, backups comprobados, ejercicio de restore, capacity validation en AWS, decisión de Multi-AZ tomada explícitamente, y la aprobación final del checklist GO/NO-GO de `PRODUCTION_RUNBOOK.md` §18).

**El sistema NO puede considerarse production-ready ahora mismo.** Toda la Fase 4C está completa a nivel de código/Infrastructure-as-Code y validada localmente (Terraform, Docker, CI, benchmarks), y la Fase 4D.1 preparó en código el bootstrap — pero "completo en código" y "production-ready" no son lo mismo: "completo en código" significa que `terraform validate` pasa y que la arquitectura descrita es coherente; "production-ready" requiere además que el `apply` del bootstrap y luego el `apply` de producción hayan ocurrido realmente, que la aplicación responda correctamente bajo tráfico real (nunca medido — todos los benchmarks de `PERFORMANCE_BASELINE.md` corrieron contra Docker local, no contra Fargate/RDS Proxy reales), y que las tres listas de blockers estén resueltas en orden. El camino desde aquí es: resolver los 8 puntos de BEFORE AWS BOOTSTRAP APPLY → `plan`/`apply` del bootstrap con revisión humana (`AWS_BOOTSTRAP.md`) → resolver los 8 puntos de BEFORE FIRST PRODUCTION STACK APPLY (incluye migrar el state a ese bootstrap ya aplicado) → `plan`/`apply` de producción con revisión humana (`PRODUCTION_RUNBOOK.md`, §5) → ejecutar la secuencia de migración/bootstrap de base de datos (§6) → smoke test (§8) → resolver los 12 puntos de BEFORE PUBLIC GO-LIVE → recién entonces evaluar el checklist GO/NO-GO completo (`PRODUCTION_RUNBOOK.md`, §18) para el primer tráfico real.
