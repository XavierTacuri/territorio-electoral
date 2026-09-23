# RDS PostgreSQL + RDS Proxy — Fase 4C.3

Este documento describe lo que Fase 4C.3 creó como código en `infra/terraform/`: la capa de datos productiva para Territorio Electoral. Complementa [`TERRAFORM_FOUNDATION.md`](./TERRAFORM_FOUNDATION.md) (red y security groups, Fase 4C.1) y [`ECS_ALB_FOUNDATION.md`](./ECS_ALB_FOUNDATION.md) (ECS/Fargate + ALB, Fase 4C.2), y sigue el destino descrito en [`PRODUCTION_ARCHITECTURE.md`](./PRODUCTION_ARCHITECTURE.md). **Ningún recurso de AWS existe todavía** — no se ejecutó `terraform apply` ni `terraform plan`.

**Revisiones de producción (post-implementación inicial), ambas antes de cualquier commit**:
1. La primera versión conectaba el ECS Service del backend con el usuario MAESTRO de RDS — corregido, ver "Separación de identidades" abajo.
2. La contraseña del usuario de aplicación se generaba con `resource "random_password"` (persistía en el Terraform state) — corregido a `ephemeral "random_password"` + `secret_string_wo`, ver "Manejo de credenciales" abajo.

## Diagrama

```mermaid
flowchart TD
    svc["ECS backend Service (runtime)\nusuario de APLICACION"] -->|"POSTGRES_HOST = proxy endpoint\nTLS (require_tls)"| proxy["RDS Proxy\n(subredes de base de datos)"]
    migrate["migration task (Alembic)\nbootstrap task (crea el rol app)\nusuario MAESTRO"] --> proxy
    proxy -->|"pooling administrado"| rds[("RDS PostgreSQL 16\nstorage_encrypted, Multi-AZ configurable")]
    secretmaster[("Secrets Manager\nsecreto MAESTRO, gestionado por RDS")]
    secretapp[("Secrets Manager\nsecreto APLICACION, creado por Terraform")]
    proxy -. "auth: 2 secret_arn\n(IAM role dedicado)" .-> secretmaster
    proxy -. .-> secretapp
    svc -. "secrets: POSTGRES_PASSWORD\n(secreto app)" .-> secretapp
    migrate -. "secrets: POSTGRES_PASSWORD\n(secreto master)" .-> secretmaster
```

Ninguna flecha llega desde Internet ni desde el ALB — la base de datos y el proxy están completamente aislados en las subredes privadas de base de datos de Fase 4C.1.

## Separación de identidades (revisión de producción)

### Auditoría: ¿el backend usaba el usuario maestro?

**Sí, en la primera versión de esta fase.** Evidencia, siguiendo las referencias de Terraform sin inferir nada:

- `environments/prod/main.tf` pasaba `db_username = var.db_user` a `module.database` → esto se convertía en `aws_db_instance.this.username`, el usuario **maestro** de RDS.
- El mismo `environments/prod/main.tf` pasaba `db_user = var.db_user` a `module.ecs` → el **mismo** valor exacto, usado como `POSTGRES_USER` del contenedor del backend Service.
- `secrets_manager_secret_arns` inyectaba `POSTGRES_PASSWORD = "${module.database.master_user_secret_arn}:password::"` → el secreto **maestro**.

Conclusión: el ECS Service del backend (y, por construcción compartida de los `locals`, también la migration task) se autenticaba como el usuario maestro de RDS. Esto se corrigió antes del commit.

### Diseño final

| Identidad | Quién la usa | Privilegios | Vía |
| --- | --- | --- | --- |
| **Usuario MAESTRO** (`db_master_user`, RDS `username`) | `backend_migrate` (Alembic) y `backend_bootstrap` (crea/actualiza el rol de aplicación) — **nunca** el ECS Service | Administrativos (RDS `rds_superuser`): DDL completo, `CREATE EXTENSION`, `CREATE ROLE` | RDS Proxy, secreto gestionado automáticamente por RDS (`manage_master_user_password = true`) |
| **Usuario de APLICACIÓN** (`db_app_user`, rol de PostgreSQL creado por `backend_bootstrap`) | ECS Service del backend, en runtime | Solo DML (`SELECT`/`INSERT`/`UPDATE`/`DELETE`) + `USAGE` sobre secuencias, en el esquema `public`. **Sin** `CREATEROLE`, `CREATEDB`, `rds_superuser` ni capacidad de crear extensiones | RDS Proxy, secreto creado por Terraform (`ephemeral "random_password"` + `aws_secretsmanager_secret` con `secret_string_wo` — el password nunca queda en el Terraform state, ver "Manejo de credenciales") |

