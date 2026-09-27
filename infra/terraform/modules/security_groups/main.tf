# Cadena de confianza de red que estos security groups establecen como
# fundacion para las subfases siguientes de Fase 4C:
#
#   Internet -> [ALB] -> [ECS tasks] -> [RDS Proxy] -> [RDS]
#
# Los cuatro security groups NO declaran ingress/egress en absoluto — el
# ownership de TODAS sus reglas es exclusivo de recursos separados
# (aws_vpc_security_group_ingress_rule / egress_rule, mas abajo). Es la unica
# forma de permitir referencias cruzadas entre security groups (el egress
# del ALB necesita el ID del SG de ECS, y el ingress de ECS necesita el ID
# del SG del ALB) sin crear un ciclo de dependencias en el grafo de
# Terraform: si esas reglas fueran bloques inline dentro de cada
# aws_security_group, dos SGs que se referencian mutuamente formarian un
# ciclo irresoluble en `terraform validate`/`plan`.
#
# Fase 4D.4 (correccion post primer-apply-parcial): estos 4 SGs se crearon
# originalmente con `ingress = [] / egress = []` explicitos -- eso SI
# elimina la regla "permitir todo" que AWS agrega por defecto a un security
# group nuevo, pero crea un conflicto real y documentado (HashiCorp) al
# combinarse con los recursos aws_vpc_security_group_*_rule que administran
# las mismas reglas por separado: en cada `plan` posterior a que esas reglas
# ya existan en AWS, Terraform detecta "drift" entre el `[]` declarado y las
# reglas reales, y planea REVOCARLAS para que coincidan con la lista vacia
# declarada -- confirmado empiricamente en el primer apply real de este
# stack (ver docs/aws/PRODUCTION_RUNBOOK.md). La correccion es no declarar
# ingress/egress en absoluto en estos 4 recursos (nunca reemplazarlos por
# `lifecycle.ignore_changes`, que solo esconderia el drift en vez de
# eliminar su causa): sin el argumento, Terraform deja de intentar
# "reconciliar" el atributo, y las reglas reales quedan exclusivamente en
# manos de los recursos separados de abajo. Seguro para estos 4 porque ya
# existen en AWS con la regla por defecto ya revocada desde su creacion
# original (revocar una vez es permanente; omitir el atributo despues no
# hace que AWS la reintroduzca). Ver `frontend_tasks` en modules/ecs/main.tf
# para el caso distinto de un security group que TODAVIA no existe.

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "ALB publico: recibe trafico de Internet, reenvia unicamente a las tasks ECS de la API."
  vpc_id      = var.vpc_id
  # ingress/egress: NO declarados a proposito -- ownership exclusivo de los
  # aws_vpc_security_group_ingress_rule/egress_rule de mas abajo (alb_https,
  # alb_http_redirect, alb_to_ecs, alb_to_frontend en modules/ecs). Ver nota
  # de cabecera del archivo.

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.name_prefix}-ecs-tasks"
  description = "Tasks ECS/Fargate de la API: solo reciben trafico del ALB; salen hacia RDS Proxy y APIs de AWS (S3, ECR, CloudWatch, Secrets Manager) via HTTPS."
  vpc_id      = var.vpc_id
  # ingress/egress: NO declarados a proposito -- ownership exclusivo de
  # ecs_from_alb, ecs_to_rds_proxy, ecs_https_egress (mas abajo). Ver nota
  # de cabecera del archivo.

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-tasks" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "rds_proxy" {
  name        = "${var.name_prefix}-rds-proxy"
  description = "RDS Proxy: solo recibe trafico de las tasks ECS, solo sale hacia RDS."
  vpc_id      = var.vpc_id
  # ingress/egress: NO declarados a proposito -- ownership exclusivo de
  # rds_proxy_from_ecs, rds_proxy_to_rds (mas abajo). Ver nota de cabecera
  # del archivo.

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-proxy" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds"
  description = "RDS PostgreSQL/PostGIS: solo recibe trafico de RDS Proxy. Nunca accesible directamente desde ECS ni desde Internet."
  vpc_id      = var.vpc_id
  # ingress/egress: NO declarados a proposito -- ownership exclusivo de
  # rds_from_proxy (mas abajo; RDS no necesita ningun egress). Ver nota de
  # cabecera del archivo.

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds" })

  lifecycle {
    create_before_destroy = true
  }
}

