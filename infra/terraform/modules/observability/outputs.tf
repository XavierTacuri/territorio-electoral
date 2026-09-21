output "dashboard_name" {
  value = aws_cloudwatch_dashboard.this.dashboard_name
}

output "dashboard_arn" {
  value = aws_cloudwatch_dashboard.this.dashboard_arn
}

output "alarm_sns_topic_arn" {
  description = "ARN del SNS topic resuelto (creado o externo), o cadena vacia si ninguno esta configurado."
  value       = local.alarm_topic_arn
}

output "backend_error_metric_filter_name" {
  value = aws_cloudwatch_log_metric_filter.backend_errors.name
}

output "alarm_names" {
  description = "Nombres de todas las alarmas CloudWatch creadas."
  value = [
    aws_cloudwatch_metric_alarm.backend_error_log_count.alarm_name,
    aws_cloudwatch_metric_alarm.alb_5xx.alarm_name,
    aws_cloudwatch_metric_alarm.alb_target_5xx_backend.alarm_name,
    aws_cloudwatch_metric_alarm.alb_response_time_backend.alarm_name,
    aws_cloudwatch_metric_alarm.alb_unhealthy_hosts_backend.alarm_name,
    aws_cloudwatch_metric_alarm.alb_unhealthy_hosts_frontend.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_backend_cpu.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_backend_memory.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_frontend_cpu.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_frontend_memory.alarm_name,
    aws_cloudwatch_metric_alarm.rds_cpu.alarm_name,
    aws_cloudwatch_metric_alarm.rds_free_storage.alarm_name,
    aws_cloudwatch_metric_alarm.rds_freeable_memory.alarm_name,
    aws_cloudwatch_metric_alarm.rds_database_connections.alarm_name,
  ]
}
