output "alb_security_group_id" {
  description = "Security group para el futuro ALB."
  value       = aws_security_group.alb.id
}

output "ecs_tasks_security_group_id" {
  description = "Security group para las futuras tasks ECS/Fargate de la API."
  value       = aws_security_group.ecs_tasks.id
}

output "rds_proxy_security_group_id" {
  description = "Security group para el futuro RDS Proxy."
  value       = aws_security_group.rds_proxy.id
}

output "rds_security_group_id" {
  description = "Security group para el futuro RDS."
  value       = aws_security_group.rds.id
}
