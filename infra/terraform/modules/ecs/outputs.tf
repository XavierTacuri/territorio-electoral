output "cluster_arn" {
  description = "ARN del ECS Cluster."
  value       = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  description = "Nombre del ECS Cluster."
  value       = aws_ecs_cluster.this.name
}

output "backend_service_name" {
  value = aws_ecs_service.backend.name
}

output "frontend_service_name" {
  value = aws_ecs_service.frontend.name
}

output "backend_task_definition_arn" {
  value = aws_ecs_task_definition.backend.arn
}

output "frontend_task_definition_arn" {
  value = aws_ecs_task_definition.frontend.arn
}

output "backend_migrate_task_definition_arn" {
  description = "ARN de la task definition de release (Alembic). Se invoca manualmente con `aws ecs run-task`, nunca desde un aws_ecs_service."
  value       = aws_ecs_task_definition.backend_migrate.arn
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "frontend_tasks_security_group_id" {
  description = "Security group propio de las tasks del frontend (creado en este modulo, distinto del ecs_tasks_security_group_id del backend de Fase 4C.1)."
  value       = aws_security_group.frontend_tasks.id
}

output "backend_log_group_name" {
  value = aws_cloudwatch_log_group.backend.name
}

output "frontend_log_group_name" {
  value = aws_cloudwatch_log_group.frontend.name
}