RDS Proxy tiene **dos** bloques `auth` (uno por secreto) — nunca más de los dos que realmente necesitan conectarse a través de él. Distingue qué identidad usar por el `username` que cada conexión entrante presenta.

## Bootstrap administrativo vs. migraciones Alembic vs. runtime

| Etapa | Qué hace | Identidad | Dónde vive |
| --- | --- | --- | --- |
| **A. Bootstrap administrativo** | Crea/actualiza el rol `db_app_user` con privilegios DML mínimos (`GRANT`s + `ALTER DEFAULT PRIVILEGES` para que las tablas que Alembic cree en el futuro hereden el acceso automáticamente) | MAESTRO | `aws_ecs_task_definition.backend_bootstrap` (nuevo en esta revisión), invocación manual (`aws ecs run-task`), nunca un `aws_ecs_service` |
| **B. Migraciones Alembic normales** | `alembic upgrade head` — DDL de esquema, y (solo en la primera migración del historial) `CREATE EXTENSION IF NOT EXISTS postgis` | MAESTRO | `aws_ecs_task_definition.backend_migrate` (Fase 4C.2, sin cambios de código en esta revisión más allá de qué secreto recibe) |
| **C. Runtime del backend** | Servir tráfico HTTP normal — solo DML | APLICACIÓN | `aws_ecs_service.backend` |

La aplicación nunca hereda privilegios administrativos solo porque el bootstrap los necesitó — son procesos, roles de PostgreSQL y (en A y B) tasks completamente distintos del Service que sirve tráfico.

### Cómo se crea/actualiza el rol de aplicación (sin exponer su contraseña)

`aws_ecs_task_definition.backend_bootstrap` (`modules/ecs/main.tf`) ejecuta, como su `command`, un script Python embebido que reutiliza `psycopg` (ya presente en la imagen del backend — `requirements.txt` — **cero cambios de código de aplicación**, ningún archivo nuevo bajo `backend/`):

```python
# Resumen (script completo en modules/ecs/main.tf, local.db_bootstrap_script):
# 1. Conecta a POSTGRES_HOST (RDS Proxy) con las credenciales MAESTRAS.
# 2. CREATE ROLE <app_user> WITH LOGIN PASSWORD %s (o ALTER ROLE si ya existe) — parametrizado, sin concatenar el password en el SQL.
# 3. GRANT CONNECT/USAGE/SELECT,INSERT,UPDATE,DELETE sobre el esquema public al rol de aplicacion.
# 4. ALTER DEFAULT PRIVILEGES FOR ROLE <master> ... GRANT ... TO <app_user>
#    — para que las tablas que Alembic cree DESPUES tambien queden accesibles, sin volver a correr el bootstrap.
```

Usa `psycopg.sql.Identifier()` para los nombres de rol/base de datos (nunca concatenación de strings) y parámetros `%s` para el password — sin riesgo de inyección SQL, aunque los valores provienen de variables de Terraform (entrada de operador, no de usuario final). Es **idempotente**: seguro de invocar más de una vez (por ejemplo, tras rotar la contraseña de aplicación).

**Orden recomendado desde cero**: bootstrap (una sola vez; `ALTER DEFAULT PRIVILEGES` cubre cualquier tabla futura) → `alembic upgrade head` (crea el esquema, ya heredado automáticamente por el rol de aplicación) → desplegar el ECS Service. Ver "Secuencia completa de bootstrap" más abajo.

## Auditoría de PostGIS

Búsqueda exhaustiva en `backend/alembic/versions/` (`CREATE EXTENSION`, `postgis`, `Geometry`, `Geography`, `geoalchemy`, sin asumir que Docker/CI pasando implique que RDS también lo haría):

