# Fundacion de Fase 4C.1: red (VPC, subredes public/app/db en 2+ AZ, NAT,
# VPC endpoint S3) y security groups (limites ALB -> ECS -> RDS Proxy ->
# RDS). ALB, ECS/Fargate, RDS, RDS Proxy, WAF y CloudWatch se agregan en
# subfases posteriores de Fase 4C — ver docs/aws/TERRAFORM_FOUNDATION.md.

# Fase 4D.2: combinacion insegura bloqueada en plan/apply sin introducir
# ningun dependency cycle — un `check` solo lee 2 variables de este mismo
# root module, no depende de ningun recurso ni de otro modulo. Con un
# certificado ACM real (HTTPS) configurado, las cookies de sesion del
# navegador SIEMPRE deben llevar el atributo Secure; `browser_cookie_secure
# = false` solo es valido durante la prueba temporal por HTTP sin dominio
# (certificate_arn = ""). No fuerza certificate_arn — un stack sin
# certificate_arn puede tener browser_cookie_secure en true o false por
# igual (el HTTP no lo necesita, pero tampoco lo prohibe).
check "https_requires_secure_cookies" {
  assert {
    condition     = var.certificate_arn == "" || var.browser_cookie_secure
    error_message = "browser_cookie_secure debe ser true cuando certificate_arn esta configurado (HTTPS real) — false solo es valido para la prueba temporal por HTTP sin dominio (certificate_arn vacio). Ver docs/aws/ECS_ALB_FOUNDATION.md, \"Prueba sin dominio (ALB DNS)\"."
  }
}

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

  access_logs_bucket = var.alb_access_logs_bucket
  access_logs_prefix = var.alb_access_logs_prefix
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
  ecs_tasks_security_group_id = module.security_groups.ecs_tasks_security_group_id
  db_port                     = var.db_port

  db_proxy_enabled = var.db_proxy_enabled

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

  performance_insights_enabled    = var.db_performance_insights_enabled
  enabled_cloudwatch_logs_exports = var.db_enabled_cloudwatch_logs_exports

  require_tls                  = var.db_proxy_require_tls
  idle_client_timeout          = var.db_proxy_idle_client_timeout
  connection_borrow_timeout    = var.db_proxy_connection_borrow_timeout
  max_connections_percent      = var.db_proxy_max_connections_percent
  max_idle_connections_percent = var.db_proxy_max_idle_connections_percent
}

# ------------------------------------------------------------------------------
# Fase 4C.8: bucket S3 de artifacts (evidencia/informes), ahora propiedad
# real de este stack — a diferencia del diseno anterior de Fase 4C.5 (ver
# modules/s3_lifecycle), este modulo SI declara aws_s3_bucket. Se instancia
# antes de module.ecs y module.s3_lifecycle porque ambos consumen su output
# bucket_name (el nombre REAL del bucket, nunca un string inventado). Ver
# docs/aws/BACKUP_DR_FOUNDATION.md, "Ownership del bucket de artifacts".
# ------------------------------------------------------------------------------

module "s3_artifact_bucket" {
  source = "../../modules/s3_artifact_bucket"

  bucket_name = var.s3_artifact_bucket_name

  enable_versioning = var.s3_versioning_enabled
  sse_mode          = var.s3_artifact_bucket_sse_mode
  kms_key_id        = var.s3_artifact_bucket_kms_key_id

  tags = local.common_tags
}

# ------------------------------------------------------------------------------
# Fase 4D.3: secretos de aplicacion (SECRET_KEY, BROWSER_REFRESH_TOKEN_HMAC_SECRET,
# SURVEY_SUBMISSION_HMAC_SECRET, INITIAL_ADMIN_PASSWORD) — los 4 que
# backend/app/core/config.py exige en app_env=production y que, hasta ahora,
# no tenian infraestructura propia (secrets_manager_secret_arns era un mapa
# vacio que el operador debia llenar a mano). Igual que module.s3_artifact_bucket,
# se instancia antes de module.ecs porque este consume su output. Valores
# ephemeral + write-only (ver modules/app_secrets/main.tf): nunca llegan al
# tfstate.
# ------------------------------------------------------------------------------

module "app_secrets" {
  source = "../../modules/app_secrets"

  name_prefix    = local.name_prefix
  secret_version = var.app_secrets_version

  tags = local.common_tags
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
  alb_dns_name                = module.alb.alb_dns_name
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

  log_retention_days         = var.log_retention_days
  container_insights_enabled = var.container_insights_enabled

