# Terraform — Territorio Electoral

Infraestructura como código para el despliegue AWS de Territorio Electoral (Fase 4C). Ver la fundación de red/security groups en [`docs/aws/TERRAFORM_FOUNDATION.md`](../../docs/aws/TERRAFORM_FOUNDATION.md), la capa ECS/Fargate + ALB en [`docs/aws/ECS_ALB_FOUNDATION.md`](../../docs/aws/ECS_ALB_FOUNDATION.md), la capa de datos RDS + RDS Proxy en [`docs/aws/RDS_PROXY_FOUNDATION.md`](../../docs/aws/RDS_PROXY_FOUNDATION.md), WAF + CloudWatch/observabilidad en [`docs/aws/WAF_CLOUDWATCH_FOUNDATION.md`](../../docs/aws/WAF_CLOUDWATCH_FOUNDATION.md), S3 lifecycle + backup/DR en [`docs/aws/BACKUP_DR_FOUNDATION.md`](../../docs/aws/BACKUP_DR_FOUNDATION.md), dimensionamiento y evidencia de carga en [`docs/performance/PERFORMANCE_BASELINE.md`](../../docs/performance/PERFORMANCE_BASELINE.md), y el diseño objetivo completo en [`docs/aws/PRODUCTION_ARCHITECTURE.md`](../../docs/aws/PRODUCTION_ARCHITECTURE.md).

**Antes de operar esta infraestructura contra AWS real**: [`docs/aws/PRODUCTION_RUNBOOK.md`](../../docs/aws/PRODUCTION_RUNBOOK.md) (procedimientos de despliegue, migración, rollback, incidentes, Election Day), [`docs/aws/PRODUCTION_READINESS.md`](../../docs/aws/PRODUCTION_READINESS.md) (matriz de preparación y blockers reales — hoy en estado **NO-GO**, ver ese documento) y [`docs/aws/AWS_BOOTSTRAP.md`](../../docs/aws/AWS_BOOTSTRAP.md) (remote state, ECR, modelo IAM — Fase 4D.1, precede a cualquier `apply` de `environments/prod`) son de lectura obligatoria para cualquier operador nuevo.

## Bootstrap (Fase 4D.1)

`infra/terraform/bootstrap/` es un stack Terraform **separado e independiente** de `environments/prod`, que prepara los recursos que deben existir en AWS antes del primer `apply` del stack productivo: el bucket S3 de Terraform state remoto, los repositorios ECR (backend/frontend), y las policies IAM de alcance ya conocido (acceso al propio state bucket, push/pull ECR). Ver [`docs/aws/AWS_BOOTSTRAP.md`](../../docs/aws/AWS_BOOTSTRAP.md) para el detalle completo — **código preparado y validado localmente, ningún recurso creado todavía en AWS**.

## Estado actual (Fase 4C.1 a 4C.7)

- **4C.1 — fundación**: red (VPC, subredes públicas/aplicación/base de datos en 2+ AZ, NAT, endpoint S3) y security groups (límites ALB → ECS → RDS Proxy → RDS).
- **4C.2 — ejecución**: ECS Cluster (Fargate), Task Definitions (backend, frontend, y una task de release `backend-migrate` para Alembic, no adjunta a ningún Service), ECS Services con autoscaling base, ALB con routing por path (`/api/*` → backend, resto → frontend), IAM de mínimo privilegio (Execution Role vs. Task Role).
- **4C.3 — datos**: RDS PostgreSQL 16 (cifrado, privado, backups, Multi-AZ configurable) + RDS Proxy (TLS, autenticado vía Secrets Manager, identidades master/aplicación separadas) + contraseña de aplicación `ephemeral`/write-only (nunca en el Terraform state).
- **4C.4 — protección perimetral y observabilidad**: WAFv2 Web ACL (managed rules + rate limiting en `/api/*`) asociado al ALB; 14 alarmas CloudWatch (ALB/ECS/RDS/log-based); dashboard operativo; SNS opcional para notificaciones.
- **4C.5 — S3 lifecycle + backup/DR**: configuración opcional (versioning, lifecycle rules, encryption por defecto, public access block) adjunta por nombre al bucket externo de artifacts, sin adoptarlo como recurso Terraform; documentación completa de backup/DR de RDS (PITR, snapshots, RPO/RTO, matriz de incidentes, procedimientos de restore) — ver `docs/aws/BACKUP_DR_FOUNDATION.md`.
- **4C.6 — load/stress testing + dimensionamiento**: perfil RECOMMENDED aplicado a `terraform.tfvars.example` (backend 1024 CPU/2048 MiB, frontend 256 CPU/512 MiB, `desired_count`/`min`/`max` 2/2/4 ambos) con evidencia de `k6` — ver `docs/performance/PERFORMANCE_BASELINE.md`.
- **4C.7 — runbook + validación integral**: auditoría completa de networking/IAM/secrets/storage/sizing/observabilidad, runbook operativo y matriz de preparación — ver `docs/aws/PRODUCTION_RUNBOOK.md` y `docs/aws/PRODUCTION_READINESS.md` (estado actual: **NO-GO**, blockers reales listados ahí).

