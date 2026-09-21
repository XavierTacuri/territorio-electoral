variable "name_prefix" {
  description = "Prefijo para nombrar todos los recursos WAF (ej. territorio-electoral-prod)."
  type        = string
}

variable "alb_arn" {
  description = "ARN del ALB (modulo alb, Fase 4C.2) al que se asocia el Web ACL."
  type        = string
}

variable "backend_path_prefix" {
  description = "Prefijo de ruta de la API, usado para acotar la regla de rate limiting solo a /api/* (no a assets estaticos del frontend) — debe coincidir con el routing real del ALB (modulo alb: path_pattern [\"/api/*\"])."
  type        = string
  default     = "/api/"
}

# ============================================================================
# AWS Managed Rule Groups
# ============================================================================
# Conjunto deliberadamente acotado (item 7/8 de la revision de 4C.4): cubre
# proteccion generica OWASP (Common), patrones de ataque conocidos (Known
# Bad Inputs) e IPs con reputacion maliciosa confirmada (IP Reputation) — no
# se agregan todos los managed rule groups disponibles de AWS para evitar
# coste y falsos positivos innecesarios. Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md.

variable "enable_common_rule_set" {
  description = "AWSManagedRulesCommonRuleSet: proteccion generica de aplicacion web (OWASP-like). Riesgo de falso positivo documentado: campos de texto libre de la aplicacion (necesidades ciudadanas, incidentes) podrian coincidir con patrones genericos de XSS/SQLi — override_action=none (bloquea), monitorear metricas por regla tras cualquier despliegue real."
  type        = bool
  default     = true
}

variable "enable_known_bad_inputs_rule_set" {
  description = "AWSManagedRulesKnownBadInputsRuleSet: bloquea patrones de exploits conocidos (ej. Log4Shell). Riesgo de falso positivo bajo — firma especificas de ataques conocidos, no patrones genericos."
  type        = bool
  default     = true
}

variable "enable_ip_reputation_list" {
  description = "AWSManagedRulesAmazonIpReputationList: bloquea IPs con reputacion maliciosa confirmada por inteligencia de amenazas de AWS. Riesgo de falso positivo muy bajo."
  type        = bool
  default     = true
}

variable "waf_managed_rules_count_mode" {
  description = "true (por defecto): los 3 managed rule groups corren en modo Count (override_action{count{}} — evaluan y generan metrica/log, pero NUNCA bloquean trafico real) — el rollout seguro que AWS recomienda antes de confiar en un managed rule group nuevo contra trafico de produccion. false: override_action{none{}} — cada managed rule group aplica sus acciones internas reales (tipicamente Block). Cambiar a false solo despues de observar metricas/logs reales y confirmar ausencia de falsos positivos inaceptables. Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md, \"Rollout de Managed Rule Groups\"."
  type        = bool
  default     = true
}

# ============================================================================
# Rate limiting
# ============================================================================

variable "rate_limit_requests" {
  description = "Limite de solicitudes por IP origen en una ventana de 5 minutos (rate_based_statement, evaluation_window_sec=300), acotado a backend_path_prefix. Valor inicial deliberadamente generoso — una regla de rate limiting por IP agrupa a usuarios detras de la misma IP publica/NAT; un umbral demasiado bajo bloquearia trafico legitimo. Ajuste definitivo: Fase 4C.6, con datos reales de load/stress testing."
  type        = number
  default     = 2000

  validation {
    condition     = var.rate_limit_requests >= 100
    error_message = "rate_limit_requests debe ser al menos 100 (el minimo que AWS WAF acepta para rate_based_statement)."
  }
}

# ============================================================================
# Sampled requests
# ============================================================================
# DISTINTO de cloudwatch_metrics_enabled (contadores agregados, sin
# contenido de solicitud — siempre true, nunca configurable) y de
# waf_logging_enabled (logging de requests con redacted_fields, arriba).
# Los sampled requests son una muestra de SOLICITUDES REALES (hasta ~5000,
# ~3 horas) consultable via la consola/API de WAF (GetSampledRequests) — y
# `redacted_fields` de aws_wafv2_web_acl_logging_configuration NO protege
# esta muestra: son mecanismos completamente separados de AWS WAF. AWS
# ofrece un mecanismo dedicado para proteger sampled requests
# (aws_wafv2_web_acl.data_protection_config), no implementado en esta fase
# por no ser necesario si sampled requests permanece deshabilitado por
# defecto — ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md.
variable "waf_sampled_requests_enabled" {
  description = "false (por defecto, recomendado para produccion inicial): sin muestreo de solicitudes reales — evita capturar contenido de solicitud (headers, query strings) sin una capa de proteccion de datos dedicada. true: habilita el muestreo (util para depurar falsos positivos durante un rollout en Count mode) — si se habilita, considerar tambien aws_wafv2_web_acl.data_protection_config (no implementado aqui) antes de dejarlo activo de forma permanente."
  type        = bool
  default     = false
}

# ============================================================================
# Logging
# ============================================================================

variable "waf_logging_enabled" {
  description = "false (por defecto): sin logging de solicitudes WAF (las metricas CloudWatch de cada regla quedan habilitadas de todas formas, ver visibility_config — esto es logging de REQUESTS individuales, no metricas agregadas). true: crea un log group dedicado (\"aws-waf-logs-<prefijo>\", nombre exigido por AWS para el destino CloudWatch Logs) y habilita aws_wafv2_web_acl_logging_configuration. Sin arquitectura de Kinesis Firehose/S3 — el destino CloudWatch Logs es el mas simple soportado nativamente, suficiente para esta fase."
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "Retencion del log group de WAF, si waf_logging_enabled=true."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