**Hallazgo**: `backend/alembic/versions/20260803_0001_users_roles_auth.py`, línea 16:

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    ...
```

- `revision = "20260803_0001"`, `down_revision = None` → es la **primera** migración del historial completo (la raíz de la cadena de Alembic).
- Es la **primera línea** de su `upgrade()`, antes de cualquier `CREATE TABLE`.

**Conclusión**: `alembic upgrade head` contra una RDS PostgreSQL completamente vacía **sí** crea la extensión PostGIS automáticamente, como parte de la primerísima migración — **siempre que la conexión use un usuario con privilegio suficiente** (`CREATE EXTENSION` requiere `rds_superuser` en RDS, que el usuario maestro tiene automáticamente; el usuario de aplicación, deliberadamente, no). No se modificó ni se necesitó modificar ninguna migración histórica — el mecanismo ya existía, correcto, desde el primer commit del historial de Alembic. No se creó ningún paso de bootstrap adicional específico para PostGIS: la migration task (identidad MAESTRA) ya lo resuelve.

Esto es un hallazgo distinto del de la separación de identidades: el gap real no era PostGIS (ya resuelto por el historial existente, confirmado con evidencia), sino la ausencia de un mecanismo para crear el rol de aplicación de bajo privilegio — eso es lo que `backend_bootstrap` resuelve.

**Riesgo documentado, no resuelto en esta fase**: la versión de PostGIS que RDS empaqueta para PostgreSQL 16 no es elegible independientemente (depende de lo que AWS incluya para esa engine version) y podría no ser exactamente `3.4` como en Docker. Verificar compatibilidad de extensión antes de cualquier migración real de datos geoespaciales a RDS.

## Secuencia completa de bootstrap desde cero

```
1. RDS PostgreSQL disponible (aws_db_instance)
2. RDS Proxy + sus dos secretos (master, app) disponibles
3. Bootstrap administrativo (backend_bootstrap, identidad MAESTRA):
   crea/actualiza el rol de aplicacion + sus privilegios DML minimos
4. alembic upgrade head (backend_migrate, identidad MAESTRA):
   CREATE EXTENSION IF NOT EXISTS postgis (primera migracion) + resto del esquema
   — las tablas nuevas heredan automaticamente el acceso del rol de aplicacion (paso 3)
