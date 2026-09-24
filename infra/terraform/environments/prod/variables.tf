variable "project" {
  description = "Nombre del proyecto. Se usa en el prefijo de nombres de recursos y en el tag Project."
  type        = string
  default     = "territorio-electoral"
}

variable "environment" {
  description = "Nombre del entorno. Hoy solo existe prod (ver docs/aws/TERRAFORM_FOUNDATION.md sobre por que no se crean staging/dev ficticios en Fase 4C.1)."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "Region de AWS donde se despliega la infraestructura. Default us-east-2 (Ohio): region habilitada en la cuenta AWS disponible para el primer deployment real — us-east-1 (N. Virginia) exigiria activar caracteristicas avanzadas de la cuenta que no se van a activar para esta prueba. Debe coincidir con var.aws_region de infra/terraform/bootstrap (recursos regionales, ACM futuro) — ver docs/aws/AWS_BOOTSTRAP.md, \"AWS region\"."
  type        = string
  default     = "us-east-2"
}

variable "vpc_cidr" {
  description = "Bloque CIDR de la VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Numero de zonas de disponibilidad (minimo 2)."
  type        = number
  default     = 2
}

variable "single_nat_gateway" {
  description = "true: un NAT Gateway compartido por todas las AZs (menor costo fijo). false: un NAT Gateway por AZ (alta disponibilidad, mayor costo). Ver docs/aws/TERRAFORM_FOUNDATION.md, seccion de costos, antes de cambiar el valor por defecto."
  type        = bool
  default     = true
}

