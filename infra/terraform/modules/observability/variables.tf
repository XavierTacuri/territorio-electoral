# ============================================================================
# Identificadores de recursos ya creados (4C.1-4C.3) — nada de esto se crea
# aqui, solo se referencia para las dimensiones de las metricas CloudWatch.
# ============================================================================

variable "name_prefix" {
  description = "Prefijo para nombrar todos los recursos de observabilidad (ej. territorio-electoral-prod)."
  type        = string
}

variable "aws_region" {
  type = string
}

variable "alb_arn_suffix" {
  description = "Sufijo de ARN del ALB (modulo alb) — dimension LoadBalancer de las metricas AWS/ApplicationELB."
  type        = string
}

variable "backend_target_group_arn_suffix" {
  type = string
}

variable "frontend_target_group_arn_suffix" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "ecs_backend_service_name" {
  type = string
}

variable "ecs_frontend_service_name" {
  type = string
}

variable "db_instance_id" {
  description = "Identificador de la instancia RDS (modulo database) — dimension DBInstanceIdentifier de las metricas AWS/RDS."
  type        = string
}

variable "db_allocated_storage_gib" {
  description = "Almacenamiento asignado a RDS en GiB (modulo database, var.db_allocated_storage) — usado para calcular el umbral de la alarma de espacio libre como porcentaje, en vez de un valor absoluto que asuma un tamano de disco fijo."
  type        = number
}

variable "backend_log_group_name" {
  description = "Log group del backend (modulo ecs) — base del metric filter de errores."
  type        = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}

# ============================================================================
# SNS para notificaciones de alarmas (item 33-35)
# ============================================================================

variable "create_alarm_sns_topic" {
  description = "true: crea un aws_sns_topic propio para las alarmas. false (por defecto): no crea ninguno — usar alarm_sns_topic_arn si ya existe uno externo, o dejar las alarmas sin acciones (enable_alarm_actions=false)."
  type        = bool
  default     = false
}

variable "alarm_sns_topic_arn" {
  description = "ARN de un SNS topic EXISTENTE a usar para las alarmas, si create_alarm_sns_topic=false. Vacio por defecto. No puede combinarse con create_alarm_sns_topic=true (ambiguo sobre cual topic usar) — validado abajo. Sin direcciones de correo hardcodeadas: las suscripciones (email, etc.) se administran fuera de este Terraform, manualmente, sobre el topic resultante."
  type        = string
  default     = ""

  validation {
    condition     = !(var.create_alarm_sns_topic && length(var.alarm_sns_topic_arn) > 0)
    error_message = "create_alarm_sns_topic=true y alarm_sns_topic_arn no vacio son mutuamente excluyentes: elige uno de los dos mecanismos."
  }
}

variable "enable_alarm_actions" {
  description = "false (por defecto): las alarmas se crean y quedan visibles en CloudWatch, pero no notifican a ningun SNS topic — apropiado en validacion/desarrollo Terraform, donde no queremos notificaciones reales. true: cada alarma incluye el ARN resuelto (creado o externo) en alarm_actions."
  type        = bool
  default     = false
}

variable "enable_ok_actions" {
  description = "Si ademas de alarm_actions, cada alarma tambien notifica cuando vuelve a estado OK. No obligatorio — por defecto false."
  type        = bool
  default     = false
}

# ============================================================================
# ALB
# ============================================================================

variable "alb_5xx_threshold" {
  description = "Umbral de HTTPCode_ELB_5XX_Count (suma en el periodo) para disparar la alarma. Baseline inicial — Fase 4C.6 lo ajustara con trafico real."
  type        = number
  default     = 10
}

variable "alb_target_5xx_threshold" {
  description = "Umbral de HTTPCode_Target_5XX_Count del target group del backend. Baseline inicial."
  type        = number
  default     = 10
}

variable "alb_response_time_threshold_seconds" {
  description = "Umbral de TargetResponseTime (p50/Average) del target group del backend, en segundos. Baseline inicial, no un SLO definitivo."
  type        = number
  default     = 2
}

variable "alb_evaluation_periods" {
  description = "Numero de periodos consecutivos de 60s antes de disparar las alarmas de ALB (5xx, response time)."
  type        = number
  default     = 5
}

variable "alb_unhealthy_host_evaluation_periods" {
  description = "Numero de periodos consecutivos de 60s con UnHealthyHostCount > 0 antes de alarmar — mayor a 1 deliberadamente, para no generar ruido por un target temporalmente unhealthy durante un rolling deployment normal."
  type        = number
  default     = 5
}

# ============================================================================
# ECS
# ============================================================================

variable "ecs_cpu_threshold_percent" {
  type    = number
  default = 85
}

variable "ecs_memory_threshold_percent" {
  type    = number
  default = 85
}

variable "ecs_evaluation_periods" {
  description = "Numero de periodos consecutivos de 300s (5 min) antes de alarmar CPU/memoria de ECS — sostenido, no un pico puntual, y superior a la duracion tipica de un rolling deployment."
  type        = number
  default     = 3
}

# ============================================================================
# RDS
# ============================================================================

variable "rds_cpu_threshold_percent" {
  type    = number
  default = 80
}

variable "rds_free_storage_threshold_percent" {
  description = "Porcentaje MINIMO de almacenamiento libre antes de alarmar (se calcula como db_allocated_storage_gib * este_porcentaje / 100, convertido a bytes) — no un valor absoluto, para no asumir que el tamano de disco actual es definitivo."
  type        = number
  default     = 20
}

variable "rds_freeable_memory_threshold_mb" {
  description = "Umbral MINIMO de FreeableMemory antes de alarmar, en MiB. Baseline generico — depende de instance_class, ajustar en Fase 4C.6."
  type        = number
  default     = 256
}

variable "rds_database_connections_threshold" {
  description = "Umbral de DatabaseConnections. El trafico normal del backend pasa por RDS Proxy (pooling), no conecta directo a RDS — este umbral cubre conexiones RECIBIDAS POR RDS (desde RDS Proxy, y las tasks de bootstrap/migracion que si conectan directo). Valor generico, sin relacion verificada con el max_connections real de la instance_class elegida — ajustar en Fase 4C.6. Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md."
  type        = number
  default     = 80
}

variable "rds_evaluation_periods" {
  type    = number
  default = 3
}

# ============================================================================
# Log-based metric (item 30)
# ============================================================================

variable "backend_error_log_threshold" {
  description = "Numero de lineas de log con level=ERROR en el periodo (5 min) antes de alarmar."
  type        = number
  default     = 10
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