5. Desplegar/actualizar ECS Service backend (identidad de APLICACION)
6. Desplegar/actualizar ECS Service frontend (sin credenciales de DB)
```

El ECS Service del backend **nunca** es responsable de inicializar administrativamente la base — los pasos 3 y 4 son tasks de un solo uso (`aws ecs run-task`), no servicios, y ninguno de los dos se ejecuta automáticamente por réplica.

## Versión de PostgreSQL

`engine_version = "16"` (solo el major). Docker/CI usan `postgis/postgis:16-3.4` (PostgreSQL 16) — esta fase iguala esa major sin forzar ninguna actualización de motor. Se usa solo el major, no una minor específica, porque fijarla requeriría verificar contra la consola/API de AWS qué minors de PostgreSQL 16 están soportadas por RDS en este momento — verificación que no se puede hacer sin credenciales de AWS en esta fase.

## RDS PostgreSQL — configuración

| Aspecto | Valor | Notas |
| --- | --- | --- |
| `instance_class` | `db.t4g.micro` (default, configurable) | Valor inicial conservador — dimensionamiento definitivo: Fase 4C.6 |
| `allocated_storage` | 20 GiB (default, configurable) | |
| `max_allocated_storage` | 100 GiB (default, configurable) | RDS Storage Autoscaling |
| `storage_type` | `gp3` | Fijo, defaults de gp3 suficientes |
| `storage_encrypted` | `true` | **Invariante, no variable** |
| `publicly_accessible` | `false` | **Invariante, no variable** |
| `multi_az` | `false` (default, configurable) | Ver "Multi-AZ" abajo |
| `backup_retention_period` | 7 días (default, configurable) | |
| `backup_window` / `maintenance_window` | `null` (AWS asigna automáticamente) | |
| `deletion_protection` | `true` (default, configurable) | |
| `skip_final_snapshot` | `false` (default, configurable) | Ver "Final snapshot" abajo |
| `performance_insights_enabled` | `false` (default, configurable) | |
| `apply_immediately` | `false` (fijo) | |
| Parameter group | Ninguno (default de `postgres16`) | Sin necesidad de tuning concreta todavía |
| Enhanced monitoring | No implementado | Requeriría un IAM role adicional dedicado |

### Multi-AZ

- `multi_az = false` (default): instancia única, menor costo, **menor disponibilidad**.
- `multi_az = true`: standby sincrónico + failover automático, aproximadamente el doble de costo.

Decisión deliberadamente diferida a Fase 4C.6, igual que `single_nat_gateway` en Fase 4C.1.

### Deletion protection

`deletion_protection = true` (default): AWS rechaza cualquier eliminación hasta desactivarlo explícitamente. `false` solo para entornos desechables.

### Final snapshot

`skip_final_snapshot = false` (default). `final_snapshot_identifier` usa un nombre **estable** (`"${name_prefix}-db-final-snapshot"`, sin `timestamp()`) — evita un diff de Terraform en cada `plan`. **Revisado de nuevo en esta ronda**: el riesgo de colisión (eliminar y recrear la misma instancia bajo el mismo `name_prefix` chocaría con el snapshot del primer borrado) sigue siendo un caso extremo aceptado, no automatizado — introducir un sufijo dinámico (timestamp, `uuid`) para evitarlo reintroduciría exactamente el problema de diffs permanentes que el identificador estable evita; la mitigación operativa (renombrar/eliminar el snapshot anterior antes de recrear) es preferible a esa complejidad. Sin cambios.

## Manejo de credenciales

**Ninguna contraseña de base de datos existe en texto plano en Terraform versionado, en `terraform.tfvars.example`, en variables, en outputs, en el Terraform state, ni en la documentación.**

- **Usuario maestro**: `manage_master_user_password = true` — RDS genera y administra la contraseña en un secreto propio. Terraform nunca la ve, calcula ni almacena.
- **Usuario de aplicación**: no existe un mecanismo nativo equivalente para un rol de PostgreSQL arbitrario (esa capacidad es exclusiva del usuario maestro de la instancia). La primera versión de este módulo usaba `resource "random_password"` + `aws_secretsmanager_secret_version.secret_string` — un diseño funcional pero que **sí** dejaba el password en el state de Terraform (`random_password.app_user.result` es un atributo de un `resource`, y todo atributo de un `resource` se persiste en el state, aunque Terraform lo marque `sensitive` para ocultarlo de la salida en consola). Una revisión posterior lo reemplazó por:

  ```hcl
  ephemeral "random_password" "app_user" {
    length  = 32
    special = true
  }

  resource "aws_secretsmanager_secret_version" "app_user" {
    secret_id = aws_secretsmanager_secret.app_user.id
    secret_string_wo = jsonencode({
      username = var.db_app_username
      password = ephemeral.random_password.app_user.result
    })
    secret_string_wo_version = var.db_app_secret_version
  }
  ```

  Verificado contra el schema real de los providers ya resueltos (`terraform providers schema -json`, no asumido): `hashicorp/random 3.9.1` ya expone `ephemeral_resource_schemas["random_password"]`, y `hashicorp/aws 5.100.0` ya expone `secret_string_wo`/`secret_string_wo_version` (`write_only: true`) en `aws_secretsmanager_secret_version` — **ningún piso de versión de provider tuvo que subirse**. Sí subió el **piso de Terraform** del módulo (`required_version >= 1.11.0`, antes `>= 1.7.0`): los recursos `ephemeral` requieren Terraform ≥ 1.10, los argumentos write-only ≥ 1.11. Terraform aplica el máximo de los `required_version` de todos los módulos de la configuración, así que esto ya es, de hecho, el piso efectivo de todo `environments/prod` — documentado en `modules/database/versions.tf` y en `environments/prod/versions.tf`, sin duplicar la constraint innecesariamente.

  Un recurso `ephemeral` **nunca** persiste su resultado en el state — es la definición misma del tipo de recurso. Un argumento write-only **nunca** se lee de vuelta ni se guarda en el state. Lo único que Terraform sí conserva es `secret_string_wo_version` (un número entero, no el valor) — es lo que decide *cuándo* reescribir el secreto, nunca *qué* valor escribir. `db_app_secret_version` (default `1`) es ese disparador.

- Se evaluó y se descartó, por ahora, autenticación IAM de base de datos (`iam_database_authentication_enabled`, tokens de corta duración sin contraseña alguna): requeriría que el backend genere/renueve tokens IAM en cada conexión, una integración de código real que **no existe hoy** en `backend/app/db/session.py` — implementarla especulativamente aquí violaría la instrucción explícita de no introducir un diseño no soportado por el repositorio actual. Queda documentada como mejora futura posible, no implementada.

### Rotación futura (manual, no automatizada en esta fase)

1. Incrementar `db_app_secret_version` en `terraform.tfvars`.
2. `terraform apply` — como el `ephemeral.random_password` se re-evalúa en cada operación, esto escribe un valor **nuevo** en Secrets Manager (el disparador `secret_string_wo_version` cambió).
3. Volver a invocar `aws_ecs_task_definition.backend_bootstrap` (`aws ecs run-task`) — su `ALTER ROLE ... WITH LOGIN PASSWORD %s` (rama idempotente "ya existe") sincroniza la contraseña real del rol de PostgreSQL con el nuevo valor del secreto.

Dos pasos deliberadamente manuales y separados (Terraform nunca ejecuta SQL por sí mismo) — no un pipeline de rotación automática, fuera de alcance de esta fase.

### `DATABASE_URL` y caracteres especiales

La aplicación (`backend/app/core/config.py`) ya soporta componentes separados (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`), combinados con `quote_plus()` sobre usuario y contraseña antes de construir la URL. Esta fase usa esa opción, no construye `DATABASE_URL` en Terraform — evita el problema de una contraseña aleatoria con caracteres no válidos sin escapar dentro de una URL. Sin cambios respecto a la versión anterior de este documento.

