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