**No se ha creado ningún recurso real en AWS** — nada de esto se ha aplicado todavía.

## Estructura

```
infra/terraform/
  bootstrap/          Remote state bucket, ECR backend/frontend, IAM minimo (Fase 4D.1) — stack independiente, state local
  modules/
    network/           VPC, subredes, NAT, routing, VPC endpoint S3 (4C.1)
    security_groups/   Security groups ALB / ECS tasks / RDS Proxy / RDS (4C.1)
    alb/                Application Load Balancer, target groups, listeners (4C.2)
    ecs/                Cluster, IAM, Task Definitions, Services, autoscaling (4C.2)
    database/           RDS PostgreSQL, RDS Proxy, IAM del proxy (4C.3)
    waf/                WAFv2 Web ACL, managed rules, rate limiting, asociacion al ALB (4C.4)
    observability/      Alarmas CloudWatch, dashboard, SNS (4C.4)
    s3_lifecycle/       Versioning/lifecycle/encryption/public-access-block sobre el bucket externo de artifacts (4C.5)
  environments/
    prod/               Único entorno hoy; compone los módulos de arriba
```

## Validación local (sin credenciales de AWS)

```bash
cd infra/terraform/environments/prod
terraform init -backend=false
terraform validate
terraform fmt -check -recursive ../../..
```

`terraform init -backend=false` sigue funcionando en `environments/prod` aunque `versions.tf` ya declara `backend "s3" {}` (configuración parcial, Fase 4D.1) — `-backend=false` ignora ese bloque por completo y no contacta AWS. Ver `docs/aws/AWS_BOOTSTRAP.md` para el detalle del backend remoto y la sección "Terraform state" en `docs/aws/TERRAFORM_FOUNDATION.md` para el contexto original.

`infra/terraform/bootstrap/` se valida igual, desde su propio directorio:

```bash
cd infra/terraform/bootstrap
terraform init -backend=false
terraform validate
```

Este stack no declara ningún bloque `backend` (state local, permanente por diseño — ver `docs/aws/AWS_BOOTSTRAP.md`, "State del propio bootstrap"), por lo que `terraform init` a secas también funciona sin credenciales AWS.

## Uso previsto (cuando corresponda desplegar de verdad)

```bash
cd infra/terraform/environments/prod
cp terraform.tfvars.example terraform.tfvars   # editar si hace falta
terraform init                                  # con backend remoto ya configurado
terraform plan
terraform apply
```

**Nada de esto se ha ejecutado en Fase 4C.1.** `terraform plan`/`apply` requieren credenciales de AWS y quedan fuera del alcance de esta subfase.

## Convenciones

- Un único proveedor `aws`, versión fijada (`>= 5.27.0, < 6.0.0` — necesaria por los recursos `aws_vpc_security_group_*_rule` usados en `security_groups`).
- Ningún secreto, ARN, ID de cuenta ni identificador de recurso real en el código — todo lo variable viene de `variables.tf`/`terraform.tfvars`.
- Tags comunes (`Project`, `Environment`, `ManagedBy`) via `default_tags` del provider en `environments/prod/providers.tf`; cada recurso añade además su propio tag `Name`.
- No se crean módulos vacíos "por si acaso" — cada módulo existente resuelve una necesidad concreta de esta subfase.