# --- ALB: entrada publica (futuro WAF/Internet), salida solo hacia ECS ----

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  for_each = toset(var.alb_ingress_cidr_blocks)

  security_group_id = aws_security_group.alb.id
  description       = "HTTPS publico hacia el ALB."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_ingress_rule" "alb_http_redirect" {
  for_each = toset(var.alb_ingress_cidr_blocks)

  security_group_id = aws_security_group.alb.id
  description       = "HTTP publico hacia el ALB, unicamente para redirigir a HTTPS."
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "alb_to_ecs" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Reenvio del ALB hacia las tasks ECS de la API."
  ip_protocol                  = "tcp"
  from_port                    = var.backend_container_port
  to_port                      = var.backend_container_port
  referenced_security_group_id = aws_security_group.ecs_tasks.id
}

# --- ECS tasks: entrada solo del ALB, salida a RDS Proxy y APIs de AWS ----

resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  security_group_id            = aws_security_group.ecs_tasks.id
  description                  = "Trafico de la API unicamente desde el ALB."
  ip_protocol                  = "tcp"
  from_port                    = var.backend_container_port
  to_port                      = var.backend_container_port
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_rds_proxy" {
  security_group_id            = aws_security_group.ecs_tasks.id
  description                  = "Conexiones de base de datos unicamente hacia RDS Proxy."
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.rds_proxy.id
}

resource "aws_vpc_security_group_egress_rule" "ecs_https_egress" {
  security_group_id = aws_security_group.ecs_tasks.id
  description       = "HTTPS saliente hacia APIs de AWS (S3 via VPC endpoint, ECR, CloudWatch, Secrets Manager, STS) y hosts publicos que la aplicacion consulta explicitamente (PUBLIC_FETCH_*, ver backend/app/core/config.py). Candidato a restringirse a prefix lists especificas de AWS en una subfase posterior - ver docs/aws/TERRAFORM_FOUNDATION.md, riesgos."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# --- RDS Proxy: entrada solo de ECS, salida solo a RDS ---------------------

resource "aws_vpc_security_group_ingress_rule" "rds_proxy_from_ecs" {
  security_group_id            = aws_security_group.rds_proxy.id
  description                  = "Conexiones de base de datos unicamente desde las tasks ECS."
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.ecs_tasks.id
}

resource "aws_vpc_security_group_egress_rule" "rds_proxy_to_rds" {
  security_group_id            = aws_security_group.rds_proxy.id
  description                  = "Conexiones de base de datos unicamente hacia RDS."
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.rds.id
}

# --- RDS: entrada solo de RDS Proxy, sin salida -----------------------------

resource "aws_vpc_security_group_ingress_rule" "rds_from_proxy" {
  security_group_id            = aws_security_group.rds.id
  description                  = "Conexiones de base de datos unicamente desde RDS Proxy. Nunca 0.0.0.0/0 - la base de datos jamas queda publicamente accesible."
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.rds_proxy.id
}

# El security group por defecto de la VPC (creado automaticamente por AWS
# junto con la VPC) se deja explicitamente sin reglas: cualquier recurso que
# en el futuro se cree sin especificar un security group propio no debe
# heredar ningun acceso de red por omision.
resource "aws_default_security_group" "this" {
  vpc_id  = var.vpc_id
  ingress = []
  egress  = []

  tags = merge(var.tags, { Name = "${var.name_prefix}-default-locked" })
}