## Secrets Manager

Dos secretos, cada uno consumido solo por quien realmente lo necesita:

```hcl
# environments/prod/main.tf — module "ecs"
db_master_user       = var.db_master_user
db_master_secret_arn = module.database.master_user_secret_arn   # migrate, bootstrap
db_app_user          = var.db_app_user
db_app_secret_arn    = module.database.app_user_secret_arn      # ECS Service (runtime)
```

`modules/ecs/main.tf` construye el entorno/secretos de cada container a partir de `local.backend_service_environment`/`secrets` (identidad de aplicación, solo el Service) o `local.backend_admin_environment`/`secrets` (identidad maestra, migrate y bootstrap) — nunca los mismos para el Service que para migrate/bootstrap. El sufijo `:password::` extrae la clave JSON `password` de cada secreto (ambos tienen la forma `{"username":"...","password":"..."}` — el de aplicación se construyó deliberadamente igual que el de RDS para esa consistencia).

**El frontend no recibe ningún secreto de base de datos** — su Task Definition nunca declaró una sección `secrets`.

## IAM de RDS Proxy

```json
{
  "Effect": "Allow",
  "Action": ["secretsmanager:GetSecretValue"],
  "Resource": ["<arn del secreto maestro>", "<arn del secreto de aplicacion>"]
}
```

Exactamente los dos secretos que el proxy autentica — sin `secretsmanager:*`, sin `Resource: "*"`.

## IAM de ECS (Task Execution Role)

Ya no es condicional: como `db_master_secret_arn`/`db_app_secret_arn` son obligatorios desde esta fase, `aws_iam_role_policy.execution_secrets` siempre existe, con `Resource` = exactamente esos dos ARNs más cualquier ARN adicional de `secrets_manager_secret_arns` (SECRET_KEY, etc., todavía sin infraestructura propia). Ningún wildcard.

Sin cambios KMS: ambos secretos usan la clave de Secrets Manager por defecto (AWS managed) — no se añadió ningún permiso `kms:*`. Si en el futuro se configura una CMK propia, los consumidores de ese secreto (RDS Proxy, y el Execution Role de ECS) necesitarán el permiso mínimo `kms:Decrypt` sobre esa clave específica — no se agrega preventivamente ahora, documentado para cuando corresponda.

## Application Task Role — sin cambios

La aplicación no consulta Secrets Manager en tiempo de ejecución — el **Task Role** (permisos S3 de Fase 4C.2) no necesita ningún permiso nuevo. Sin cambios en sus policies (renombrado a `aws_iam_role.backend_task` en Fase 4C.7 al separarlo del frontend — mismos permisos, ver `ECS_ALB_FOUNDATION.md`).

## Connection pooling: SQLAlchemy + RDS Proxy

Sin cambios respecto a la versión anterior de este documento: RDS Proxy multiplexa conexiones de aplicación sobre un número menor de conexiones reales a RDS, pero no reemplaza el pool de SQLAlchemy (`pool_pre_ping`/`pool_recycle`, Fase 4B) — son dos capas independientes que cooperan.

### Configuración del pool de RDS Proxy

| Variable | Default | Nota |
| --- | --- | --- |
| `db_proxy_connection_borrow_timeout` | 120s | |
| `db_proxy_max_connections_percent` | 100% | Ver justificación abajo |
| `db_proxy_max_idle_connections_percent` | 50% | |
| `db_proxy_idle_client_timeout` | 1800s | |

