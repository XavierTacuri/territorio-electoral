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

variable "browser_cookie_secure" {
  description = "BROWSER_COOKIE_SECURE. true (default, produccion normal/dominio HTTPS): las cookies de sesion del navegador llevan el atributo Secure. false: SOLO para la prueba temporal por HTTP sin dominio via DNS del ALB (certificate_arn=\"\") — el check \"https_requires_secure_cookies\" (main.tf) impide dejarlo en false si certificate_arn esta configurado. Ver docs/aws/ECS_ALB_FOUNDATION.md, \"Prueba sin dominio (ALB DNS)\"."
  type        = bool
  default     = true
}

variable "frontend_origins" {
  description = "FRONTEND_ORIGINS: origen(es) real(es) del frontend, coma-separados, CON esquema (ej. \"https://app.dominio-real\"). Vacio (por defecto): sin dominio propio todavia — module.ecs deriva automaticamente \"http://<DNS del ALB>\" para la primera prueba sin dominio/ACM (ver docs/aws/ECS_ALB_FOUNDATION.md, \"Prueba sin dominio (ALB DNS)\"). Nunca se inventa un dominio: un valor explicito aqui tiene siempre precedencia sobre la derivacion automatica, y es obligatorio en cuanto exista un dominio real (no se puede emitir un certificado ACM para el DNS propio del ALB, asi que certificate_arn y esta derivacion automatica son mutuamente excluyentes en la practica)."
  type        = string
  default     = ""
}

variable "browser_allowed_origins" {
  description = "BROWSER_ALLOWED_ORIGINS. Mismas reglas y mismo default vacio (auto-derivado) que frontend_origins."
  type        = string
  default     = ""
}

