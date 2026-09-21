output "vpc_id" {
  description = "ID de la VPC."
  value       = module.network.vpc_id
}

output "availability_zones" {
  description = "Zonas de disponibilidad utilizadas."
  value       = module.network.availability_zones
}

output "public_subnet_ids" {
  description = "Subredes publicas (destino futuro: ALB)."
  value       = module.network.public_subnet_ids
}

output "app_subnet_ids" {
  description = "Subredes privadas de aplicacion (destino futuro: ECS/Fargate)."
  value       = module.network.app_subnet_ids
}

output "db_subnet_ids" {
  description = "Subredes privadas de base de datos (destino futuro: RDS, RDS Proxy)."
  value       = module.network.db_subnet_ids
}

output "nat_gateway_ids" {
  description = "NAT Gateway(s) creados."
  value       = module.network.nat_gateway_ids
}

output "s3_vpc_endpoint_id" {
  description = "VPC Endpoint (Gateway) hacia S3."
  value       = module.network.s3_vpc_endpoint_id
}

output "alb_security_group_id" {
  description = "Security group para el futuro ALB."
  value       = module.security_groups.alb_security_group_id
}

output "ecs_tasks_security_group_id" {
  description = "Security group para las futuras tasks ECS/Fargate."
  value       = module.security_groups.ecs_tasks_security_group_id
}

output "rds_proxy_security_group_id" {
  description = "Security group para el futuro RDS Proxy."
  value       = module.security_groups.rds_proxy_security_group_id
}

output "rds_security_group_id" {
  description = "Security group para el futuro RDS."
  value       = module.security_groups.rds_security_group_id
}

# ------------------------------------------------------------------------------
# Fase 4C.2 — ECS/Fargate + ALB
# ------------------------------------------------------------------------------

output "alb_dns_name" {
  description = "Nombre DNS del ALB (destino de un futuro registro DNS del dominio real)."
  value       = module.alb.alb_dns_name
}

output "alb_arn" {
  value = module.alb.alb_arn
}

output "backend_target_group_arn" {
  value = module.alb.backend_target_group_arn
}

output "frontend_target_group_arn" {
  value = module.alb.frontend_target_group_arn
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "ecs_cluster_arn" {
  value = module.ecs.cluster_arn
}

output "backend_service_name" {
  value = module.ecs.backend_service_name
}

output "frontend_service_name" {
  value = module.ecs.frontend_service_name
}

output "backend_task_definition_arn" {
  value = module.ecs.backend_task_definition_arn
}

output "frontend_task_definition_arn" {
  value = module.ecs.frontend_task_definition_arn
}

output "backend_migrate_task_definition_arn" {
  description = "Task definition de release (Alembic). Invocar manualmente con `aws ecs run-task` antes de actualizar el servicio backend — ver docs/aws/ECS_ALB_FOUNDATION.md."
  value       = module.ecs.backend_migrate_task_definition_arn
}

output "ecs_execution_role_arn" {
  value = module.ecs.execution_role_arn
}

output "ecs_task_role_arn" {
  value = module.ecs.task_role_arn
}
