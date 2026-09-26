# Unico punto publico hacia los servicios ECS (backend y frontend). El
# routing por path replica exactamente lo que frontend/nginx.conf ya hace
# hoy en docker-compose.prod.yml (`location /api/` -> proxy_pass hacia la
# API, todo lo demas -> SPA): `/api/*` se reenvia al target group del
# backend, cualquier otra ruta al del frontend. Ver docs/aws/ECS_ALB_FOUNDATION.md
# para por que el ALB, y no nginx, hace ahora ese split.

locals {
  # aws_lb_target_group.name tiene un limite de AWS mucho mas estricto (32
  # caracteres, solo alfanumerico/guiones, no puede empezar/terminar en
  # guion) que el resto de recursos de este stack (ALB/ECS/RDS/S3 toleran
  # name_prefix completo sin truncar) -- "${name_prefix}-backend"/"-frontend"
  # ya lo supera con el name_prefix actual (25 + 8/9 = 33/34 caracteres).
  # Se trunca name_prefix a 20 caracteres y se le agrega un hash corto
  # DETERMINISTA (md5 solo como identificador de naming, nunca con proposito
  # criptografico) derivado unicamente de var.name_prefix -- estable entre
  # plans, sin account ID, sin timestamps, sin nada random del provider.
  # Nunca se usa el argumento "name_prefix" de aws_lb_target_group: genera
  # un sufijo aleatorio distinto en cada apply, rompiendo la reproducibilidad
  # que el resto de este stack ya tiene con nombres fijos.
  target_group_name_hash     = substr(md5(var.name_prefix), 0, 6)
  backend_target_group_name  = "${substr(var.name_prefix, 0, 20)}-be-${local.target_group_name_hash}"
  frontend_target_group_name = "${substr(var.name_prefix, 0, 20)}-fe-${local.target_group_name_hash}"
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  # Deshabilitados por defecto (access_logs_bucket vacio): requieren un
  # bucket S3 dedicado con la bucket policy que exige el servicio de ALB
  # (principal de la cuenta de AWS que opera ELB en la region, distinto por
  # region) — nunca el bucket de artifacts de usuarios (evidencia/actas/
  # informes). Crear ese bucket dedicado pertenece a la subfase de
  # Lifecycle S3, fuera de alcance de 4C.4 — ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md.
  dynamic "access_logs" {
    for_each = var.access_logs_bucket == "" ? [] : [1]
    content {
      bucket  = var.access_logs_bucket
      prefix  = var.access_logs_prefix
      enabled = true
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

resource "aws_lb_target_group" "backend" {
  name        = local.backend_target_group_name
  port        = var.backend_container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  lifecycle {
    precondition {
      condition     = length(local.backend_target_group_name) <= 32
      error_message = "backend_target_group_name ('${local.backend_target_group_name}', ${length(local.backend_target_group_name)} caracteres) excede el limite de 32 caracteres de AWS para aws_lb_target_group.name — revisar local.backend_target_group_name en modules/alb/main.tf."
    }
  }

  health_check {
    # /api/v1/health (liveness, nunca toca la base de datos) — deliberadamente
    # NO /api/v1/ready: ese endpoint si consulta la base de datos, y usarlo
    # como health check del target group haria que el ALB deje de enviar
    # trafico (o que ECS reemplace la task) ante una caida transitoria de la
    # base de datos — exactamente lo que el split health/ready de Fase 4B
    # evita a nivel de contenedor. Ver docs/aws/ECS_ALB_FOUNDATION.md.
    path                = "/api/v1/health"
    protocol            = "HTTP"
    matcher             = "200"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
  }

  deregistration_delay = 30

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend" })
}

resource "aws_lb_target_group" "frontend" {
  name        = local.frontend_target_group_name
  port        = var.frontend_container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  lifecycle {
    precondition {
      condition     = length(local.frontend_target_group_name) <= 32
      error_message = "frontend_target_group_name ('${local.frontend_target_group_name}', ${length(local.frontend_target_group_name)} caracteres) excede el limite de 32 caracteres de AWS para aws_lb_target_group.name — revisar local.frontend_target_group_name en modules/alb/main.tf."
    }
  }

  health_check {
    # /health: el mismo endpoint que ya usa el HEALTHCHECK del propio
    # frontend/Dockerfile.
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
  }

  deregistration_delay = 30

  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend" })
}

# --- Listener HTTP :80 -------------------------------------------------------
# Sin certificate_arn (por defecto): sirve HTTP directamente — base tecnica
# configurable, sin dominio ni certificado inventados (item 12). Con
# certificate_arn: redirige todo a HTTPS.

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.frontend.arn
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [] : [1]
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-http" })
}

resource "aws_lb_listener_rule" "http_api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# --- Listener HTTPS :443 (opcional, requiere certificate_arn) --------------

resource "aws_lb_listener" "https" {
  count = var.certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-https" })
}

resource "aws_lb_listener_rule" "https_api" {
  count = var.certificate_arn == "" ? 0 : 1

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}
