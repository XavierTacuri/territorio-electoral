# Nota general (item 11-12 de la revision de 4C.4): cada alarma fija
# `datapoints_to_alarm` explicitamente igual a `evaluation_periods` (M de N
# con M=N) — antes quedaba implicito (CloudWatch usa ese mismo default
# cuando se omite), ahora es visible en el codigo que CADA periodo
# consecutivo debe incumplir el umbral, no solo alguno de ellos.

# ============================================================================
# SNS para notificaciones de alarmas (opcional)
# ============================================================================

resource "aws_sns_topic" "alarms" {
  count = var.create_alarm_sns_topic ? 1 : 0

  name = "${var.name_prefix}-alarms"

  tags = merge(var.tags, { Name = "${var.name_prefix}-alarms" })
}

locals {
  # Topic resuelto: el creado aqui, o el externo provisto — nunca ambos (la
  # variable alarm_sns_topic_arn ya valida que sean mutuamente excluyentes).
  alarm_topic_arn = var.create_alarm_sns_topic ? aws_sns_topic.alarms[0].arn : var.alarm_sns_topic_arn

  # Sin ARN resuelto (ni creado ni externo), las acciones quedan vacias
  # incluso si enable_alarm_actions=true — nunca referenciar un ARN vacio.
  alarm_actions_list        = var.enable_alarm_actions && local.alarm_topic_arn != "" ? [local.alarm_topic_arn] : []
  ok_actions_list           = var.enable_ok_actions && local.alarm_topic_arn != "" ? [local.alarm_topic_arn] : []
  rds_free_storage_bytes    = var.db_allocated_storage_gib * 1024 * 1024 * 1024 * var.rds_free_storage_threshold_percent / 100
  rds_freeable_memory_bytes = var.rds_freeable_memory_threshold_mb * 1024 * 1024
}

# ============================================================================
# Log-based metric: errores del backend (item 30) — senal estable porque
# JsonFormatter (backend/app/core/observability.py, Fase 4B) ya emite
# "level" como campo JSON de primer nivel en cada linea; el patron de
# metric filter usa sintaxis JSON nativa de CloudWatch Logs
# ({ $.level = "ERROR" }), no un regex fragil sobre texto libre.
# ============================================================================

resource "aws_cloudwatch_log_metric_filter" "backend_errors" {
  name           = "${var.name_prefix}-backend-error-log-count"
  log_group_name = var.backend_log_group_name
  pattern        = "{ $.level = \"ERROR\" }"

  metric_transformation {
    namespace = "TerritorioElectoral/Backend"
    name      = "ErrorLogCount"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "backend_error_log_count" {
  alarm_name          = "${var.name_prefix}-backend-error-log-count"
  alarm_description   = "Mas de ${var.backend_error_log_threshold} lineas de log con level=ERROR en 5 minutos en el backend."
  namespace           = "TerritorioElectoral/Backend"
  metric_name         = "ErrorLogCount"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.backend_error_log_threshold
  # Sin errores logueados en el periodo = ausencia de datos, no un problema.
  treat_missing_data = "notBreaching"

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-error-log-count" })

  depends_on = [aws_cloudwatch_log_metric_filter.backend_errors]
}

# ============================================================================
# ALB — namespace AWS/ApplicationELB (metricas estandar, ampliamente
# documentadas: HTTPCode_ELB_5XX_Count, HTTPCode_Target_5XX_Count,
# TargetResponseTime, UnHealthyHostCount)
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name_prefix}-alb-5xx"
  alarm_description   = "Tasa anormal de errores 5xx generados por el propio ALB (no por los targets) — baseline inicial, ajustar en Fase 4C.6."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = var.alb_evaluation_periods
  datapoints_to_alarm = var.alb_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_5xx_threshold
  # Sin solicitudes 5xx en el periodo = ausencia de datos, no un problema.
  treat_missing_data = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-5xx" })
}

resource "aws_cloudwatch_metric_alarm" "alb_target_5xx_backend" {
  alarm_name          = "${var.name_prefix}-alb-target-5xx-backend"
  alarm_description   = "Tasa anormal de errores 5xx devueltos por las tasks del backend."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = var.alb_evaluation_periods
  datapoints_to_alarm = var.alb_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_target_5xx_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.backend_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-target-5xx-backend" })
}

resource "aws_cloudwatch_metric_alarm" "alb_response_time_backend" {
  alarm_name          = "${var.name_prefix}-alb-response-time-backend"
  alarm_description   = "Latencia alta sostenida del backend, medida por el ALB — baseline inicial, no un SLO definitivo."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = var.alb_evaluation_periods
  datapoints_to_alarm = var.alb_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_response_time_threshold_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.backend_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-response-time-backend" })
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts_backend" {
  alarm_name          = "${var.name_prefix}-alb-unhealthy-hosts-backend"
  alarm_description   = "Targets del backend marcados unhealthy de forma sostenida (no un blip momentaneo de rolling deployment)."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = var.alb_unhealthy_host_evaluation_periods
  datapoints_to_alarm = var.alb_unhealthy_host_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  # Ausencia de datos en este metric es ambigua (podria ser un problema del
  # propio target group) — se prefiere mantener el estado anterior de la
  # alarma en vez de asumir "sin problema" o "problema" automaticamente.
  treat_missing_data = "missing"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.backend_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-unhealthy-hosts-backend" })
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts_frontend" {
  alarm_name          = "${var.name_prefix}-alb-unhealthy-hosts-frontend"
  alarm_description   = "Targets del frontend marcados unhealthy de forma sostenida."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = var.alb_unhealthy_host_evaluation_periods
  datapoints_to_alarm = var.alb_unhealthy_host_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "missing"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.frontend_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-unhealthy-hosts-frontend" })
}