`max_connections_percent = 100` se mantiene porque: existe un único RDS Proxy; todo el tráfico normal del backend pasa por él (nunca conexión directa a RDS, dado que el security group de RDS solo acepta desde el SG de RDS Proxy); y el dimensionamiento real (junto con `WEB_CONCURRENCY`/`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/número de tasks) es explícitamente Fase 4C.6, con datos de load/stress testing — no se ajusta especulativamente aquí.

## TLS

`require_tls = true` (default) en RDS Proxy. **Confirmado, sin cambios necesarios**: no existe ningún `sslmode=disable` ni equivalente en el código (`backend/app/core/config.py`, `backend/app/db/session.py`) — psycopg3 (el driver real que usa el backend) negocia TLS automáticamente por el `sslmode` por defecto de libpq (`"prefer"`), y como RDS Proxy lo exige, la negociación se resuelve con TLS. No se desactivó `require_tls` para simplificar nada.

## Migration task y bootstrap task

- **`aws_ecs_task_definition.backend_migrate`**: sin cambios de código en esta revisión más allá de recibir ahora la identidad MAESTRA explícitamente (antes recibía, sin distinción, la misma identidad que terminó siendo master de cualquier forma — el comportamiento observable no cambió, la garantía arquitectónica sí). Sigue sin formar parte de ningún `aws_ecs_service`, corre en subredes privadas de aplicación sin IP pública, usa el mismo security group que el backend, y termina con el exit code real de `alembic upgrade head` (vía `exec`) — un fallo de Alembic se refleja como exit code ≠ 0 de la task.
- **`aws_ecs_task_definition.backend_bootstrap`** (nueva en esta revisión): misma red/security group/ausencia de IP pública que `backend_migrate`, identidad MAESTRA, termina con el exit code real del script Python (`exec python3 <<'PYEOF' ... PYEOF`) — cualquier excepción de psycopg se propaga como exit code ≠ 0.

Ninguna de las dos se convierte en `aws_ecs_service`; ninguna se automatiza en un pipeline CI/CD en esta fase.

## Outputs (no sensibles)

`db_instance_id`, `db_endpoint` (administrativo), `db_port`, `db_proxy_endpoint`, `db_proxy_arn`, `db_username`/`db_app_username` (nombres, no contraseñas), `master_user_secret_arn`, `app_user_secret_arn` (ambos ARNs — nunca contenido). Ningún output contiene una contraseña ni una `DATABASE_URL` completa.

## Costos con impacto permanente

| Recurso | Costo | Notas |
| --- | --- | --- |
| RDS PostgreSQL (instancia) | Por hora + almacenamiento (gp3) + I/O | `db.t4g.micro`/20 GiB por defecto |
| RDS Multi-AZ | Aproximadamente ×2 | Solo si `db_multi_az = true` |
| RDS Proxy | Por hora + capacidad de conexión provisionada | Siempre activo |
| Secrets Manager (2 secretos) | Por secreto-mes | El de aplicación es nuevo en esta revisión; costo marginal |
| Backups automatizados | Incluido hasta el tamaño de instancia; exceso por GB-mes | `db_backup_retention_period` (default 7 días) |
| Performance Insights | Gratis 7 días; costo si se extiende | Deshabilitado por defecto |
| Snapshot final | Por GB-mes | Solo al eliminar la instancia |

Nada de esto se ha creado — no se ejecutó `terraform apply`.

## Limitaciones y riesgos documentados

1. **Versión de PostGIS en RDS**: no verificada contra la API/consola de AWS — confirmar antes de cualquier migración real de datos geoespaciales.
2. **Piso de Terraform elevado a 1.11.0** (solo `modules/database`, efectivo para todo `environments/prod`): requerido por `ephemeral`/`secret_string_wo`. Documentado, no oculto — cualquier operador debe correr Terraform ≥ 1.11 para este stack.
3. **`skip_final_snapshot` + recreación bajo el mismo nombre**: caso extremo documentado, no automatizado (sin cambios).
4. **Sin parameter group personalizado ni enhanced monitoring**: deliberadamente fuera de alcance.
5. **`multi_az`/dimensionamiento/pool de RDS Proxy**: valores conservadores iniciales, pendientes de Fase 4C.6.
6. **Backup/DR completo**: fuera de alcance — Fase 4C.5.
7. **CloudWatch avanzado sobre RDS/RDS Proxy**: fuera de alcance — Fase 4C.4.
8. **Autenticación IAM de base de datos**: evaluada y descartada por ahora (requeriría cambios de código en `backend/app/db/session.py` que no existen hoy) — posible mejora futura, no implementada.
9. **Automatización del bootstrap/migración**: ambas siguen siendo invocaciones manuales (`aws ecs run-task`), no un paso de pipeline — consistente con el alcance de Fase 4C.2/4C.3.

## Validación local

```bash
cd infra/terraform/environments/prod
terraform init -backend=false
terraform validate
terraform fmt -check -recursive ../../..
```
