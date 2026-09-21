# ============================================================================
# Red y seguridad (de Fase 4C.1 — nada de esto se crea aqui)
# ============================================================================

variable "name_prefix" {
  description = "Prefijo para nombrar todos los recursos de base de datos (ej. territorio-electoral-prod)."
  type        = string
}

variable "db_subnet_ids" {
  description = "Subredes privadas de base de datos (modulo network de Fase 4C.1), al menos 2 AZ. RDS y RDS Proxy corren aqui — nunca en subredes publicas ni de aplicacion."
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "Security group de RDS, ya creado en Fase 4C.1 (modulo security_groups): ingress unicamente desde el security group de RDS Proxy."
  type        = string
}

variable "rds_proxy_security_group_id" {
  description = "Security group de RDS Proxy, ya creado en Fase 4C.1 (modulo security_groups): ingress unicamente desde el security group de las tasks ECS del backend."
  type        = string
}

variable "db_port" {
  type    = number
  default = 5432
}

# ============================================================================
# RDS PostgreSQL
# ============================================================================

variable "engine_version" {
  description = "Version de PostgreSQL. \"16\" (solo major) deja que RDS elija la ultima minor 16.x soportada al momento del apply, en vez de fijar una minor que no se puede verificar sin credenciales/consola de AWS en esta fase. Elegida para igualar la major que ya usa Docker/CI (postgis/postgis:16-3.4) sin forzar una actualizacion de motor como parte de esta subfase."
  type        = string
  default     = "16"
}

variable "instance_class" {
  description = "Clase de instancia RDS. Valor inicial conservador — el dimensionamiento definitivo es Fase 4C.6."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Almacenamiento inicial (GiB)."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Tope de RDS Storage Autoscaling (GiB) — evita una parada por disco lleno sin requerir un `apply` manual. El dimensionamiento definitivo es Fase 4C.6."
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Nombre de la base de datos (POSTGRES_DB). Debe coincidir con el que recibe el backend — ver environments/prod/main.tf, una sola fuente de verdad (var.db_name en la raiz)."
  type        = string
}

variable "db_username" {
  description = "Usuario MAESTRO de RDS. Reservado para bootstrap administrativo y migraciones Alembic (necesitan poder crear extensiones/roles/objetos) — el ECS backend en runtime NUNCA usa esta identidad, ver docs/aws/RDS_PROXY_FOUNDATION.md, seccion \"Separacion de identidades\"."
  type        = string
}

variable "db_app_username" {
  description = "Usuario de APLICACION (bajo privilegio: solo DML sobre las tablas del esquema, sin CREATEROLE/CREATEDB/rds_superuser). Es el que usa el ECS backend en runtime, siempre a traves de RDS Proxy. Se crea/actualiza mediante la task de bootstrap (modulo ecs), no mediante este modulo directamente — este modulo solo genera y guarda su secreto."
  type        = string
  default     = "territorio_app"
}

variable "db_app_secret_version" {
  description = "Disparador de reescritura de aws_secretsmanager_secret_version.app_user (argumento write-only secret_string_wo_version). Terraform no puede detectar por si solo que un valor write-only \"cambio\" — este numero es la unica senial. Incrementarlo (y aplicar) es el primer paso de una rotacion manual de la contrasenia de aplicacion; el segundo paso (fuera de este modulo) es volver a invocar la bootstrap task para que PostgreSQL adopte el nuevo valor. Sin rotacion automatica en esta fase."
  type        = number
  default     = 1
}

variable "backup_retention_period" {
  description = "Dias de retencion de backups automatizados. 0 deshabilita los backups automatizados (no recomendado en produccion)."
  type        = number
  default     = 7
}

variable "backup_window" {
  description = "Ventana de backup (UTC, formato hh24:mi-hh24:mi). null (por defecto) deja que RDS asigne una ventana automaticamente — no se inventa un horario operativo real sin que el equipo lo decida."
  type        = string
  default     = null
}

variable "maintenance_window" {
  description = "Ventana de mantenimiento (formato ddd:hh24:mi-ddd:hh24:mi). null (por defecto) deja que RDS asigne una automaticamente."
  type        = string
  default     = null
}

variable "deletion_protection" {
  description = "true (por defecto, recomendado para produccion): AWS rechaza cualquier intento de eliminar la instancia hasta desactivar esto explicitamente. false solo para entornos no productivos."
  type        = bool
  default     = true
}

variable "skip_final_snapshot" {
  description = "false (por defecto, recomendado para produccion): al eliminar la instancia, RDS crea un snapshot final antes de destruirla. true omite ese snapshot (perdida de datos irreversible si no hay otro backup) — solo para entornos desechables."
  type        = bool
  default     = false
}

variable "multi_az" {
  description = "false (por defecto): instancia unica, menor costo, menor disponibilidad (una caida de AZ es una caida de base de datos). true: standby sincronico en otra AZ con failover automatico, mayor costo (aprox. el doble del costo de computo/almacenamiento de la instancia). Decision de costo/disponibilidad deliberadamente diferida — ver docs/aws/RDS_PROXY_FOUNDATION.md."
  type        = bool
  default     = false
}

variable "performance_insights_enabled" {
  description = "false (por defecto): sin costo adicional. true habilita Performance Insights (gratis los primeros 7 dias de retencion, costo si se extiende la retencion) — util para diagnostico de queries, no obligatorio para esta fase."
  type        = bool
  default     = false
}

variable "copy_tags_to_snapshot" {
  type    = bool
  default = true
}

variable "apply_immediately" {
  description = "false (por defecto): los cambios que requieren downtime esperan a la maintenance window en vez de aplicarse de inmediato. Mantenido en false — un `apply` en horario de oficina no deberia poder tumbar la base de datos productiva."
  type        = bool
  default     = false
}

# ============================================================================
# RDS Proxy
# ============================================================================

variable "require_tls" {
  description = "true (por defecto): RDS Proxy exige TLS en toda conexion entrante. psycopg3 (el driver que ya usa el backend) negocia TLS automaticamente via el sslmode por defecto de libpq (\"prefer\": intenta TLS primero) — no requiere ningun cambio de codigo. Ver docs/aws/RDS_PROXY_FOUNDATION.md."
  type        = bool
  default     = true
}

variable "idle_client_timeout" {
  description = "Segundos de inactividad antes de que RDS Proxy cierre una conexion de cliente ociosa. Valor por defecto de AWS — el dimensionamiento definitivo es Fase 4C.6."
  type        = number
  default     = 1800
}

variable "connection_borrow_timeout" {
  description = "Segundos que un cliente espera por una conexion disponible del pool de RDS Proxy antes de fallar. Valor inicial conservador — Fase 4C.6 lo ajustara con datos reales de load/stress testing."
  type        = number
  default     = 120
}

variable "max_connections_percent" {
  description = "Porcentaje del max_connections de la instancia RDS que RDS Proxy puede usar como maximo. Valor inicial conservador — Fase 4C.6 lo ajustara."
  type        = number
  default     = 100
}

variable "max_idle_connections_percent" {
  description = "Porcentaje del max_connections de la instancia RDS que RDS Proxy mantiene como conexiones ociosas listas para reuso. Valor inicial conservador — Fase 4C.6 lo ajustara."
  type        = number
  default     = 50
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
