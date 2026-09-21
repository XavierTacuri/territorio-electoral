# Unico punto de inspeccion de trafico publico antes del ALB (Fase 4C.2).
# scope = "REGIONAL" (no CLOUDFRONT): protege un ALB, no una distribucion
# CloudFront — no existe CloudFront en esta arquitectura (ver decision
# documentada en docs/aws/ECS_ALB_FOUNDATION.md sobre por que el frontend
# corre en ECS y no en CloudFront+S3).
#
# default_action = allow: la politica normal es permitir todo el trafico;
# las reglas de abajo bloquean unicamente lo que coincide con sus
# condiciones (managed rule groups conocidos, o el limite de tasa por IP).
# Un default deny requeriria modelar explicitamente cada patron de trafico
# valido de la aplicacion — fuera de alcance y de riesgo injustificado para
# esta fase.
#
# CloudWatch metrics (cloudwatch_metrics_enabled) vs. WAF request logging
# (aws_wafv2_web_acl_logging_configuration, abajo) vs. sampled requests
# (sampled_requests_enabled): TRES mecanismos distintos, con implicaciones
# de datos distintas — ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md,
# "Metrics, logging y sampled requests: tres mecanismos distintos".
# cloudwatch_metrics_enabled se mantiene SIEMPRE true (son contadores
# agregados, sin contenido de solicitud — nunca se desactiva).

