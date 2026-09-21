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

# ------------------------------------------------------------------------------
# Fase 4C.3: RDS PostgreSQL + RDS Proxy. Usa exclusivamente las database
# subnets y los security groups rds/rds_proxy ya creados en Fase 4C.1 —
# ningun modulo de 4C.1 se modifica.
# ------------------------------------------------------------------------------

module "database" {
  source = "../../modules/database"

  name_prefix                 = local.name_prefix
  db_subnet_ids               = module.network.db_subnet_ids
  rds_security_group_id       = module.security_groups.rds_security_group_id
  rds_proxy_security_group_id = module.security_groups.rds_proxy_security_group_id
  db_port                     = var.db_port

  engine_version        = var.db_engine_version
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  db_name               = var.db_name
  db_username           = var.db_master_user
  db_app_username       = var.db_app_user
  db_app_secret_version = var.db_app_secret_version

  backup_retention_period = var.db_backup_retention_period
  backup_window           = var.db_backup_window
  maintenance_window      = var.db_maintenance_window
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.db_skip_final_snapshot
  multi_az                = var.db_multi_az

  performance_insights_enabled = var.db_performance_insights_enabled

  require_tls                  = var.db_proxy_require_tls
  idle_client_timeout          = var.db_proxy_idle_client_timeout
  connection_borrow_timeout    = var.db_proxy_connection_borrow_timeout
  max_connections_percent      = var.db_proxy_max_connections_percent
  max_idle_connections_percent = var.db_proxy_max_idle_connections_percent
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

  # Endpoint de RDS Proxy (Fase 4C.3), nunca el endpoint directo de RDS — el
  # backend nunca se salta el pooling administrado del proxy.
  db_host = module.database.proxy_endpoint
  db_name = var.db_name
  db_port = var.db_port

  # Separacion de identidades (revision de produccion de Fase 4C.3): el ECS
  # Service del backend usa SIEMPRE el usuario de aplicacion (bajo
  # privilegio); migrate y bootstrap usan SIEMPRE el usuario maestro. Ver
  # docs/aws/RDS_PROXY_FOUNDATION.md, "Separacion de identidades".
  db_master_user       = var.db_master_user
  db_master_secret_arn = module.database.master_user_secret_arn
  db_app_user          = var.db_app_user
  db_app_secret_arn    = module.database.app_user_secret_arn

  # Secretos ADICIONALES (SECRET_KEY, etc.), todavia sin infraestructura
  # propia — POSTGRES_PASSWORD ya no viaja por aqui, ver db_master_secret_arn/db_app_secret_arn arriba.
  secrets_manager_secret_arns = var.secrets_manager_secret_arns

  depends_on = [module.alb, module.database]
}