variable "trusted_hosts" {
  description = "TRUSTED_HOSTS, coma-separados, SIN esquema (Starlette TrustedHostMiddleware compara solo el hostname). Vacio (por defecto): se deriva automaticamente el DNS del ALB. Un valor explicito tiene precedencia — debe incluir el dominio real y, si corresponde, seguir incluyendo el DNS del ALB."
  type        = string
  default     = ""
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

variable "s3_artifact_bucket_name" {
  description = "Nombre GLOBALMENTE UNICO del bucket S3 de artifacts (evidencia/informes) que module.s3_artifact_bucket crea y administra (Fase 4C.8) — ya no un bucket externo. Sin default: nunca se inventa un nombre de bucket real, mismo criterio que state_bucket_name en infra/terraform/bootstrap y que backend_image/frontend_image/frontend_origins mas arriba. Obligatorio: artifact_storage_provider por defecto es \"s3\", que requiere este valor. RECOMENDADO para este proyecto: evitar \".\" en el nombre (aunque la regla oficial de S3 lo permite, ver validations abajo) — un nombre con puntos rompe la validacion de certificado TLS wildcard de S3 en acceso virtual-hosted-style (*.s3.amazonaws.com), degradando a HTTP o a path-style; un nombre solo con letras/digitos/guiones evita ese problema por completo. Ver terraform.tfvars.example."
  type        = string

  # Reglas oficiales de nombres de bucket S3 (General Purpose Buckets),
  # cada una en su propia validation — mas legible y mas facil de mantener
  # que una unica regex monolitica, y cada mensaje de error senala
  # exactamente que regla se violo.

  validation {
    condition     = length(var.s3_artifact_bucket_name) >= 3 && length(var.s3_artifact_bucket_name) <= 63
    error_message = "s3_artifact_bucket_name debe tener entre 3 y 63 caracteres."
  }

  validation {
    condition     = can(regex("^[a-z0-9.-]+$", var.s3_artifact_bucket_name))
    error_message = "s3_artifact_bucket_name solo puede contener minusculas (a-z), digitos (0-9), puntos (.) y guiones (-) — sin mayusculas, guiones bajos ni ningun otro caracter."
  }

  validation {
    condition     = can(regex("^[a-z0-9].*[a-z0-9]$", var.s3_artifact_bucket_name))
    error_message = "s3_artifact_bucket_name debe empezar y terminar con una letra minuscula o un digito — nunca con un punto o un guion."
  }

  validation {
    condition     = !can(regex("\\.\\.", var.s3_artifact_bucket_name))
    error_message = "s3_artifact_bucket_name no puede contener dos puntos consecutivos (\"..\")."
  }

  validation {
    condition     = !can(regex("^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$", var.s3_artifact_bucket_name))
    error_message = "s3_artifact_bucket_name no puede tener formato de direccion IPv4 (ej. \"192.168.1.1\") — prohibido por las reglas de S3, independientemente de si los octetos son validos como IP real."
  }

  validation {
    condition     = !can(regex("^(xn--|sthree-|amzn-s3-demo-)", var.s3_artifact_bucket_name))
    error_message = "s3_artifact_bucket_name no puede empezar con un prefijo reservado por AWS: \"xn--\", \"sthree-\" o \"amzn-s3-demo-\"."
  }

  validation {
    condition     = !can(regex("(-s3alias|--ol-s3|\\.mrap|--x-s3|--table-s3)$", var.s3_artifact_bucket_name))
    error_message = "s3_artifact_bucket_name no puede terminar con un sufijo reservado por AWS: \"-s3alias\", \"--ol-s3\", \".mrap\", \"--x-s3\" o \"--table-s3\"."
  }
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
  description = "Mapa nombre-de-variable-de-entorno -> ARN de Secrets Manager ADICIONAL a POSTGRES_PASSWORD (que ya se resuelve por separado segun identidad, master o app — ver main.tf) y a los 4 generados automaticamente por module.app_secrets (SECRET_KEY, BROWSER_REFRESH_TOKEN_HMAC_SECRET, SURVEY_SUBMISSION_HMAC_SECRET, INITIAL_ADMIN_PASSWORD). Vacio por defecto: un ARN aqui con la MISMA clave que uno de esos 4 tiene precedencia y lo sobrescribe (main.tf hace el merge); tambien sirve para secretos futuros sin infraestructura propia todavia."
  type        = map(string)
  default     = {}
}

variable "app_secrets_version" {
  description = "Disparador de rotacion de los 4 secretos de aplicacion generados por module.app_secrets (secret_string_wo_version, mismo patron que db_app_secret_version). Incrementar + apply reescribe los 4 con nuevos valores aleatorios. Sin rotacion automatica en esta fase."
  type        = number
  default     = 1
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

variable "db_proxy_enabled" {
  description = "true (DEFAULT productivo, no cambiar): arquitectura production-like completa -- ECS runtime se conecta a PostgreSQL a traves de RDS Proxy. false: SOLO para cuentas AWS con planes limitados donde la API de AWS rechaza la creacion de RDS Proxy con FreeTierRestrictionError (\"This feature isn't available with free plan accounts\") -- ECS runtime se conecta DIRECTO a la instancia RDS. RDS Proxy nunca se elimina de la arquitectura: este interruptor solo evita crear su SERVICIO en cuentas donde AWS lo rechaza. Ver module.database (modules/database/variables.tf) y docs/aws/RDS_PROXY_FOUNDATION.md, \"Modo direct-RDS para cuentas Free Plan\". Set false only for limited test accounts where RDS Proxy is unavailable."
  type        = bool
  default     = true
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
# Fase 4C.5/4C.8 — Bucket de artifacts + S3 Lifecycle + Backup/Disaster Recovery
# ==============================================================================
# El bucket de artifacts es, desde Fase 4C.8, un recurso Terraform real
# (module.s3_artifact_bucket, ver main.tf) — ya no externo. RDS ya expone
# toda su superficie de backup/DR real (backup_retention_period,
# deletion_protection, skip_final_snapshot, multi_az — Fase 4C.3): esta
# seccion agrega el nombre del bucket, su encryption, y el interruptor y los
# parametros del modulo s3_lifecycle. Ver docs/aws/BACKUP_DR_FOUNDATION.md.

variable "s3_lifecycle_management_enabled" {
  description = "true (por defecto): activa modules/s3_lifecycle (reglas de expiracion/transicion por prefijo) sobre el bucket real que crea module.s3_artifact_bucket. Las dos confirmaciones de ownership que este modulo exige internamente ya no son variables de tfvars — environments/prod/main.tf las pasa como literal true, porque al ser este mismo stack quien crea el bucket son ciertas por construccion (a diferencia del diseno anterior, con un bucket externo). false: sin ninguna regla de lifecycle (el bucket sigue existiendo, con versioning/encryption/public-access-block igual de activos via module.s3_artifact_bucket, que no depende de este interruptor)."
  type        = bool
  default     = true
}

variable "s3_versioning_enabled" {
  description = "true (por defecto): S3 Versioning activado en el bucket de artifacts. Una unica fuente de verdad pasada a AMBOS module.s3_artifact_bucket (que crea el recurso real aws_s3_bucket_versioning) y module.s3_lifecycle (que lo usa solo para decidir si sus reglas incluyen noncurrent_version_*) — nunca dos booleans independientes que puedan desincronizarse."
  type        = bool
  default     = true
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

variable "s3_artifact_bucket_sse_mode" {
  description = "AES256 (por defecto) o aws:kms — mismos valores validos que S3_SSE_MODE (backend/app/core/config.py). Encryption por defecto SIEMPRE activa a nivel de bucket (module.s3_artifact_bucket, sin interruptor on/off — defensa en profundidad); la aplicacion ya envia ademas su propio header de encryption en cada escritura, independientemente de esto."
  type        = string
  default     = "AES256"
}

variable "s3_artifact_bucket_kms_key_id" {
  description = "ARN/ID de la CMK, obligatorio solo si s3_artifact_bucket_sse_mode = \"aws:kms\". Sin valor por defecto: no se crea ninguna CMK automaticamente."
  type        = string
  default     = ""
}

# Nota: ya no existen s3_default_encryption_enabled ni s3_public_access_block_enabled
# como interruptores — module.s3_artifact_bucket aplica encryption y Public
# Access Block (4/4) de forma incondicional sobre el bucket que el mismo
# crea, sin variable que pueda desactivarlos por error.