  app_env                 = var.app_env
  web_concurrency         = var.web_concurrency
  browser_cookie_secure   = var.browser_cookie_secure
  frontend_origins        = var.frontend_origins
  browser_allowed_origins = var.browser_allowed_origins
  trusted_hosts           = var.trusted_hosts

  artifact_storage_provider = var.artifact_storage_provider
  s3_artifact_bucket        = module.s3_artifact_bucket.bucket_name
  s3_evidence_prefix        = var.s3_evidence_prefix
  s3_report_prefix          = var.s3_report_prefix

  # Endpoint de RDS Proxy (Fase 4C.3) cuando db_proxy_enabled=true (default);
  # endpoint directo de RDS SOLO si db_proxy_enabled=false (cuentas AWS con
  # RDS Proxy no disponible) — ver module.database.effective_db_host,
  # variables.tf "db_proxy_enabled" y docs/aws/RDS_PROXY_FOUNDATION.md.
  db_host = module.database.effective_db_host
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
  # Los 4 secretos generados por module.app_secrets son la base; un ARN
  # manual en var.secrets_manager_secret_arns (misma clave) tiene precedencia
  # y lo sobrescribe — mismo patron de precedencia ya usado en este archivo
  # para frontend_origins/browser_allowed_origins/trusted_hosts.
  secrets_manager_secret_arns = merge(module.app_secrets.secret_arns, var.secrets_manager_secret_arns)

  depends_on = [module.alb, module.database]
}

# ------------------------------------------------------------------------------
# Fase 4C.4: WAF + CloudWatch/observabilidad. Consumen unicamente outputs de
# los modulos de arriba — ningun modulo de 4C.1-4C.3 se modifica salvo
# ampliaciones minimas ya aplicadas (alb: access_logs opcional; ecs:
# Container Insights configurable; database: RDS log exports opcionales).
# ------------------------------------------------------------------------------

module "waf" {
  source = "../../modules/waf"

  name_prefix         = local.name_prefix
  alb_arn             = module.alb.alb_arn
  backend_path_prefix = "/api/"

  enable_common_rule_set           = var.waf_enable_common_rule_set
  enable_known_bad_inputs_rule_set = var.waf_enable_known_bad_inputs_rule_set
  enable_ip_reputation_list        = var.waf_enable_ip_reputation_list
  rate_limit_requests              = var.waf_rate_limit_requests

  waf_managed_rules_count_mode = var.waf_managed_rules_count_mode
  waf_sampled_requests_enabled = var.waf_sampled_requests_enabled

  waf_logging_enabled = var.waf_logging_enabled
  log_retention_days  = var.log_retention_days
}

module "observability" {
  source = "../../modules/observability"

  name_prefix = local.name_prefix
  aws_region  = var.aws_region

  alb_arn_suffix                   = module.alb.alb_arn_suffix
  backend_target_group_arn_suffix  = module.alb.backend_target_group_arn_suffix
  frontend_target_group_arn_suffix = module.alb.frontend_target_group_arn_suffix

  ecs_cluster_name          = module.ecs.cluster_name
  ecs_backend_service_name  = module.ecs.backend_service_name
  ecs_frontend_service_name = module.ecs.frontend_service_name

  db_instance_id           = module.database.db_instance_id
  db_allocated_storage_gib = var.db_allocated_storage

  backend_log_group_name = module.ecs.backend_log_group_name
  log_retention_days     = var.log_retention_days

  create_alarm_sns_topic = var.create_alarm_sns_topic
  alarm_sns_topic_arn    = var.alarm_sns_topic_arn
  enable_alarm_actions   = var.enable_alarm_actions
  enable_ok_actions      = var.enable_ok_actions

  alb_5xx_threshold                     = var.alb_5xx_threshold
  alb_target_5xx_threshold              = var.alb_target_5xx_threshold
  alb_response_time_threshold_seconds   = var.alb_response_time_threshold_seconds
  alb_evaluation_periods                = var.alb_evaluation_periods
  alb_unhealthy_host_evaluation_periods = var.alb_unhealthy_host_evaluation_periods

  ecs_cpu_threshold_percent    = var.ecs_cpu_threshold_percent
  ecs_memory_threshold_percent = var.ecs_memory_threshold_percent
  ecs_evaluation_periods       = var.ecs_evaluation_periods

  rds_cpu_threshold_percent          = var.rds_cpu_threshold_percent
  rds_free_storage_threshold_percent = var.rds_free_storage_threshold_percent
  rds_freeable_memory_threshold_mb   = var.rds_freeable_memory_threshold_mb
  rds_database_connections_threshold = var.rds_database_connections_threshold
  rds_evaluation_periods             = var.rds_evaluation_periods

