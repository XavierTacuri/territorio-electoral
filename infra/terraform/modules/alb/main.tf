# Unico punto publico hacia los servicios ECS (backend y frontend). El
# routing por path replica exactamente lo que frontend/nginx.conf ya hace
# hoy en docker-compose.prod.yml (`location /api/` -> proxy_pass hacia la
# API, todo lo demas -> SPA): `/api/*` se reenvia al target group del
# backend, cualquier otra ruta al del frontend. Ver docs/aws/ECS_ALB_FOUNDATION.md
# para por que el ALB, y no nginx, hace ahora ese split.

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
  name        = "${var.name_prefix}-backend"
  port        = var.backend_container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

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
  name        = "${var.name_prefix}-frontend"
  port        = var.frontend_container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

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
