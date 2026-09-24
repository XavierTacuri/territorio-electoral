# AWS Bootstrap — Territorio Electoral (Fase 4D.1)

Preparación, mediante código y documentación, de los recursos que deben existir en AWS **antes** del primer `terraform apply` del stack productivo (`infra/terraform/environments/prod`). Complementa, sin duplicar:

- [`TERRAFORM_FOUNDATION.md`](./TERRAFORM_FOUNDATION.md) — ya anticipaba este bootstrap en su sección "Terraform state".
- [`PRODUCTION_RUNBOOK.md`](./PRODUCTION_RUNBOOK.md), §2 — "Remote Terraform state — BLOCKER BEFORE REAL PRODUCTION APPLY".
- [`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md) — matriz de preparación y blockers.

**Estado al cierre de Fase 4D.1: código de bootstrap preparado en `infra/terraform/bootstrap/`, validado localmente (`fmt`/`init -backend=false`/`validate`). Ningún recurso de AWS ha sido creado. Ningún `terraform plan`/`apply`/`destroy` se ha ejecutado contra una cuenta AWS real.**

---

## 0. Dos despliegues distintos, nunca el mismo evento

Este documento y `PRODUCTION_READINESS.md` distinguen explícitamente dos `terraform apply` diferentes, en dos directorios distintos, con prerrequisitos distintos:

- **(A) BOOTSTRAP APPLY** — `terraform apply` en `infra/terraform/bootstrap/`. Es, en sí mismo, **el primer contacto real de este proyecto con AWS**. Crea únicamente el state bucket, los dos repositorios ECR y las dos IAM policies de alcance conocido (§3). No depende de ningún otro `apply`.
- **(B) PRODUCTION STACK APPLY** — `terraform apply` en `infra/terraform/environments/prod/`. Crea VPC, ECS, RDS, ALB, WAF, CloudWatch, S3 lifecycle. **Depende de que (A) ya se haya ejecutado y verificado** — necesita el state bucket y los repositorios ECR que (A) crea.

Una tercera categoría, **BEFORE PUBLIC GO-LIVE**, no es un `apply` en absoluto — es lo que falta resolver, con el stack productivo (B) ya aplicado, antes de exponer el sistema a tráfico público real.

Las tres listas completas y exhaustivas de requisitos (BEFORE AWS BOOTSTRAP APPLY / BEFORE FIRST PRODUCTION STACK APPLY / BEFORE PUBLIC GO-LIVE) viven en `PRODUCTION_READINESS.md`, sección "Blockers reales — tres momentos distintos", para no duplicarlas en dos documentos — este documento detalla el *cómo* de la primera lista (bootstrap); `PRODUCTION_READINESS.md` es la fuente única de verdad del *qué* de las tres.

## 1. Propósito

Antes de que el stack productivo (`environments/prod`) pueda tener un `terraform apply` real, deben existir en AWS, de forma independiente a ese stack:

1. Un bucket S3 dedicado para el Terraform state remoto de `environments/prod` (y de cualquier entorno futuro).
2. Dos repositorios ECR (backend, frontend) donde publicar las imágenes de contenedor que consumirán `var.backend_image`/`var.frontend_image`.
3. Las policies IAM cuyo alcance es enteramente conocido hoy (acceso al propio state bucket, push/pull a los propios repositorios ECR) — listas para adjuntarse a la identidad de deployment cuando se decida.

Estos recursos **no pueden vivir dentro del state de `environments/prod`** porque ese state va a residir, precisamente, en el bucket que este bootstrap crea — sería una dependencia circular (el bucket que guarda el state no puede depender de un backend remoto que todavía no existe).

## 2. Arquitectura

```
infra/terraform/
  bootstrap/            <- Fase 4D.1 (este documento). State LOCAL, permanente.
    state bucket S3 (Terraform state remoto)
    ECR backend
    ECR frontend
    IAM: policy de acceso al state bucket
    IAM: policy de push/pull ECR
  environments/
    prod/                <- Fase 4C.1-4C.7. Backend "s3" parcial (Fase 4D.1),
                            sin migrar todavía. VPC, ECS, RDS, ALB, WAF,
                            CloudWatch, S3 lifecycle.
```

El bootstrap es deliberadamente pequeño: **no** contiene VPC, ECS, RDS, ALB, WAF, ni ningún recurso de aplicación. Tampoco adopta el bucket de artifacts de la aplicación (ese bucket sigue siendo un blocker separado, ver §12).

## 3. Qué crea este bootstrap (cuando se aplique)

| Recurso | Archivo | Propósito |
| --- | --- | --- |
| `aws_s3_bucket.terraform_state` | `state_bucket.tf` | Bucket dedicado exclusivamente a Terraform state |
| `aws_s3_bucket_versioning.terraform_state` | `state_bucket.tf` | Versioning `Enabled` |
| `aws_s3_bucket_server_side_encryption_configuration.terraform_state` | `state_bucket.tf` | SSE-S3 (AES256) |
| `aws_s3_bucket_ownership_controls.terraform_state` | `state_bucket.tf` | `BucketOwnerEnforced` (ACLs deshabilitadas) |
| `aws_s3_bucket_public_access_block.terraform_state` | `state_bucket.tf` | Las 4 protecciones activas |
| `aws_s3_bucket_policy.terraform_state` | `state_bucket.tf` | Deny si `aws:SecureTransport=false` |
| `aws_ecr_repository.backend` | `ecr.tf` | Repositorio ECR del backend, `IMMUTABLE`, scan on push |
| `aws_ecr_repository.frontend` | `ecr.tf` | Repositorio ECR del frontend, `IMMUTABLE`, scan on push |
| `aws_iam_policy.terraform_state_access` | `iam.tf` | Acceso mínimo (GetObject/PutObject + lockfile) al state bucket |
| `aws_iam_policy.ecr_push` | `iam.tf` | Push/pull únicamente sobre los dos repositorios ECR de este proyecto |

## 4. Qué NO crea este bootstrap

- VPC, security groups, ECS, ALB, RDS, RDS Proxy, WAF, CloudWatch — eso es `environments/prod` (Fase 4C, ya completa a nivel de código).
- El bucket de artifacts de la aplicación (evidence/reports) — sigue siendo un blocker operativo separado (`s3_artifact_bucket`, ver `BACKUP_DR_FOUNDATION.md`). **No se adopta silenciosamente aquí.**
- Ningún Route53 hosted zone ni certificado ACM — requieren un dominio real, todavía no decidido.
- Ningún secreto real en Secrets Manager — pertenecen a `environments/prod` (RDS) o a Fase 4D.2 (secrets de aplicación).
- Un IAM Role de "Terraform deployment" con permisos sobre VPC/ECS/RDS/WAF/CloudWatch/Secrets Manager — ver §7.
- Ningún `aws_iam_openid_connect_provider`/role de GitHub Actions — ver §9.
- Ninguna tabla DynamoDB de locking — ver §6.
- Ninguna lifecycle policy de ECR — ver §8.
- Ningún AWS Budget/alarma de costos con email — ver §11.

## 5. Remote state — detalle de configuración

| Propiedad | Valor | Razón |
| --- | --- | --- |
| Versioning | `Enabled` | Recuperar una versión anterior del `tfstate` ante overwrite/corrupción/error humano. Sin política de expiración de versiones antiguas — cleanup diferido, sin decisión operativa tomada todavía. |
| Encryption | SSE-S3 (`AES256`) | Cifrado en reposo sin crear una CMK KMS únicamente por complejidad. Migración futura a SSE-KMS: crear la CMK, cambiar `apply_server_side_encryption_by_default.sse_algorithm` a `aws:kms` y añadir `kms_master_key_id` — objetos existentes no se re-cifran retroactivamente, solo los nuevos. |
| Ownership | `BucketOwnerEnforced` | Deshabilita ACLs por completo — mecanismo recomendado por AWS, compatible con Public Access Block. |
| Public Access Block | Las 4 protecciones activas | Terraform state contiene información sensible de infraestructura — nunca debe ser público. |
| Secure transport | `Deny` si `aws:SecureTransport=false` | Bucket policy sin account IDs hardcodeados (Principal `"*"` acotado por Resource + condición). |
| `prevent_destroy` | `true` | Destruir este bucket por accidente impide administrar el resto de la infraestructura. Ver "Eliminación controlada" abajo. |

### Eliminación controlada del state bucket

`prevent_destroy = true` rechaza cualquier `terraform destroy`/reemplazo que intente eliminar `aws_s3_bucket.terraform_state`, incluso por accidente (p. ej. un cambio de nombre que fuerce recreate). Para eliminarlo **intencionalmente**:

1. Confirmar que ningún entorno depende ya de este bucket como backend (todos los `environments/*` migrados a otro backend, o el proyecto completo dado de baja).
2. Editar `state_bucket.tf` y comentar/eliminar el bloque `lifecycle { prevent_destroy = true }`.
3. `terraform apply` (este cambio por sí solo no destruye nada, solo quita la protección).
4. `terraform destroy -target=aws_s3_bucket.terraform_state` (o el `destroy` completo del bootstrap).
5. Revertir el paso 2 si el bootstrap se sigue usando para otra cosa.

## 6. State locking

Backend `s3` con `use_lockfile = true` (locking nativo, soportado desde Terraform 1.10+; este proyecto usa 1.16.x). **No se crea ninguna tabla DynamoDB** — el locking basado en DynamoDB para el backend S3 está deprecated en versiones modernas de Terraform; `use_lockfile` logra el mismo resultado (un objeto de lock `*.tflock` en el propio bucket S3) sin un recurso adicional que mantener.

## 7. Backend parcial en `environments/prod`

`infra/terraform/environments/prod/versions.tf` ya declara:

```hcl
backend "s3" {}
```

Vacío a propósito (**partial backend configuration**) — ni bucket, ni key, ni region, ni credenciales viven en el repositorio. `terraform init -backend=false` (el único modo usado hasta ahora, y el único documentado en `infra/terraform/README.md`) ignora este bloque por completo y sigue sin contactar AWS ni requerir `-backend-config` — confirmado en esta subfase (`terraform init -backend=false` + `terraform validate` de `environments/prod` siguen en PASS tras este cambio).

Cuando se autorice la migración real (fuera del alcance de Fase 4D.1):

```bash
cd infra/terraform/environments/prod
terraform init \
  -backend-config="bucket=<state_bucket_name del output de bootstrap>" \
  -backend-config="key=territorio-electoral/prod/terraform.tfstate" \
  -backend-config="region=<misma region que aws_region>" \
  -backend-config="use_lockfile=true"
```

**Nunca pasar `access_key`/`secret_key` vía `-backend-config`**: esos valores pueden terminar persistidos en el directorio `.terraform/` local (metadata de backend), que no está pensado para guardar secretos de larga vida. Terraform debe obtener credenciales por los mecanismos estándar de AWS — perfil de AWS CLI, variables de entorno `AWS_*` de la sesión, un rol asumido, o (más adelante) OIDC en CI.

## 8. State key

Key determinista para producción, sin workspaces (solo existe `prod` hoy, igual que `environments/prod`):

```
territorio-electoral/prod/terraform.tfstate
```

Sin datos personales. Un entorno futuro (`environments/staging`, si llegara a existir) usaría `territorio-electoral/staging/terraform.tfstate` en el mismo bucket.

## 9. Secuencia exacta: bootstrap → migración de state → production plan (documentada, NO ejecutada)

Orden estricto — cada paso presupone que el anterior se completó y se verificó, nunca se saltan pasos para "ganar tiempo":

1. **El Terraform del bootstrap continúa con state local** (§10) — no requiere ninguna acción previa, es su estado por diseño.
2. **Ejecutar el `terraform plan` del bootstrap** contra la cuenta/región elegidas (`infra/terraform/bootstrap/`).
3. **Revisar ese plan** (revisión humana, mismo criterio que cualquier `plan` real — `PRODUCTION_RUNBOOK.md` §5) — confirmar que solo toca los recursos de §3 (state bucket, ECR, IAM policies), nada más.
4. **`terraform apply` del bootstrap** — el primer contacto real de este proyecto con AWS.
5. **Verificar manualmente** (AWS Console o CLI) el state bucket (versioning `Enabled`, encryption configurada, Public Access Block activo, bucket policy de `SecureTransport`) y los dos repositorios ECR — no asumir que el `apply` fue exitoso sin verificarlo.
6. **Inicializar `environments/prod` con el backend S3 real**: `terraform init` con los 4 `-backend-config` de §7 (bucket/key/region/`use_lockfile`) — el backend parcial `backend "s3" {}` ya está en `versions.tf` desde esta subfase.
7. **Migrar el state de `environments/prod`**: Terraform pregunta si se desea copiar el state local existente al backend remoto recién inicializado — responder que sí; luego verificar con `terraform state list` (ya contra el backend remoto) que la lista de recursos coincide exactamente con la que mostraba el state local antes de migrar.
8. **Verificar state remoto y locking**: respaldar el `terraform.tfstate` local anterior (copiarlo fuera del repositorio, con fecha, sin eliminarlo todavía) y confirmar el locking ejecutando dos `terraform plan` casi simultáneos (prueba deliberada) — el segundo debe esperar o fallar por lock, nunca correr ambos sobre el mismo state a la vez.
9. **Solo después de (1)-(8) verificados, preparar el `terraform plan` de producción** — este paso es un evento distinto (BEFORE FIRST PRODUCTION STACK APPLY, `PRODUCTION_READINESS.md`), con sus propios prerrequisitos (imágenes en ECR, ownership del bucket de artifacts, secrets, etc.), no una continuación automática de la migración de state.

Solo después de confirmar (8) de forma explícita (no automática) que el remoto es correcto y accesible por el equipo se archiva el `tfstate` local respaldado — nunca eliminarlo inmediatamente sin ese respaldo.

**Ninguno de estos 9 pasos se ha ejecutado en Fase 4D.1.**

## 10. State del propio bootstrap

El bootstrap (`infra/terraform/bootstrap`) usa **state local**, de forma deliberada y — a diferencia de `environments/prod` — **permanente por defecto**: no puede usar como backend el bucket que él mismo crea sin una dependencia circular en su primer `apply`.

Estrategia elegida para esta subfase: **(A) el state del bootstrap permanece local y protegido** (respaldado manualmente por el operador, nunca commiteado — ya cubierto por `.gitignore`, ver §14). Es la opción de menor complejidad y evita cualquier dependencia circular.

Alternativa documentada para más adelante, si el equipo lo decide explícitamente: **(B)** una vez que el state bucket ya existe (tras el primer `apply` del bootstrap), migrar el propio state del bootstrap a una key separada del mismo bucket (p. ej. `territorio-electoral/bootstrap/terraform.tfstate`) con un `terraform init -migrate-state` **dentro del propio directorio `bootstrap/`** — sin circularidad porque el bucket ya existiría en ese momento. No se resuelve mediante ningún truco de dependencia circular (p. ej. no se intenta que el bootstrap se auto-referencie en su primer `apply`).

**El state del bootstrap y el state remoto de `environments/prod` son, y deben seguir siendo, dos states distintos** — nunca la misma key, incluso si en el futuro (opción B) ambos terminan viviendo en el mismo bucket físico. Key de producción: `territorio-electoral/prod/terraform.tfstate` (§8). Key del bootstrap, si algún día se migra (opción B): `territorio-electoral/bootstrap/terraform.tfstate` — prefijo distinto, nunca superpuesto. Mezclarlos en una sola key haría que un `apply` de un stack pudiera sobrescribir o corromper el state del otro.

## 11. ECR — backend y frontend

Dos repositorios separados (nunca uno compartido):

| Propiedad | Valor | Razón |
| --- | --- | --- |
| `image_tag_mutability` | `IMMUTABLE` | El mismo tag no puede sobrescribirse accidentalmente — obliga a que cada deployment use un tag único (SHA de commit) o un digest. |
| `image_scanning_configuration.scan_on_push` | `true` | Escaneo básico de vulnerabilidades en cada push (`basic scanning`, incluido sin costo adicional en ECR). Escaneo avanzado (Amazon Inspector, `enhanced scanning`) queda diferido — no hay evidencia todavía de que la escala del proyecto lo requiera; se documenta como mejora futura, no como parte de esta subfase. |
| `encryption_configuration.encryption_type` | `AES256` | Cifrado en reposo gestionado por AWS, mismo criterio que el state bucket (sin CMK por complejidad). |

**Estrategia de tags**: `commit SHA -> tag único`. Un build de CI etiqueta la imagen como `<repository_url>:<git_sha_corto_o_completo>` y la publica; `environments/prod` referencia esa URI completa en `backend_image`/`frontend_image`. Nunca `:latest` — ya documentado en `ECS_ALB_FOUNDATION.md`, "Estrategia de imágenes", y reforzado aquí porque `IMMUTABLE` haría fallar un segundo push con el mismo tag de todos modos.

**Lifecycle policy: diferida** (no hay `aws_ecr_lifecycle_policy` en este bootstrap). Sin una decisión operativa sobre cuántas imágenes o cuántos días de ventana de rollback preservar, escribir una política ahora arriesga borrar una imagen todavía necesaria para un rollback real. Cuando exista esa decisión, la política debe garantizar como mínimo: preservar la imagen actualmente desplegada, preservar una ventana razonable de imágenes anteriores para rollback, y preservar los tags más recientes — nunca una expiración agresiva por edad sin relación con qué está desplegado.

## 12. Outputs del bootstrap

`state_bucket_name`, `state_bucket_arn`, `backend_ecr_repository_url`, `backend_ecr_repository_arn`, `frontend_ecr_repository_url`, `frontend_ecr_repository_arn`, `terraform_state_access_policy_arn`, `ecr_push_policy_arn`. Ninguno sensible (nombres/ARNs de recursos, no contenido de secretos).

## 13. AWS region

`var.aws_region` en el bootstrap (default **`us-east-2` — US East (Ohio)**, igual que `environments/prod`) es una variable explícita, no una decisión silenciosa. **Debe coincidir con la región que use `environments/prod`** — varios de sus recursos son regionales.

**Decisión para el primer deployment real de esta cuenta**: `us-east-2` (Ohio). La cuenta AWS disponible hoy permite `us-east-2`; `us-east-1` (N. Virginia) exigiría activar características avanzadas de la cuenta que deliberadamente no se activan para esta prueba. Por eso el default de `aws_region` en ambos stacks (`infra/terraform/bootstrap/variables.tf`, `infra/terraform/environments/prod/variables.tf`) y ambos `terraform.tfvars.example` es `us-east-2` — sigue siendo una variable explícita y overridable (una cuenta distinta, sin esa restricción, puede pasar cualquier otra región vía `terraform.tfvars`), no una región hardcodeada dentro de ningún recurso.

### ACM y región

Un certificado ACM usado por un Application Load Balancer es **regional**: debe existir en la misma región que el ALB. No se crea ningún ACM en esta subfase porque el dominio todavía no está decidido (ver `PRODUCTION_READINESS.md`, blocker de dominio/TLS) — cuando se decida, el certificado se solicita en `us-east-2` (o la región que en ese momento tenga `environments/prod`, si cambiara), nunca en una región distinta a la del ALB.

## 14. Account ID

Ningún account ID hardcodeado en el repositorio (confirmado por auditoría de seguridad de esta subfase — ver §17 más abajo). Cuando haga falta referenciarlo dentro de un recurso Terraform (p. ej. una policy que necesite el ARN completo de un rol), se usará `data "aws_caller_identity" "current"` — pero **no** se añade ese data source al bootstrap todavía, porque ningún recurso de esta subfase lo necesita y un data source de este tipo obligaría a contactar AWS incluso en `terraform validate`/`plan` sin aportar valor real hoy.

## 15. Naming y tagging

Misma convención que `environments/prod`: `name_prefix = "${var.project}-${var.environment}"` (`territorio-electoral-prod`), y las mismas tres tags comunes (`Project`, `Environment`, `ManagedBy`) vía `default_tags` del provider — sin tags empresariales adicionales inventadas. Los repositorios ECR, por defecto, se llaman `<name_prefix>-backend`/`<name_prefix>-frontend`.

## 16. Modelo IAM

```
identidad de bootstrap (humana, permisos acotados a los recursos
de §3, credenciales de corta duración — nunca access keys estáticas)
        |
        v
  [BOOTSTRAP APPLY: crea state bucket, ECR, policies]
        |
        v
  [uso TEMPORAL, solo si se autoriza explícitamente: la misma
   identidad de bootstrap obtiene el primer `terraform plan` de
   environments/prod — evidencia de qué recursos/acciones toca]
        |
        v
Terraform deployment role  <-- NO CREADO NI OPERATIVO EN ESTA SUBFASE
(permisos de mínimo privilegio sobre VPC/ECS/RDS/WAF/CloudWatch/
 Secrets Manager, derivados de ese primer plan)
        |
        v
PRODUCTION STACK APPLY (environments/prod)
```

**Estado actual, sin ambigüedad**: el "Terraform deployment role" de producción **no existe ni es operativo**. Solo existen las dos policies de alcance ya conocido (`terraform_state_access`, `ecr_push`, §5/§11), sin adjuntar a ningún role todavía. Esta subfase prohíbe explícitamente `AdministratorAccess`/`PowerUserAccess` como atajo, y escribir a mano una policy anticipada con wildcards amplios ("por si acaso cubre todo lo que Terraform necesite") sería exactamente el mismo atajo con otro nombre. En su lugar, el flujo previsto es:

1. La identidad de bootstrap ejecuta (A) BOOTSTRAP APPLY.
2. Esa misma identidad **puede reutilizarse temporalmente**, únicamente si se autoriza explícitamente para ese uso puntual, para obtener el primer `terraform plan` real de `environments/prod` — sin `apply` todavía, solo como evidencia de qué servicios/acciones toca ese plan concreto.
3. A partir de esa evidencia se crea o ajusta una identidad de deployment de **mínimo privilegio**, específica para `environments/prod` (`ec2:*Vpc*`, `ecs:*`, `rds:*`, `wafv2:*`, `cloudwatch:*`, `logs:*`, `elasticloadbalancing:*`, `secretsmanager:*`, `iam:*Role*`/`iam:*Policy*` acotados a los roles que crean los módulos, etc.) — documentado aquí como procedimiento a seguir, no resuelto de antemano.
4. Las dos policies creadas por este bootstrap (`terraform_state_access_policy_arn`, `ecr_push_policy_arn`, outputs de §12) se adjuntan a esa identidad de deployment.
5. Recién con esa identidad de mínimo privilegio (nunca con la identidad de bootstrap de forma permanente) se ejecuta (B) PRODUCTION STACK APPLY.

**En ningún punto de este flujo la identidad de bootstrap se convierte en la identidad permanente de deployment de producción**, y en ningún punto se usa `AdministratorAccess`/`PowerUserAccess` como solución definitiva.

## 17. Bootstrap identity

Alguien con permisos iniciales suficientes debe ejecutar el `apply` de este bootstrap (crear el state bucket, ECR, las policies). Esa identidad:

- Es de **uso único/infrecuente** (bootstrap y, ocasionalmente, cambios al propio bootstrap) — no es la identidad que ejecuta los `apply` rutinarios de `environments/prod`.
- **No debe convertirse en credenciales estáticas guardadas en el repositorio, en CI, ni en la máquina de una persona de forma permanente.**
- Preferencia: credenciales de corta duración vía AWS SSO / Identity Center, o un rol asumido temporalmente (`sts:AssumeRole`) por una persona autorizada — nunca un usuario IAM con `access_key`/`secret_key` de larga vida.

## 18. CI / GitHub OIDC — estado

**No configurado, deliberadamente, en esta subfase.** El repositorio real (`github.com/XavierTacuri/territorio-electoral`, obtenido de `git remote -v` local, sin exponer ningún secreto) sería el `sub` esperado en una futura trust policy de un `aws_iam_openid_connect_provider` + role, con una condición del tipo `repo:XavierTacuri/territorio-electoral:ref:refs/heads/main` (o el ref que se decida) — patrón documentado aquí como referencia futura, **sin crear ningún recurso OIDC todavía**. CI (`.github/workflows/ci.yml`) sigue siendo solo validación (backend, frontend, e2e, compose) — ningún `terraform apply` se dispara automáticamente desde un push.

## 19. Separación CI / deployment

Sin cambios en esta subfase: CI sigue limitado a validación. Un deployment real a AWS deberá requerir, como mínimo: un `plan` generado y revisado por una persona (`PRODUCTION_RUNBOOK.md` §5), autorización humana explícita, y (cuando exista) un workflow manual o un entorno protegido de GitHub Actions — nunca un `terraform apply` disparado por un push normal a una rama.

## 20. Permisos IAM mínimos sobre el bucket de state

Ya implementados como `aws_iam_policy.terraform_state_access` (§16, `iam.tf`):

- `s3:ListBucket` sobre el bucket, acotado por `s3:prefix` a `territorio-electoral/*`.
- `s3:GetObject`/`s3:PutObject` sobre `territorio-electoral/*` (el `tfstate` real).
- `s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` sobre `territorio-electoral/*.tflock` (los lockfiles del locking nativo).

Sin `s3:*` sobre ningún bucket, ni siquiera sobre el propio state bucket.

## 21. State sensible

El `tfstate` de `environments/prod` va a contener, en algún momento, valores derivados de recursos reales (endpoints, ARNs, IDs) — algunos de RDS/Secrets Manager quedan marcados `sensitive` en los módulos existentes, pero **el archivo de state completo debe tratarse como sensible en su totalidad**, `sensitive`/`ephemeral`/write-only o no: cualquier atacante con lectura del `tfstate` obtiene un mapa detallado de la infraestructura. Nunca se sube a Git (ver §22) y el acceso queda limitado a la policy mínima de §20.

## 22. Auditoría de `.gitignore`

Ya cubre, desde antes de esta subfase:

```
**/.terraform/
*.tfstate
*.tfstate.*
crash.log
crash.*.log
*.tfvars
!*.tfvars.example
*.tfplan
override.tf
override.tf.json
*_override.tf
*_override.tf.json
```

`.terraform.lock.hcl` **no** está ignorado (correcto — debe versionarse, fija versiones/checksums de providers). No se encontró ningún hueco real: los nuevos archivos de `infra/terraform/bootstrap/` (`terraform.tfvars.example` incluido) quedan cubiertos por los mismos patrones que ya protegían `environments/prod`. Sin cambios a `.gitignore` en esta subfase.

## 23. Variables del bootstrap

`project`, `environment`, `aws_region`, `state_bucket_name` (sin default, obligatoria), `backend_ecr_repository_name`/`frontend_ecr_repository_name` (opcionales, con fallback a `name_prefix-backend`/`-frontend`), `additional_tags`. Ningún password/access key/secret key en ningún lugar de `variables.tf` ni de `terraform.tfvars.example`.

## 24. Costos

| Recurso | Costo aproximado | Nota |
| --- | --- | --- |
| S3 state bucket | Bajo pero no cero — almacenamiento (un archivo de pocos KB-MB, con versiones) + requests | Costo marginal, no significativo a esta escala |
| ECR | Almacenamiento por GB de imágenes + transferencia de datos en pull | Escala con el número/tamaño de imágenes retenidas — mitigado a futuro por una lifecycle policy (§11, diferida) |
| Escaneo básico de ECR (`scan_on_push`) | Sin costo adicional | Incluido en ECR estándar |
| IAM (policies) | Sin costo | — |

Sin infraestructura de aplicación todavía (VPC/ECS/RDS/ALB/WAF/CloudWatch de `environments/prod` no se ha aplicado). AWS Budgets con una alarma de costo real queda como mejora recomendada para una fase posterior, **una vez exista una dirección de notificación real decidida** — no se crea aquí una alarma con un email de ejemplo/ficticio.

## 25. BEFORE AWS BOOTSTRAP APPLY

Lista exhaustiva de lo que debe resolverse antes de que `terraform apply` en `infra/terraform/bootstrap/` pueda ejecutarse — copia autorizada de `PRODUCTION_READINESS.md`, sección "Blockers reales — tres momentos distintos" (fuente única, mantener ambas en sincronía si se edita una). Ninguno de estos puntos se resuelve en esta subfase — son decisiones del operador humano:

1. **AWS account disponible.**
2. **Método seguro de autenticación de corta duración** para la identidad de bootstrap — nunca `access_key`/`secret_key` estáticas (§17).
3. **Región AWS elegida** (`aws_region`) — **`us-east-2` (Ohio)** ya es el default en ambos stacks para el primer deployment de esta cuenta (§13); confirmar que sigue siendo la región correcta antes del `apply`, o sobrescribirla explícitamente en `terraform.tfvars` si la cuenta cambiara. Debe coincidir con la que use `environments/prod`.
4. **Nombre globalmente único del state bucket** (`state_bucket_name`) decidido — no reversible sin recrear el bucket (y perder el nombre).
5. **Nombres ECR confirmados**, o aceptación explícita de los defaults documentados (`<project>-<environment>-backend`/`-frontend`, §15).
6. **Identidad de bootstrap con permisos suficientes para crear exactamente los recursos de §3** — S3, ECR, IAM `CreatePolicy`. Nunca `AdministratorAccess`/`PowerUserAccess`.
7. **`terraform.tfvars` real del bootstrap preparado localmente** (copiado de `terraform.tfvars.example`) y **no versionado** (§22).
8. **Revisión humana del primer `terraform plan` del bootstrap** antes de cualquier `apply` (§9, paso 3).

**NO forman parte de esta lista** — no bloquean el bootstrap apply, aunque sí bloqueen el production stack apply o el go-live: ownership del bucket de artifacts, dominio, ACM, secrets de aplicación, decisión de Multi-AZ, `db_instance_class`, rollout de WAF (Count → Enforce). El bootstrap no crea, ni depende de, ninguno de esos recursos — ver §4, "Qué NO crea este bootstrap".

## 26. Notas de seguridad

- Cero secretos, cero credenciales AWS estáticas, cero account IDs de 12 dígitos, cero políticas `Resource: "*"` amplias en `infra/terraform/bootstrap/` — confirmado por auditoría explícita en esta subfase (grep de AWS access keys, private keys, account IDs, `password=`, `:latest`). El único wildcard de recurso (`resources = ["*"]` en `ecr_push`) está acotado a una única acción de autenticación (`ecr:GetAuthorizationToken`), exigida por el propio diseño de la API de ECR — no hay ARN de recurso más específico posible para esa acción.
- `prevent_destroy = true` en el state bucket es la única excepción deliberada a "no usar `prevent_destroy` indiscriminadamente" — justificada porque perderlo compromete la capacidad de administrar toda la infraestructura restante.
- Ningún dato personal en ningún nombre de recurso (bucket, repositorio, key de state).

## 27. Troubleshooting

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| `terraform init -backend=false` falla en `environments/prod` tras este cambio | No debería — confirmado en PASS en esta subfase | Revisar que `versions.tf` mantiene `backend "s3" {}` **vacío** (sin bucket/key/region dentro del bloque) |
| `terraform init` (sin `-backend=false`) pide interactivamente `bucket`/`key`/`region` | Comportamiento esperado de un backend parcial sin `-backend-config` | Pasar los 4 `-backend-config` de §7, o seguir usando `-backend=false` mientras no haya backend remoto real |
| `Error creating S3 bucket: BucketAlreadyExists` | El nombre elegido para `state_bucket_name` ya existe globalmente (de otra cuenta) | Elegir otro nombre — los nombres de bucket S3 son únicos a nivel global, no solo por cuenta |
| `terraform destroy` rechaza el state bucket | `prevent_destroy = true` funcionando como se espera | Ver "Eliminación controlada del state bucket", §5 |
| Push a ECR falla con `AccessDenied` | La identidad usada no tiene adjunta `ecr_push` (o no se autenticó con `ecr:GetAuthorizationToken` primero) | Confirmar `aws ecr get-login-password` + adjuntar `ecr_push_policy_arn` a la identidad correspondiente |

---

## Decisiones pendientes antes del primer AWS apply (bootstrap)

Lista exhaustiva de lo que el operador humano debe decidir — nada de esto lo decide este documento ni el código:

1. ~~Región AWS definitiva~~ — **decidida: `us-east-2` (Ohio)**, ya reflejada como default en ambos stacks (bootstrap y `environments/prod` coinciden). Sigue siendo overridable vía `terraform.tfvars` si la cuenta cambiara.
2. Nombre real y único globalmente del state bucket.
3. Quién ejecuta el bootstrap y con qué mecanismo de credenciales de corta duración.
4. Si se usan los nombres de ECR por defecto (`territorio-electoral-prod-backend`/`-frontend`) o nombres explícitos.
5. Cuándo y quién crea el "Terraform deployment role" (§16) — depende del primer `plan` real de `environments/prod`, que sigue sin ejecutarse.
6. Si/cuándo se habilita GitHub OIDC (§18) — no antes de tener el deployment role del punto anterior.
7. Cuándo se ejecuta la migración real del state (§9) — requiere que el bootstrap ya esté aplicado y verificado.
