# Terraform — Territorio Electoral

Infraestructura como código para el despliegue AWS de Territorio Electoral (Fase 4C). Ver la fundación de red/security groups en [`docs/aws/TERRAFORM_FOUNDATION.md`](../../docs/aws/TERRAFORM_FOUNDATION.md), la capa ECS/Fargate + ALB en [`docs/aws/ECS_ALB_FOUNDATION.md`](../../docs/aws/ECS_ALB_FOUNDATION.md), la capa de datos RDS + RDS Proxy en [`docs/aws/RDS_PROXY_FOUNDATION.md`](../../docs/aws/RDS_PROXY_FOUNDATION.md), WAF + CloudWatch/observabilidad en [`docs/aws/WAF_CLOUDWATCH_FOUNDATION.md`](../../docs/aws/WAF_CLOUDWATCH_FOUNDATION.md), y el diseño objetivo completo en [`docs/aws/PRODUCTION_ARCHITECTURE.md`](../../docs/aws/PRODUCTION_ARCHITECTURE.md).

## Estado actual (Fase 4C.1 + 4C.2 + 4C.3 + 4C.4)

- **4C.1 — fundación**: red (VPC, subredes públicas/aplicación/base de datos en 2+ AZ, NAT, endpoint S3) y security groups (límites ALB → ECS → RDS Proxy → RDS).
- **4C.2 — ejecución**: ECS Cluster (Fargate), Task Definitions (backend, frontend, y una task de release `backend-migrate` para Alembic, no adjunta a ningún Service), ECS Services con autoscaling base, ALB con routing por path (`/api/*` → backend, resto → frontend), IAM de mínimo privilegio (Execution Role vs. Task Role).
- **4C.3 — datos**: RDS PostgreSQL 16 (cifrado, privado, backups, Multi-AZ configurable) + RDS Proxy (TLS, autenticado vía Secrets Manager, identidades master/aplicación separadas) + contraseña de aplicación `ephemeral`/write-only (nunca en el Terraform state).
- **4C.4 — protección perimetral y observabilidad**: WAFv2 Web ACL (managed rules + rate limiting en `/api/*`) asociado al ALB; 14 alarmas CloudWatch (ALB/ECS/RDS/log-based); dashboard operativo; SNS opcional para notificaciones.

**No se ha creado ningún recurso real en AWS** — nada de esto se ha aplicado todavía.

## Estructura

```
infra/terraform/
  modules/
    network/           VPC, subredes, NAT, routing, VPC endpoint S3 (4C.1)
    security_groups/   Security groups ALB / ECS tasks / RDS Proxy / RDS (4C.1)
    alb/                Application Load Balancer, target groups, listeners (4C.2)
    ecs/                Cluster, IAM, Task Definitions, Services, autoscaling (4C.2)
    database/           RDS PostgreSQL, RDS Proxy, IAM del proxy (4C.3)
    waf/                WAFv2 Web ACL, managed rules, rate limiting, asociacion al ALB (4C.4)
    observability/      Alarmas CloudWatch, dashboard, SNS (4C.4)
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

`terraform init -backend=false` funciona porque `versions.tf` no declara ningún bloque `backend` (state local por defecto) — ver la sección "Terraform state" en `docs/aws/TERRAFORM_FOUNDATION.md`.

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
