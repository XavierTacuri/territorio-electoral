# Terraform — Territorio Electoral

Infraestructura como código para el despliegue AWS de Territorio Electoral (Fase 4C). Ver la fundación de red/security groups en [`docs/aws/TERRAFORM_FOUNDATION.md`](../../docs/aws/TERRAFORM_FOUNDATION.md), la capa ECS/Fargate + ALB en [`docs/aws/ECS_ALB_FOUNDATION.md`](../../docs/aws/ECS_ALB_FOUNDATION.md), y el diseño objetivo completo en [`docs/aws/PRODUCTION_ARCHITECTURE.md`](../../docs/aws/PRODUCTION_ARCHITECTURE.md).

## Estado actual (Fase 4C.1 + 4C.2)

- **4C.1 — fundación**: red (VPC, subredes públicas/aplicación/base de datos en 2+ AZ, NAT, endpoint S3) y security groups (límites ALB → ECS → RDS Proxy → RDS).
- **4C.2 — ejecución**: ECS Cluster (Fargate), Task Definitions (backend, frontend, y una task de release `backend-migrate` para Alembic, no adjunta a ningún Service), ECS Services con autoscaling base, ALB con routing por path (`/api/*` → backend, resto → frontend), IAM de mínimo privilegio (Execution Role vs. Task Role).

**No se ha creado ningún recurso real en AWS** — nada de esto se ha aplicado todavía. RDS, RDS Proxy, WAF y CloudWatch avanzado llegan en subfases posteriores.

## Estructura

```
infra/terraform/
  modules/
    network/           VPC, subredes, NAT, routing, VPC endpoint S3 (4C.1)
    security_groups/   Security groups ALB / ECS tasks / RDS Proxy / RDS (4C.1)
    alb/                Application Load Balancer, target groups, listeners (4C.2)
    ecs/                Cluster, IAM, Task Definitions, Services, autoscaling (4C.2)
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
