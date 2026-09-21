# ============================================================================
# Red y seguridad (de Fase 4C.1 / modulo alb — nada de esto se crea aqui)
# ============================================================================

variable "name_prefix" {
  description = "Prefijo para nombrar todos los recursos ECS (ej. territorio-electoral-prod)."
  type        = string
}

variable "aws_region" {
  description = "Region de AWS (para awslogs-region en la configuracion de logs)."
  type        = string
}

variable "vpc_id" {
  description = "ID de la VPC (modulo network de Fase 4C.1) — necesario para el security group propio del frontend."
  type        = string
}

variable "app_subnet_ids" {
  description = "Subredes privadas de aplicacion (modulo network de Fase 4C.1) donde corren las tasks ECS."
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group del ALB (modulo security_groups de Fase 4C.1) — se usa solo para autorizar el egress del ALB hacia el security group propio del frontend creado en este modulo."
  type        = string
}

variable "ecs_tasks_security_group_id" {
  description = "Security group de las tasks ECS del backend, ya creado en Fase 4C.1 (modulo security_groups). El frontend usa un security group propio, creado en este modulo — ver docs/aws/ECS_ALB_FOUNDATION.md."
  type        = string
}

variable "backend_target_group_arn" {
  description = "ARN del target group del backend (modulo alb)."
  type        = string
}

variable "frontend_target_group_arn" {
  description = "ARN del target group del frontend (modulo alb)."
  type        = string
}

variable "backend_container_port" {
  type = number
}

variable "frontend_container_port" {
  type = number
}

variable "db_port" {
  description = "Puerto de PostgreSQL (POSTGRES_PORT) — el mismo puerto en el que escucha el endpoint de RDS Proxy."
  type        = number
  default     = 5432
}

# ============================================================================
# Imagenes de contenedor
# ============================================================================

variable "backend_image" {
  description = "URI completa de la imagen del backend (ej. ECR por digest o tag de commit inmutable). Sin valor por defecto: no se inventa ningun repositorio ni cuenta de AWS — debe suministrarla un pipeline/operador antes de cualquier plan/apply real. Evitar `:latest` en produccion (ver docs/aws/ECS_ALB_FOUNDATION.md)."
  type        = string
}

variable "frontend_image" {
  description = "URI completa de la imagen del frontend. Mismas reglas que backend_image."
  type        = string
}

# ============================================================================
# Dimensionamiento Fargate (valores iniciales conservadores — el
# dimensionamiento definitivo corresponde a Fase 4C.6)
# ============================================================================

variable "backend_task_cpu" {
  description = "CPU units Fargate del backend (256 = 0.25 vCPU)."
  type        = string
  default     = "256"
}

variable "backend_task_memory" {
  description = "Memoria (MiB) Fargate del backend."
  type        = string
  default     = "512"
}

variable "frontend_task_cpu" {
  description = "CPU units Fargate del frontend."
  type        = string
  default     = "256"
}

variable "frontend_task_memory" {
  description = "Memoria (MiB) Fargate del frontend."
  type        = string
  default     = "512"
}

variable "backend_desired_count" {
  description = "Numero de tasks del servicio backend. Fase 4B ya valido multiinstancia (docker-compose.multi-instance.yml); produccion deberia usar >= 2. Se mantiene en 1 por defecto porque el dimensionamiento definitivo es Fase 4C.6."
  type        = number
  default     = 1
}

variable "frontend_desired_count" {
  description = "Numero de tasks del servicio frontend. Escala independientemente del backend."
  type        = number
  default     = 1
}

variable "fargate_spot_weight_percent" {
  description = "Porcentaje (0-100) de capacidad FARGATE_SPOT frente a FARGATE on-demand, aplicado igual a backend y frontend. 0 (por defecto) = 100% on-demand. FARGATE_SPOT nunca es la unica capacidad: el peso restante siempre corre en FARGATE on-demand."
  type        = number
  default     = 0

  validation {
    condition     = var.fargate_spot_weight_percent >= 0 && var.fargate_spot_weight_percent <= 100
    error_message = "fargate_spot_weight_percent debe estar entre 0 y 100."
  }
}

# ============================================================================
# Autoscaling (Application Auto Scaling, target tracking por CPU —
# dimensionamiento definitivo en Fase 4C.6)
# ============================================================================

variable "backend_min_capacity" {
  type    = number
  default = 1
}

variable "backend_max_capacity" {
  type    = number
  default = 4
}

variable "frontend_min_capacity" {
  type    = number
  default = 1
}

variable "frontend_max_capacity" {
  type    = number
  default = 4
}

variable "backend_cpu_target_value" {
  description = "Objetivo de utilizacion de CPU (%) para el target tracking del backend."
  type        = number
  default     = 70
}

variable "frontend_cpu_target_value" {
  type    = number
  default = 70
}

# ============================================================================
# Deployment
# ============================================================================

variable "deployment_minimum_healthy_percent" {
  type    = number
  default = 100
}

variable "deployment_maximum_percent" {
  type    = number
  default = 200
}

variable "backend_health_check_grace_period_seconds" {
  description = "Tiempo que ECS espera antes de considerar los resultados del health check del ALB para reemplazar una task del backend — cubre el arranque del proceso (pull de imagen, import de la app), no una base de datos lenta: el target group ya usa /api/v1/health (liveness, nunca toca la DB), no /api/v1/ready. Ver docs/aws/ECS_ALB_FOUNDATION.md."
  type        = number
  default     = 60
}