  backend_error_log_threshold = var.backend_error_log_threshold

  depends_on = [module.ecs, module.database]
}

# ------------------------------------------------------------------------------
# Fase 4C.5/4C.8: S3 lifecycle. Administra UNICAMENTE la lifecycle
# configuration adjunta por nombre al bucket que crea module.s3_artifact_bucket
# (arriba) — el propio aws_s3_bucket, su versioning, su encryption por
# defecto y su public access block son responsabilidad exclusiva de ese otro
# modulo, nunca de este (ver modules/s3_lifecycle/variables.tf, "Ownership
# del bucket", y docs/aws/BACKUP_DR_FOUNDATION.md). Las dos confirmaciones de
# ownership del modulo se pasan como literal `true`: al ser este mismo stack
# quien crea el bucket exclusivamente para Territorio Electoral, ambas son
# ciertas por construccion — ya no son decisiones separadas que el operador
# deba confirmar a mano en tfvars (a diferencia del diseno anterior, donde el
# bucket era externo y esa certeza no existia).
#
# depends_on = [module.s3_artifact_bucket] explicito (revision pre-commit):
# bucket_name = module.s3_artifact_bucket.bucket_name SOLO crea una arista de
# dependencia hacia el recurso que produce ESE output (aws_s3_bucket.this) —
# Terraform no infiere una dependencia implicita hacia los recursos hermanos
# de ese mismo modulo (aws_s3_bucket_versioning.this,
# aws_s3_bucket_server_side_encryption_configuration.this,
# aws_s3_bucket_public_access_block.this, aws_s3_bucket_policy.secure_transport)
# porque ningun valor que este modulo consume proviene de ellos. Sin este
# depends_on explicito, aws_s3_bucket_lifecycle_configuration.this (con sus
# bloques noncurrent_version_* condicionados a var.enable_versioning, ver
# modules/s3_lifecycle/main.tf) podria crearse en paralelo con
# aws_s3_bucket_versioning.this, en vez de estrictamente despues — exactamente
# el race que este depends_on de modulo completo (equivalente al ya usado en
# module.ecs/module.observability mas arriba) elimina.
# ------------------------------------------------------------------------------

module "s3_lifecycle" {
  source = "../../modules/s3_lifecycle"

  enabled                                    = var.s3_lifecycle_management_enabled
  bucket_configuration_managed_by_this_stack = true
  bucket_dedicated_to_project                = true
  bucket_name                                = module.s3_artifact_bucket.bucket_name

  evidence_prefix = var.s3_evidence_prefix
  report_prefix   = var.s3_report_prefix

  enable_versioning = var.s3_versioning_enabled

  pending_expiration_days            = var.s3_pending_expiration_days
  pending_noncurrent_expiration_days = var.s3_pending_noncurrent_expiration_days

  reports_expiration_days = var.s3_reports_expiration_days

  evidence_final_transition_enabled       = var.s3_evidence_final_transition_enabled
  evidence_final_transition_days          = var.s3_evidence_final_transition_days
  evidence_final_transition_storage_class = var.s3_evidence_final_transition_storage_class

  evidence_final_noncurrent_transition_enabled       = var.s3_evidence_final_noncurrent_transition_enabled
  evidence_final_noncurrent_transition_days          = var.s3_evidence_final_noncurrent_transition_days
  evidence_final_noncurrent_transition_storage_class = var.s3_evidence_final_noncurrent_transition_storage_class
  evidence_final_noncurrent_expiration_days          = var.s3_evidence_final_noncurrent_expiration_days

  reports_transition_enabled       = var.s3_reports_transition_enabled
  reports_transition_days          = var.s3_reports_transition_days
  reports_transition_storage_class = var.s3_reports_transition_storage_class

  reports_noncurrent_transition_enabled       = var.s3_reports_noncurrent_transition_enabled
  reports_noncurrent_transition_days          = var.s3_reports_noncurrent_transition_days
  reports_noncurrent_transition_storage_class = var.s3_reports_noncurrent_transition_storage_class
  reports_noncurrent_expiration_days          = var.s3_reports_noncurrent_expiration_days

  expired_object_delete_marker_cleanup_enabled = var.s3_expired_delete_marker_cleanup_enabled

  abort_incomplete_multipart_upload_days = var.s3_abort_incomplete_multipart_upload_days

  depends_on = [module.s3_artifact_bucket]
}
