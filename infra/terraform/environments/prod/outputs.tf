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
  description = "Task definition de release (Alembic, identidad MAESTRA). Invocar manualmente con `aws ecs run-task` antes de actualizar el servicio backend — ver docs/aws/ECS_ALB_FOUNDATION.md."
  value       = module.ecs.backend_migrate_task_definition_arn
}

output "backend_bootstrap_task_definition_arn" {
  description = "Task definition de bootstrap administrativo (crea/actualiza el rol de aplicacion, identidad MAESTRA). Invocar manualmente con `aws ecs run-task` — ver docs/aws/RDS_PROXY_FOUNDATION.md."
  value       = module.ecs.backend_bootstrap_task_definition_arn
}

output "ecs_backend_execution_role_arn" {
  description = "Execution Role de la familia backend (service/migrate/bootstrap). El frontend usa uno propio, ver ecs_frontend_execution_role_arn."
  value       = module.ecs.backend_execution_role_arn
}

output "ecs_backend_task_role_arn" {
  description = "Task Role de la familia backend (unico con permisos S3 de aplicacion). El frontend no tiene Task Role."
  value       = module.ecs.backend_task_role_arn
}

output "ecs_frontend_execution_role_arn" {
  description = "Execution Role propio del frontend, sin acceso a los secretos de DB/aplicacion."
  value       = module.ecs.frontend_execution_role_arn
}

# ------------------------------------------------------------------------------
# Fase 4C.3 — RDS PostgreSQL + RDS Proxy
# ------------------------------------------------------------------------------
# Sin password, sin DATABASE_URL con credenciales, sin contenido de Secrets
# Manager — solo identificadores y endpoints administrativos.

output "db_instance_id" {
  value = module.database.db_instance_id
}

output "db_endpoint" {
  description = "Endpoint DIRECTO de RDS — solo uso administrativo. La aplicacion usa db_proxy_endpoint."
  value       = module.database.db_endpoint
}

output "db_port" {
  value = module.database.db_port
}

output "db_proxy_endpoint" {
  description = "Endpoint de RDS Proxy — el que usa el backend/migration task."
  value       = module.database.proxy_endpoint
}

output "db_proxy_arn" {
  value = module.database.proxy_arn
}

output "db_master_user_secret_arn" {
  description = "ARN del secreto (Secrets Manager, gestionado por RDS) con la contrasenia del usuario MAESTRO — solo lo usan bootstrap y migrate. El ARN en si no es sensible; su contenido nunca se expone aqui."
  value       = module.database.master_user_secret_arn
}

output "db_app_user_secret_arn" {
  description = "ARN del secreto (Secrets Manager, creado por Terraform) con la contrasenia del usuario de APLICACION — el que usa el ECS Service del backend en runtime. El ARN en si no es sensible; su contenido nunca se expone aqui."
  value       = module.database.app_user_secret_arn
}

# ------------------------------------------------------------------------------
# Fase 4C.4 — WAF + CloudWatch / Observabilidad
# ------------------------------------------------------------------------------

output "waf_web_acl_arn" {
  value = module.waf.web_acl_arn
}

output "waf_web_acl_id" {
  value = module.waf.web_acl_id
}

output "cloudwatch_dashboard_name" {
  value = module.observability.dashboard_name
}

output "alarm_sns_topic_arn" {
  description = "ARN del SNS topic resuelto (creado o externo) usado por las alarmas, o cadena vacia si ninguno esta configurado."
  value       = module.observability.alarm_sns_topic_arn
}

output "alarm_names" {
  value = module.observability.alarm_names
}

# ------------------------------------------------------------------------------
# Fase 4C.5 — S3 Lifecycle
# ------------------------------------------------------------------------------

output "s3_lifecycle_management_enabled" {
  description = "true si este stack esta administrando activamente la configuracion del bucket de artifacts (var.s3_lifecycle_management_enabled=true y s3_artifact_bucket no vacio)."
  value       = module.s3_lifecycle.management_enabled
}

output "s3_versioning_enabled" {
  value = module.s3_lifecycle.versioning_enabled
}