variable "alb_ingress_cidr_blocks" {
  description = "Bloques CIDR permitidos hacia el ALB publico (puertos 80/443). Por defecto Internet (0.0.0.0/0); el filtrado fino de trafico malicioso corresponde a WAF en una subfase posterior, no a este security group."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "backend_container_port" {
  description = "Puerto del contenedor de la API (EXPOSE 8000 en backend/Dockerfile)."
  type        = number
  default     = 8000
}

variable "db_port" {
  description = "Puerto de PostgreSQL."
  type        = number
  default     = 5432
}

variable "additional_tags" {
  description = "Tags adicionales especificas de este despliegue, fusionadas con las tags comunes (Project/Environment/ManagedBy)."
  type        = map(string)
  default     = {}
}

# ==============================================================================
# Fase 4C.2 — ECS/Fargate + ALB
# ==============================================================================

variable "frontend_container_port" {
  description = "Puerto del contenedor del frontend (EXPOSE 8080 en frontend/Dockerfile)."
  type        = number
  default     = 8080
}

variable "certificate_arn" {
  description = "ARN de un certificado ACM ya emitido. Vacio (por defecto): el ALB solo sirve HTTP. No se crea ni se inventa ningun certificado ni dominio en Terraform — ver docs/aws/ECS_ALB_FOUNDATION.md."
  type        = string
  default     = ""
}

variable "backend_image" {
  description = "URI completa de la imagen del backend (ECR por digest o tag de commit inmutable). Sin valor por defecto — ver docs/aws/ECS_ALB_FOUNDATION.md, seccion 'Estrategia de imagenes'."
  type        = string
}

variable "frontend_image" {
  description = "URI completa de la imagen del frontend. Mismas reglas que backend_image."
  type        = string
}

variable "backend_task_cpu" {
  description = "CPU units Fargate del backend. 1024 (1 vCPU) — perfil RECOMMENDED de Fase 4C.6 (docs/performance/PERFORMANCE_BASELINE.md, §52): 256 quedo descartado con evidencia directa (Profile A, 0.25 vCPU/512MiB, satura con solo 10 VUs — p99 21s, memoria al 99.97% de su limite); Profile C (1 vCPU/2GiB) midio 34.19 RPS, p95 427ms, p99 823ms, 0% error, con margen de memoria amplio. Combinacion Fargate valida (1024 CPU admite 2048-8192 MiB en incrementos de 1024). Confidence MEDIUM — ver PENDING AWS VALIDATION en el documento."
  type        = string
  default     = "1024"
}

variable "backend_task_memory" {
  description = "Memoria (MiB) Fargate del backend. 2048 — acompana a backend_task_cpu=1024 (ver esa variable). El pico de memoria observado en Profile A (99.97% de 512MiB) fue consecuencia directa de la restriccion de CPU, no independiente — con 1 vCPU (Profile C) la misma aplicacion nunca supero 6.87% de 2048MiB."
  type        = string
  default     = "2048"
}

variable "frontend_task_cpu" {
  description = "CPU units Fargate del frontend. Sin cambio en Fase 4C.6 — nginx sirviendo assets estaticos nunca aparecio como cuello de botella en ningun benchmark, y no se sobredimensiona sin evidencia (docs/performance/PERFORMANCE_BASELINE.md, §44)."
  type        = string
  default     = "256"
}

variable "frontend_task_memory" {
  description = "Memoria (MiB) Fargate del frontend. Sin cambio en Fase 4C.6 — misma razon que frontend_task_cpu."
  type        = string
  default     = "512"
}

variable "backend_desired_count" {
  description = "Numero de tasks del servicio backend. 2 — perfil RECOMMENDED de Fase 4C.6: HA real (nunca 1 en produccion) + evidencia de escalado horizontal fuerte (scaling efficiency ~97.6% del ideal 2x bajo limites de recursos iguales, docs/performance/PERFORMANCE_BASELINE.md, §32). Confidence HIGH (HA)."
  type        = number
  default     = 2
}

variable "frontend_desired_count" {
  description = "Numero de tasks del servicio frontend. 2 — HA, misma razon que backend_desired_count (nunca rendimiento: frontend nunca fue el cuello de botella)."
  type        = number
  default     = 2
}

variable "fargate_spot_weight_percent" {
  description = "Porcentaje (0-100) de capacidad FARGATE_SPOT frente a FARGATE on-demand. 0 (por defecto) = 100% on-demand."
  type        = number
  default     = 0
}

variable "backend_min_capacity" {
  description = "Capacidad minima de autoscaling del backend. 2 — igual a backend_desired_count, mismo razonamiento de HA (Fase 4C.6)."
  type        = number
  default     = 2
}

variable "backend_max_capacity" {
  description = "Capacidad maxima de autoscaling del backend. 4 — perfil RECOMMENDED de Fase 4C.6 (sin cambio respecto al valor ya existente); extrapolado desde 2 instancias medidas directamente, confidence MEDIUM. El techo definitivo se valida con trafico AWS real."
  type        = number
  default     = 4
}

variable "frontend_min_capacity" {
  description = "Capacidad minima de autoscaling del frontend. 2 — HA, Fase 4C.6."
  type        = number
  default     = 2
}

variable "frontend_max_capacity" {
  type    = number
  default = 4
}

variable "backend_cpu_target_value" {
  type    = number
  default = 70
}

variable "frontend_cpu_target_value" {
  type    = number
  default = 70
}

variable "deployment_minimum_healthy_percent" {
  type    = number
  default = 100
}

variable "deployment_maximum_percent" {
  type    = number
  default = 200
}

variable "backend_health_check_grace_period_seconds" {
  type    = number
  default = 60
}

variable "frontend_health_check_grace_period_seconds" {
  type    = number
  default = 30
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "app_env" {
  type    = string
  default = "production"
}

variable "web_concurrency" {
  type    = number
  default = 1
}

variable "frontend_origins" {
  description = "FRONTEND_ORIGINS: dominio(s) reales del frontend, coma-separados. Sin valor por defecto: no se inventa ningun dominio."
  type        = string
}

variable "browser_allowed_origins" {
  description = "BROWSER_ALLOWED_ORIGINS. Mismas reglas que frontend_origins."
  type        = string
}

variable "trusted_hosts" {
  description = "TRUSTED_HOSTS, coma-separados."
  type        = string
}

variable "artifact_storage_provider" {
  description = "local o s3. Valor productivo para ECS/Fargate: siempre 's3' (default) — requiere s3_artifact_bucket. Ver docs/aws/ECS_ALB_FOUNDATION.md; el modulo ecs bloquea en plan/apply las combinaciones invalidas (s3 sin bucket, local con backend_desired_count > 1) via precondition."
  type        = string
  default     = "s3"

  validation {
    condition     = contains(["local", "s3"], var.artifact_storage_provider)
    error_message = "artifact_storage_provider debe ser \"local\" o \"s3\"."
  }
}

variable "s3_artifact_bucket" {
  type    = string
  default = ""
}

variable "s3_evidence_prefix" {
  description = "S3_EVIDENCE_PREFIX. Debe coincidir con backend/app/core/config.py (default \"evidence\") — la policy IAM del Task Role se genera con este mismo valor."
  type        = string
  default     = "evidence"
}

variable "s3_report_prefix" {
  description = "S3_REPORT_PREFIX. Debe coincidir con backend/app/core/config.py (default \"reports\") — la policy IAM del Task Role se genera con este mismo valor."
  type        = string
  default     = "reports"
}

variable "db_name" {
  type    = string
  default = "territorio_electoral"
}

variable "db_master_user" {
  description = "Usuario MAESTRO de RDS — reservado para bootstrap administrativo y migraciones Alembic. El ECS Service del backend NUNCA usa esta identidad. Ver docs/aws/RDS_PROXY_FOUNDATION.md, \"Separacion de identidades\"."
  type        = string
  default     = "territorio_user"
}

variable "db_app_user" {
  description = "Usuario de APLICACION (bajo privilegio, solo DML) — el que usa el ECS Service del backend en runtime, siempre via RDS Proxy."
  type        = string
  default     = "territorio_app"
}

variable "db_app_secret_version" {
  description = "Disparador de rotacion del secreto de aplicacion (secret_string_wo_version). Incrementar + apply + reinvocar la bootstrap task es el proceso manual de rotacion — ver docs/aws/RDS_PROXY_FOUNDATION.md, \"Rotacion futura\". Sin rotacion automatica en esta fase."
  type        = number
  default     = 1
}

variable "secrets_manager_secret_arns" {
  description = "Mapa nombre-de-variable-de-entorno -> ARN de Secrets Manager ADICIONAL a POSTGRES_PASSWORD (que ya se resuelve por separado segun identidad, master o app — ver main.tf). Vacio por defecto — ver docs/aws/TERRAFORM_FOUNDATION.md."
  type        = map(string)
  default     = {}
}

# ==============================================================================
# Fase 4C.3 — RDS PostgreSQL + RDS Proxy
# ==============================================================================
# db_host ya no es una variable: la provee module.database.proxy_endpoint
# (ver main.tf) — el backend siempre pasa por RDS Proxy, nunca por un
# endpoint suministrado externamente.

variable "db_engine_version" {
  description = "Version (solo major, \"16\") de PostgreSQL — igual major que Docker/CI. Ver docs/aws/RDS_PROXY_FOUNDATION.md."
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_max_allocated_storage" {
  type    = number
  default = 100
}

variable "db_backup_retention_period" {
  type    = number
  default = 7
}

variable "db_backup_window" {
  type    = string
  default = null
}

variable "db_maintenance_window" {
  type    = string
  default = null
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = false
}

variable "db_multi_az" {
  description = "false (por defecto): menor costo, menor disponibilidad. true: standby sincronico + failover automatico, mayor costo. Ver docs/aws/RDS_PROXY_FOUNDATION.md, seccion de costos."
  type        = bool
  default     = false
}

variable "db_performance_insights_enabled" {
  type    = bool
  default = false
}

variable "db_proxy_require_tls" {
  type    = bool
  default = true
}

variable "db_proxy_idle_client_timeout" {
  type    = number
  default = 1800
}

variable "db_proxy_connection_borrow_timeout" {
  type    = number
  default = 120
}

variable "db_proxy_max_connections_percent" {
  type    = number
  default = 100
}

variable "db_proxy_max_idle_connections_percent" {
  type    = number
  default = 50
}

variable "db_enabled_cloudwatch_logs_exports" {
  description = "Tipos de log de RDS a exportar a CloudWatch (solo \"postgresql\" es valido). Vacio por defecto — ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md, \"RDS log exports\"."
  type        = list(string)
  default     = []
}

# ==============================================================================
# Fase 4C.4 — WAF + CloudWatch / Observabilidad
# ==============================================================================

variable "alb_access_logs_bucket" {
  description = "Bucket S3 EXISTENTE para access logs del ALB. Vacio (por defecto): deshabilitados — Fase 4C.4 no crea ningun bucket nuevo. Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md, \"ALB access logs\"."
  type        = string
  default     = ""
}

variable "alb_access_logs_prefix" {
  type    = string
  default = "alb"
}

variable "container_insights_enabled" {
  description = "false (por defecto): CloudWatch Container Insights deshabilitado. true: habilita metricas ECS granulares adicionales, con costo propio. Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md, \"Costos\"."
  type        = bool
  default     = false
}

# --- WAF ---

variable "waf_enable_common_rule_set" {
  type    = bool
  default = true
}

variable "waf_enable_known_bad_inputs_rule_set" {
  type    = bool
  default = true
}

variable "waf_enable_ip_reputation_list" {
  type    = bool
  default = true
}

variable "waf_rate_limit_requests" {
  description = "Limite de solicitudes por IP en 5 minutos, acotado a /api/*. Baseline inicial — Fase 4C.6 lo ajustara."
  type        = number
  default     = 2000
}

variable "waf_managed_rules_count_mode" {
  description = "true (por defecto): los managed rule groups corren en Count (nunca bloquean, solo metrica/log) — rollout seguro recomendado por AWS. false: enforcement real (bloquean). Ver docs/aws/WAF_CLOUDWATCH_FOUNDATION.md, \"Rollout de Managed Rule Groups\"."
  type        = bool
  default     = true
}

variable "waf_sampled_requests_enabled" {
  description = "false (por defecto, recomendado para produccion inicial): sin muestreo de solicitudes reales de WAF — evita capturar contenido de solicitud sin una capa de proteccion de datos dedicada (data_protection_config, no implementado). cloudwatch_metrics_enabled permanece siempre true, independientemente de esta variable."
  type        = bool
  default     = false
}

variable "waf_logging_enabled" {
  description = "false (por defecto): sin logging de solicitudes WAF individuales (las metricas CloudWatch por regla quedan habilitadas de todas formas). true: crea un log group dedicado y habilita el logging."
  type        = bool
  default     = false
}

# --- SNS / acciones de alarma ---

variable "create_alarm_sns_topic" {
  description = "true: crea un SNS topic propio para las alarmas. false (por defecto, junto con alarm_sns_topic_arn vacio): las alarmas no notifican a ningun topic."
  type        = bool
  default     = false
}

variable "alarm_sns_topic_arn" {
  description = "ARN de un SNS topic EXISTENTE, si create_alarm_sns_topic=false. Sin direcciones de correo hardcodeadas en este Terraform — las suscripciones se administran aparte, manualmente."
  type        = string
  default     = ""
}

variable "enable_alarm_actions" {
  description = "false (por defecto): las alarmas se crean sin notificar a ningun SNS topic — apropiado para validacion/desarrollo Terraform."
  type        = bool
  default     = false
}

variable "enable_ok_actions" {
  type    = bool
  default = false
}

# --- Umbrales ALB ---

variable "alb_5xx_threshold" {
  type    = number
  default = 10
}

variable "alb_target_5xx_threshold" {
  type    = number
  default = 10
}

variable "alb_response_time_threshold_seconds" {
  type    = number
  default = 2
}

variable "alb_evaluation_periods" {
  type    = number
  default = 5
}

variable "alb_unhealthy_host_evaluation_periods" {
  type    = number
  default = 5
}

# --- Umbrales ECS ---

variable "ecs_cpu_threshold_percent" {
  type    = number
  default = 85
}

variable "ecs_memory_threshold_percent" {
  type    = number
  default = 85
}

variable "ecs_evaluation_periods" {
  type    = number
  default = 3
}

# --- Umbrales RDS ---

variable "rds_cpu_threshold_percent" {
  type    = number
  default = 80
}

variable "rds_free_storage_threshold_percent" {
  type    = number
  default = 20
}

variable "rds_freeable_memory_threshold_mb" {
  type    = number
  default = 256
}

variable "rds_database_connections_threshold" {
  description = "Baseline generico, sin relacion verificada con el max_connections real de la instance_class elegida — ajustar en Fase 4C.6."
  type        = number
  default     = 80
}

variable "rds_evaluation_periods" {
  type    = number
  default = 3
}

# --- Log-based metric ---

variable "backend_error_log_threshold" {
  type    = number
  default = 10
}

# ==============================================================================
# Fase 4C.5 — S3 Lifecycle + Backup/Disaster Recovery
# ==============================================================================
# El bucket de artifacts sigue sin ser un recurso Terraform (ver
# modules/s3_lifecycle/variables.tf, "Ownership del bucket"). RDS ya expone
# toda su superficie de backup/DR real (backup_retention_period,
# deletion_protection, skip_final_snapshot, multi_az — Fase 4C.3): esta
# seccion solo agrega el interruptor y los parametros del modulo
# s3_lifecycle. Ver docs/aws/BACKUP_DR_FOUNDATION.md.

variable "s3_lifecycle_management_enabled" {
  description = "false (por defecto): este stack NO administra ninguna configuracion del bucket externo de artifacts — decision de ownership explicita, nunca asumida silenciosamente. true: activa modules/s3_lifecycle (versioning, lifecycle rules, encryption por defecto, public access block) sobre var.s3_artifact_bucket — UNICAMENTE si ademas s3_bucket_configuration_managed_by_this_stack=true Y s3_bucket_dedicated_to_project=true (validado dentro del modulo). Tres confirmaciones independientes, nunca una sola variable."
  type        = bool
  default     = false
}

variable "s3_bucket_configuration_managed_by_this_stack" {
  description = "false (por defecto). Confirmacion EXPLICITA de que ningun otro stack/IaC administra hoy el versioning/lifecycle/encryption-por-defecto/public-access-block de s3_artifact_bucket — estos recursos REEMPLAZAN por completo esa configuracion, no la fusionan. Ver modules/s3_lifecycle/variables.tf y docs/aws/BACKUP_DR_FOUNDATION.md, \"Ownership del bucket de artifacts\"."
  type        = bool
  default     = false
}

variable "s3_bucket_dedicated_to_project" {
  description = "false (por defecto). Confirmacion EXPLICITA de que s3_artifact_bucket esta dedicado exclusivamente a Territorio Electoral, no compartido con otros proyectos/workloads — tambien justifica que las reglas bucket-wide del modulo (abort multipart, delete marker cleanup) no esten acotadas por prefijo."
  type        = bool
  default     = false
}

variable "s3_versioning_enabled" {
  type    = bool
  default = true
}

variable "s3_pending_expiration_days" {
  description = "Dias tras los que un objeto CURRENT bajo {s3_evidence_prefix}/pending/ recibe accion de expiration (upload-intent nunca completado)."
  type        = number
  default     = 2
}

variable "s3_pending_noncurrent_expiration_days" {
  description = "Solo con s3_versioning_enabled=true. Retencion noncurrent CORTA e independiente para {s3_evidence_prefix}/pending/ — deliberadamente mas corta que la de evidencia final/reports (90 dias): un pending nunca completado no tiene el mismo valor de recuperacion. Ver docs/aws/BACKUP_DR_FOUNDATION.md."
  type        = number
  default     = 7
}

variable "s3_reports_expiration_days" {
  description = "0 (por defecto): sin expiracion CURRENT fisica automatica de {s3_report_prefix}/* — backend/app/scripts/cleanup_generated_reports.py y ReportService.deactivate() ya expiran/eliminan reports vencidos via artifact_storage_factory.build_report_storage(), correcto para local y S3 por igual (ver docs/aws/BACKUP_DR_FOUNDATION.md, \"Auditoria de retencion real de reports\"). Un valor > 0 anadiria una segunda expiracion current redundante."
  type        = number
  default     = 0
}

variable "s3_evidence_final_transition_enabled" {
  type    = bool
  default = false
}

variable "s3_evidence_final_transition_days" {
  type    = number
  default = 90
}

variable "s3_evidence_final_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "s3_evidence_final_noncurrent_transition_enabled" {
  type    = bool
  default = true
}

variable "s3_evidence_final_noncurrent_transition_days" {
  type    = number
  default = 30
}

variable "s3_evidence_final_noncurrent_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "s3_evidence_final_noncurrent_expiration_days" {
  description = "Solo con s3_versioning_enabled=true. Retencion noncurrent LARGA para {s3_evidence_prefix}/final/, orientada a recuperacion ante overwrite/delete accidental de evidencia definitiva."
  type        = number
  default     = 90
}

