# Dashboard operativo Terraform-managed (item 31). Solo metricas reales ya
# usadas por las alarmas de main.tf — ningun widget basado en una metrica
# no verificada. Sin RDS Proxy (ver "Limitaciones" en
# docs/aws/WAF_CLOUDWATCH_FOUNDATION.md) — no se pudo verificar el
# namespace/nombres de metrica exactos en este entorno sin acceso a
# documentacion/consola de AWS.

locals {
  dashboard_widgets = [
    # --- ALB --------------------------------------------------------------
    {
      type   = "metric"
      x      = 0
      y      = 0
      width  = 12
      height = 6
      properties = {
        title  = "ALB — Errores 5xx"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Sum"
        period = 60
        metrics = [
          ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", var.alb_arn_suffix],
          ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.backend_target_group_arn_suffix],
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 0
      width  = 12
      height = 6
      properties = {
        title  = "ALB — Latencia del backend (TargetResponseTime)"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Average"
        period = 60
        metrics = [
          ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.backend_target_group_arn_suffix],
        ]
      }
    },
    {
      type   = "metric"
      x      = 0
      y      = 6
      width  = 12
      height = 6
      properties = {
        title  = "ALB — Targets no saludables"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Maximum"
        period = 60
        metrics = [
          ["AWS/ApplicationELB", "UnHealthyHostCount", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.backend_target_group_arn_suffix, { label = "backend" }],
          ["AWS/ApplicationELB", "UnHealthyHostCount", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.frontend_target_group_arn_suffix, { label = "frontend" }],
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 6
      width  = 12
      height = 6
      properties = {
        title  = "ALB — Targets saludables"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Minimum"
        period = 60
        metrics = [
          ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.backend_target_group_arn_suffix, { label = "backend" }],
          ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.frontend_target_group_arn_suffix, { label = "frontend" }],
        ]
      }
    },
    # --- ECS backend --------------------------------------------------------
    {
      type   = "metric"
      x      = 0
      y      = 12
      width  = 12
      height = 6
      properties = {
        title  = "ECS backend — CPU / Memoria (%)"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Average"
        period = 300
        metrics = [
          ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_backend_service_name, { label = "CPU" }],
          ["AWS/ECS", "MemoryUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_backend_service_name, { label = "Memoria" }],
        ]
      }
    },
    # --- ECS frontend --------------------------------------------------------
    {
      type   = "metric"
      x      = 12
      y      = 12
      width  = 12
      height = 6
      properties = {
        title  = "ECS frontend — CPU / Memoria (%)"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Average"
        period = 300
        metrics = [
          ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_frontend_service_name, { label = "CPU" }],
          ["AWS/ECS", "MemoryUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_frontend_service_name, { label = "Memoria" }],
        ]
      }
    },
    # --- RDS --------------------------------------------------------------
    {
      type   = "metric"
      x      = 0
      y      = 18
      width  = 12
      height = 6
      properties = {
        title  = "RDS — CPU / Conexiones"
        region = var.aws_region
        view   = "timeSeries"
        period = 300
        metrics = [
          ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", var.db_instance_id, { stat = "Average", label = "CPU %" }],
          ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.db_instance_id, { stat = "Average", label = "Conexiones", yAxis = "right" }],
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 18
      width  = 12
      height = 6
      properties = {
        title  = "RDS — Almacenamiento libre / Memoria libre"
        region = var.aws_region
        view   = "timeSeries"
        period = 300
        metrics = [
          ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", var.db_instance_id, { stat = "Average", label = "Storage libre (bytes)" }],
          ["AWS/RDS", "FreeableMemory", "DBInstanceIdentifier", var.db_instance_id, { stat = "Average", label = "Memoria libre (bytes)", yAxis = "right" }],
        ]
      }
    },
    # --- Aplicacion (logs) --------------------------------------------------
    {
      type   = "metric"
      x      = 0
      y      = 24
      width  = 12
      height = 6
      properties = {
        title  = "Backend — Lineas de log con level=ERROR"
        region = var.aws_region
        view   = "timeSeries"
        stat   = "Sum"
        period = 300
        metrics = [
          ["TerritorioElectoral/Backend", "ErrorLogCount"],
        ]
      }
    },
  ]
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.name_prefix}-operations"

  dashboard_body = jsonencode({
    widgets = local.dashboard_widgets
  })
}
