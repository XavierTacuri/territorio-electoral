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
  description = "ARN de la task definition de release (Alembic). Se invoca manualmente con `aws ecs run-task`, nunca desde un aws_ecs_service. Usa la identidad MAESTRA."
  value       = aws_ecs_task_definition.backend_migrate.arn
}

output "backend_bootstrap_task_definition_arn" {
  description = "ARN de la task definition de bootstrap administrativo (crea/actualiza el rol de aplicacion). Se invoca manualmente con `aws ecs run-task`, nunca desde un aws_ecs_service. Usa la identidad MAESTRA."
  value       = aws_ecs_task_definition.backend_bootstrap.arn
}

output "backend_execution_role_arn" {
  description = "Execution Role de la familia backend (service, migrate, bootstrap) — arranca esos contenedores y lee sus secretos de DB. El frontend usa un Execution Role propio, sin acceso a estos secretos (ver frontend_execution_role_arn)."
  value       = aws_iam_role.execution.arn
}

output "backend_task_role_arn" {
  description = "Task Role de la familia backend (service, migrate, bootstrap) — unico rol con permisos S3 de aplicacion. El frontend (nginx estatico) no tiene Task Role: su Task Definition omite task_role_arn por completo."
  value       = aws_iam_role.backend_task.arn
}

output "frontend_execution_role_arn" {
  description = "Execution Role propio del frontend — solo arranca el contenedor (pull de imagen, logs); sin acceso a secretsmanager:GetSecretValue sobre los secretos de DB/aplicacion."
  value       = aws_iam_role.frontend_execution.arn
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