variable "s3_reports_transition_enabled" {
  type    = bool
  default = false
}

variable "s3_reports_transition_days" {
  type    = number
  default = 90
}

variable "s3_reports_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "s3_reports_noncurrent_transition_enabled" {
  type    = bool
  default = true
}

variable "s3_reports_noncurrent_transition_days" {
  type    = number
  default = 30
}

variable "s3_reports_noncurrent_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "s3_reports_noncurrent_expiration_days" {
  description = "Solo con s3_versioning_enabled=true. Retencion noncurrent para {s3_report_prefix}/, independiente de evidence_final (mismo default, variable propia)."
  type        = number
  default     = 90
}

variable "s3_expired_delete_marker_cleanup_enabled" {
  type    = bool
  default = true
}

variable "s3_abort_incomplete_multipart_upload_days" {
  type    = number
  default = 7
}

variable "s3_default_encryption_enabled" {
  type    = bool
  default = true
}

variable "s3_lifecycle_sse_mode" {
  description = "AES256 (por defecto) o aws:kms — mismos valores validos que S3_SSE_MODE (backend/app/core/config.py). Configuracion por defecto a nivel de bucket (defensa en profundidad); la aplicacion ya envia su propio header de encryption en cada escritura, independientemente de esto."
  type        = string
  default     = "AES256"
}

variable "s3_lifecycle_kms_key_id" {
  type    = string
  default = ""
}

variable "s3_public_access_block_enabled" {
  type    = bool
  default = true
}