# ============================================================================
# ECS — namespace AWS/ECS (CPUUtilization, MemoryUtilization; las mismas
# metricas que ya consume Application Auto Scaling desde Fase 4C.2 via
# ECSServiceAverageCPUUtilization — confirmadamente reales, no inventadas).
#
# Sin alarma de "running task count" (item 23): el namespace estandar
# AWS/ECS (sin Container Insights) no expone esa metrica directamente por
# servicio; obtenerla de forma fiable requeriria Container Insights
# (namespace ECS/ContainerInsights, metrica RunningTaskCount) o inventar
# algo no verificado. El sintoma real que "menos tasks saludables de lo
# esperado" produce — menos targets registrados y sanos en el ALB — ya
# queda cubierto por alb_unhealthy_hosts_backend/frontend de arriba, con
# metricas confirmadas. Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md.
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "ecs_backend_cpu" {
  alarm_name          = "${var.name_prefix}-ecs-backend-cpu-high"
  alarm_description   = "CPU alta sostenida del servicio backend."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.ecs_evaluation_periods
  datapoints_to_alarm = var.ecs_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.ecs_cpu_threshold_percent
  # Un servicio temporalmente sin tasks (deploy, escalado a 0 en un entorno
  # no productivo) no debe alarmar solo por ausencia de metricas.
  treat_missing_data = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_backend_service_name
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-backend-cpu-high" })
}

resource "aws_cloudwatch_metric_alarm" "ecs_backend_memory" {
  alarm_name          = "${var.name_prefix}-ecs-backend-memory-high"
  alarm_description   = "Memoria alta sostenida del servicio backend."
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.ecs_evaluation_periods
  datapoints_to_alarm = var.ecs_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.ecs_memory_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_backend_service_name
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-backend-memory-high" })
}

resource "aws_cloudwatch_metric_alarm" "ecs_frontend_cpu" {
  alarm_name          = "${var.name_prefix}-ecs-frontend-cpu-high"
  alarm_description   = "CPU alta sostenida del servicio frontend."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.ecs_evaluation_periods
  datapoints_to_alarm = var.ecs_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.ecs_cpu_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_frontend_service_name
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-frontend-cpu-high" })
}

resource "aws_cloudwatch_metric_alarm" "ecs_frontend_memory" {
  alarm_name          = "${var.name_prefix}-ecs-frontend-memory-high"
  alarm_description   = "Memoria alta sostenida del servicio frontend."
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.ecs_evaluation_periods
  datapoints_to_alarm = var.ecs_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.ecs_memory_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_frontend_service_name
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-frontend-memory-high" })
}

# ============================================================================
# RDS — namespace AWS/RDS (CPUUtilization, FreeStorageSpace,
# DatabaseConnections, FreeableMemory: metricas estandar, ampliamente
# documentadas).
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name_prefix}-rds-cpu-high"
  alarm_description   = "CPU alta sostenida de la instancia RDS."
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.rds_evaluation_periods
  datapoints_to_alarm = var.rds_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.rds_cpu_threshold_percent
  # RDS es un recurso siempre activo (no efimero como una task ECS) — la
  # ausencia sostenida de metricas de una instancia que deberia existir es,
  # en si misma, una senal de alerta (instancia detenida/eliminada, o un
  # problema del propio monitoreo).
  treat_missing_data = "breaching"

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-cpu-high" })
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "${var.name_prefix}-rds-free-storage-low"
  alarm_description   = "Espacio libre de RDS por debajo de ${var.rds_free_storage_threshold_percent}% del almacenamiento asignado (${var.db_allocated_storage_gib} GiB)."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.rds_evaluation_periods
  datapoints_to_alarm = var.rds_evaluation_periods
  comparison_operator = "LessThanThreshold"
  threshold           = local.rds_free_storage_bytes
  treat_missing_data  = "breaching"

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-free-storage-low" })
}

resource "aws_cloudwatch_metric_alarm" "rds_freeable_memory" {
  alarm_name          = "${var.name_prefix}-rds-freeable-memory-low"
  alarm_description   = "Memoria libre de RDS por debajo de ${var.rds_freeable_memory_threshold_mb} MiB — posible presion de memoria."
  namespace           = "AWS/RDS"
  metric_name         = "FreeableMemory"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.rds_evaluation_periods
  datapoints_to_alarm = var.rds_evaluation_periods
  comparison_operator = "LessThanThreshold"
  threshold           = local.rds_freeable_memory_bytes
  treat_missing_data  = "breaching"

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-freeable-memory-low" })
}

resource "aws_cloudwatch_metric_alarm" "rds_database_connections" {
  alarm_name          = "${var.name_prefix}-rds-database-connections-high"
  alarm_description   = "Numero de conexiones a RDS por encima de lo esperado. El trafico normal del backend pasa por RDS Proxy (pooling, Fase 4C.3) — esta metrica cuenta conexiones RECIBIDAS por RDS (desde el proxy, y las tasks de bootstrap/migracion que conectan directo), no conexiones de aplicacion individuales."
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.rds_evaluation_periods
  datapoints_to_alarm = var.rds_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.rds_database_connections_threshold
  # Pocas/ninguna conexion en el periodo no es un problema por si mismo.
  treat_missing_data = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }

  alarm_actions = local.alarm_actions_list
  ok_actions    = local.ok_actions_list

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-database-connections-high" })
}