resource "aws_wafv2_web_acl" "this" {
  name        = "${var.name_prefix}-web-acl"
  description = "Web ACL regional del ALB de Territorio Electoral."
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # Rollout de Managed Rule Groups (item 4-6 de la revision): AWS recomienda
  # desplegar un managed rule group nuevo en modo Count antes de bloquear
  # trafico real con el — override_action{count{}} sobre la regla completa
  # pone TODAS las reglas internas del managed rule group en modo Count
  # (nunca bloquean, solo metrica/log), sustituyendo la accion que cada
  # regla interna de AWS trae por defecto (tipicamente Block). Esto es
  # DISTINTO de `rule_action_override` (un mecanismo mas granular que
  # requeriria conocer los nombres internos exactos de cada regla dentro
  # del managed rule group — no se usa aqui porque no se pudo verificar esa
  # lista con evidencia, ver item 6). Proceso recomendado, documentado en
  # docs/aws/WAF_CLOUDWATCH_FOUNDATION.md:
  #   1. Desplegar con waf_managed_rules_count_mode = true (default).
  #   2. Observar metricas por regla + logs (si waf_logging_enabled) durante
  #      trafico real.
  #   3. Identificar falsos positivos concretos (no hipoteticos).
  #   4. Si hacen falta excepciones especificas, agregarlas con evidencia real
  #      (fuera de alcance definir aqui sin esa evidencia).
  #   5. Cambiar a waf_managed_rules_count_mode = false (enforcement real).
  #   6. Seguir monitoreando las metricas tras el cambio.

  dynamic "rule" {
    for_each = var.enable_common_rule_set ? [1] : []
    content {
      name     = "aws-common-rule-set"
      priority = 1

      override_action {
        dynamic "count" {
          for_each = var.waf_managed_rules_count_mode ? [1] : []
          content {}
        }
        dynamic "none" {
          for_each = var.waf_managed_rules_count_mode ? [] : [1]
          content {}
        }
      }

      statement {
        managed_rule_group_statement {
          name        = "AWSManagedRulesCommonRuleSet"
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        sampled_requests_enabled   = var.waf_sampled_requests_enabled
        metric_name                = "${var.name_prefix}-common-rule-set"
      }
    }
  }

  dynamic "rule" {
    for_each = var.enable_known_bad_inputs_rule_set ? [1] : []
    content {
      name     = "aws-known-bad-inputs"
      priority = 2

      override_action {
        dynamic "count" {
          for_each = var.waf_managed_rules_count_mode ? [1] : []
          content {}
        }
        dynamic "none" {
          for_each = var.waf_managed_rules_count_mode ? [] : [1]
          content {}
        }
      }

      statement {
        managed_rule_group_statement {
          name        = "AWSManagedRulesKnownBadInputsRuleSet"
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        sampled_requests_enabled   = var.waf_sampled_requests_enabled
        metric_name                = "${var.name_prefix}-known-bad-inputs"
      }
    }
  }

  dynamic "rule" {
    for_each = var.enable_ip_reputation_list ? [1] : []
    content {
      name     = "aws-ip-reputation-list"
      priority = 3

      override_action {
        dynamic "count" {
          for_each = var.waf_managed_rules_count_mode ? [1] : []
          content {}
        }
        dynamic "none" {
          for_each = var.waf_managed_rules_count_mode ? [] : [1]
          content {}
        }
      }

      statement {
        managed_rule_group_statement {
          name        = "AWSManagedRulesAmazonIpReputationList"
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        sampled_requests_enabled   = var.waf_sampled_requests_enabled
        metric_name                = "${var.name_prefix}-ip-reputation-list"
      }
    }
  }

  # Rate limiting acotado a /api/* (item 10 de la revision de 4C.4): la API
  # es la superficie que realmente golpea backend/DB por solicitud; los
  # assets estaticos del frontend son cacheables por el navegador y su
  # patron de trafico (rafagas de carga de pagina) no deberia competir por
  # el mismo presupuesto de tasa que las llamadas transaccionales de la
  # API. scope_down_statement con STARTS_WITH sobre uri_path replica
  # exactamente el prefijo que ya usa el routing del ALB (modulo alb,
  # path_pattern ["/api/*"]) — nunca inventa una ruta nueva.
  #
  # evaluation_window_sec = 300 explicito (no implicito): el provider AWS
  # 5.100.0 ya resuelto soporta este argumento (confirmado contra el schema
  # real, `terraform providers schema -json`) — se fija explicitamente para
  # que la ventana de evaluacion sea visible en el codigo, no un default
  # implicito del proveedor.
  #
  # BLOCK (no COUNT): limite deliberadamente generoso (2000/5min por IP) y
  # documentado como baseline — ver "Naturaleza aproximada del rate
  # limiting" en docs/aws/WAF_CLOUDWATCH_FOUNDATION.md. El limite no cambia
  # en esta revision (tuning definitivo: Fase 4C.6).
  rule {
    name     = "api-rate-limit"
    priority = 4

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.rate_limit_requests
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300

        scope_down_statement {
          byte_match_statement {
            search_string         = var.backend_path_prefix
            positional_constraint = "STARTS_WITH"

            field_to_match {
              uri_path {}
            }

            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      sampled_requests_enabled   = var.waf_sampled_requests_enabled
      metric_name                = "${var.name_prefix}-api-rate-limit"
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    sampled_requests_enabled   = var.waf_sampled_requests_enabled
    metric_name                = "${var.name_prefix}-web-acl"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-web-acl" })
}

# El ALB es el unico recurso protegido (item 5) — nunca RDS/RDS Proxy, que
# ya son inalcanzables desde Internet por la cadena de security groups de
# Fase 4C.1/4C.3.
resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = var.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}

# ============================================================================
# WAF logging (opcional) — logging de SOLICITUDES individuales, distinto de
# las metricas CloudWatch de arriba (que siempre quedan habilitadas via
# visibility_config) y distinto de los sampled requests (ver variable
# waf_sampled_requests_enabled arriba — redacted_fields de este recurso NO
# protege sampled requests, son mecanismos separados de AWS WAF). Destino
# CloudWatch Logs directo — sin Kinesis Firehose ni S3, la arquitectura
# minima que AWS soporta nativamente para esto.
# ============================================================================

resource "aws_cloudwatch_log_group" "waf" {
  count = var.waf_logging_enabled ? 1 : 0

  # Nombre EXIGIDO por AWS: todo log group usado como destino de WAF
  # logging debe empezar literalmente con "aws-waf-logs-" — no es una
  # convencion propia de este proyecto.
  name              = "aws-waf-logs-${var.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, { Name = "aws-waf-logs-${var.name_prefix}" })
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  count = var.waf_logging_enabled ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]

  # Redaccion de campos con datos de autenticacion reales de la aplicacion
  # (verificado contra el codigo, no inventado):
  #   - Authorization: backend/app/services/auth_service.py — Bearer/JWT
  #     para clientes API. SensitiveDataFilter (backend/app/core/observability.py)
  #     ya redacta esto en los logs de aplicacion; se redacta igual aqui
  #     por el mismo motivo.
  #   - Cookie: backend/app/services/browser_auth_service.py + backend/app/core/config.py
  #     (browser_cookie_secure, browser_access_token_minutes,
  #     browser_refresh_token_days) — sesiones de navegador via cookies
  #     HttpOnly.
  # Sin redaccion de QueryString: se revisó el codigo del backend buscando
  # un mecanismo de token/secreto transportado por query string en
  # solicitudes ENTRANTES y no se encontro ninguno (el unico "access_token"
  # del codigo es un campo de un cuerpo de respuesta JSON, no un query
  # param) — no se redacta especulativamente lo que no esta evidenciado.
  # Sin redaccion de uri_path: no hay necesidad identificada (item de la
  # revision: "no redactes URI path sin necesidad").
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}