variable "frontend_health_check_grace_period_seconds" {
  type    = number
  default = 30
}

# ============================================================================
# Logging (awslogs minimo — CloudWatch avanzado es Fase 4C.4)
# ============================================================================

variable "log_retention_days" {
  type    = number
  default = 30
}

# ============================================================================
# Configuracion de aplicacion (backend) — no sensible
# ============================================================================

variable "app_env" {
  type    = string
  default = "production"
}

variable "web_concurrency" {
  description = "Workers uvicorn por task (WEB_CONCURRENCY). Con ECS escalando por numero de tasks, 1 es la recomendacion de Fase 4B (backend/Dockerfile) — cada task refleja un proceso real en su propio health/readiness."
  type        = number
  default     = 1
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
  description = "TRUSTED_HOSTS, coma-separados. Debe incluir el dominio real y, si corresponde, el DNS del ALB."
  type        = string
}

variable "artifact_storage_provider" {
  description = "local o s3. El valor productivo para ECS/Fargate es SIEMPRE 's3' (default) — con >= 1 task efimera y potencialmente >1 replica, 'local' pierde/desincroniza evidencia y informes entre tasks. 's3' requiere ademas s3_artifact_bucket (el bucket no es un recurso de este Terraform todavia, ver docs/aws/ECS_ALB_FOUNDATION.md); la combinacion s3+bucket-vacio y la combinacion local+backend_desired_count>1 quedan bloqueadas por un precondition en aws_ecs_service.backend, no solo documentadas."
  type        = string
  default     = "s3"

  validation {
    condition     = contains(["local", "s3"], var.artifact_storage_provider)
    error_message = "artifact_storage_provider debe ser \"local\" o \"s3\"."
  }
}

variable "s3_artifact_bucket" {
  description = "Nombre del bucket S3 de artifacts. Vacio por defecto (el bucket todavia no es un recurso de este Terraform). Si se provee, el Task Role recibe permisos S3 de minimo privilegio (GetObject/PutObject/DeleteObject) sobre los prefijos s3_evidence_prefix/s3_report_prefix de ese bucket."
  type        = string
  default     = ""
}

variable "s3_evidence_prefix" {
  description = "S3_EVIDENCE_PREFIX. Debe coincidir con el prefijo que usa la aplicacion (backend/app/core/config.py, default \"evidence\") — la policy IAM del Task Role se genera con este mismo valor, nunca duplicado a mano."
  type        = string
  default     = "evidence"
}

variable "s3_report_prefix" {
  description = "S3_REPORT_PREFIX. Debe coincidir con el prefijo que usa la aplicacion (backend/app/core/config.py, default \"reports\") — la policy IAM del Task Role se genera con este mismo valor, nunca duplicado a mano."
  type        = string
  default     = "reports"
}

variable "db_host" {
  description = "POSTGRES_HOST: endpoint de PostgreSQL (RDS/RDS Proxy). Sin valor por defecto: RDS/RDS Proxy todavia no existen en este Terraform (subfase posterior) — variable preparada para esa integracion."
  type        = string
}

variable "db_name" {
  type    = string
  default = "territorio_electoral"
}

variable "db_master_user" {
  description = "Usuario MAESTRO de RDS (POSTGRES_USER para bootstrap y migration task UNICAMENTE — el ECS Service del backend nunca lo usa). Ver docs/aws/RDS_PROXY_FOUNDATION.md, \"Separacion de identidades\"."
  type        = string
  default     = "territorio_user"
}

variable "db_master_secret_arn" {
  description = "ARN del secreto (Secrets Manager, gestionado por RDS) con la contrasenia del usuario maestro — solo lo consumen backend_migrate y backend_bootstrap."
  type        = string
}

variable "db_app_user" {
  description = "Usuario de APLICACION (POSTGRES_USER para el ECS Service del backend en runtime, siempre via RDS Proxy). Bajo privilegio: solo DML, sin CREATEROLE/CREATEDB."
  type        = string
  default     = "territorio_app"
}

variable "db_app_secret_arn" {
  description = "ARN del secreto (Secrets Manager, creado por modules/database) con la contrasenia del usuario de aplicacion — lo consume el ECS Service del backend, y tambien backend_bootstrap (para crear/actualizar ese mismo rol)."
  type        = string
}

variable "db_pool_size" {
  type    = number
  default = 5
}

variable "db_max_overflow" {
  type    = number
  default = 10
}

variable "db_pool_timeout_seconds" {
  type    = number
  default = 30
}

variable "db_pool_recycle_seconds" {
  type    = number
  default = 1800
}

variable "db_connect_timeout_seconds" {
  type    = number
  default = 10
}

variable "secrets_manager_secret_arns" {
  description = "Mapa nombre-de-variable-de-entorno -> ARN de Secrets Manager para secretos ADICIONALES a POSTGRES_PASSWORD (que ya se resuelve por separado via db_master_secret_arn/db_app_secret_arn) — ej. { SECRET_KEY = \"arn:aws:secretsmanager:...\" }. Vacio por defecto: todavia no existe infraestructura Terraform para esos otros secretos. Se aplica por igual a los tres containers de la familia backend (service, migrate, bootstrap)."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
