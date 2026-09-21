# Fundacion de Fase 4C.1: red (VPC, subredes public/app/db en 2+ AZ, NAT,
# VPC endpoint S3) y security groups (limites ALB -> ECS -> RDS Proxy ->
# RDS). ALB, ECS/Fargate, RDS, RDS Proxy, WAF y CloudWatch se agregan en
# subfases posteriores de Fase 4C — ver docs/aws/TERRAFORM_FOUNDATION.md.

module "network" {
  source = "../../modules/network"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  az_count           = var.az_count
  single_nat_gateway = var.single_nat_gateway
}

module "security_groups" {
  source = "../../modules/security_groups"

  name_prefix             = local.name_prefix
  vpc_id                  = module.network.vpc_id
  alb_ingress_cidr_blocks = var.alb_ingress_cidr_blocks
  backend_container_port  = var.backend_container_port
  db_port                 = var.db_port
}

# ------------------------------------------------------------------------------
# Fase 4C.2: ALB + ECS/Fargate. Consumen unicamente los outputs de network y
# security_groups de arriba (Fase 4C.1) — ningun modulo de 4C.1 se modifica.
# ------------------------------------------------------------------------------

module "alb" {
  source = "../../modules/alb"

  name_prefix             = local.name_prefix
  vpc_id                  = module.network.vpc_id
  public_subnet_ids       = module.network.public_subnet_ids
  alb_security_group_id   = module.security_groups.alb_security_group_id
  backend_container_port  = var.backend_container_port
  frontend_container_port = var.frontend_container_port
  certificate_arn         = var.certificate_arn
}

module "ecs" {
  source = "../../modules/ecs"

  name_prefix                 = local.name_prefix
  aws_region                  = var.aws_region
  vpc_id                      = module.network.vpc_id
  app_subnet_ids              = module.network.app_subnet_ids
  alb_security_group_id       = module.security_groups.alb_security_group_id
  ecs_tasks_security_group_id = module.security_groups.ecs_tasks_security_group_id
  backend_target_group_arn    = module.alb.backend_target_group_arn
  frontend_target_group_arn   = module.alb.frontend_target_group_arn
  backend_container_port      = var.backend_container_port
  frontend_container_port     = var.frontend_container_port

  backend_image  = var.backend_image
  frontend_image = var.frontend_image

  backend_task_cpu       = var.backend_task_cpu
  backend_task_memory    = var.backend_task_memory
  frontend_task_cpu      = var.frontend_task_cpu
  frontend_task_memory   = var.frontend_task_memory
  backend_desired_count  = var.backend_desired_count
  frontend_desired_count = var.frontend_desired_count

  fargate_spot_weight_percent = var.fargate_spot_weight_percent

  backend_min_capacity      = var.backend_min_capacity
  backend_max_capacity      = var.backend_max_capacity
  frontend_min_capacity     = var.frontend_min_capacity
  frontend_max_capacity     = var.frontend_max_capacity
  backend_cpu_target_value  = var.backend_cpu_target_value
  frontend_cpu_target_value = var.frontend_cpu_target_value

  deployment_minimum_healthy_percent         = var.deployment_minimum_healthy_percent
  deployment_maximum_percent                 = var.deployment_maximum_percent
  backend_health_check_grace_period_seconds  = var.backend_health_check_grace_period_seconds
  frontend_health_check_grace_period_seconds = var.frontend_health_check_grace_period_seconds

  log_retention_days = var.log_retention_days

  app_env                 = var.app_env
  web_concurrency         = var.web_concurrency
  frontend_origins        = var.frontend_origins
  browser_allowed_origins = var.browser_allowed_origins
  trusted_hosts           = var.trusted_hosts

  artifact_storage_provider = var.artifact_storage_provider
  s3_artifact_bucket        = var.s3_artifact_bucket
  s3_evidence_prefix        = var.s3_evidence_prefix
  s3_report_prefix          = var.s3_report_prefix

  db_host = var.db_host
  db_name = var.db_name
  db_user = var.db_user

  secrets_manager_secret_arns = var.secrets_manager_secret_arns

  depends_on = [module.alb]
}
