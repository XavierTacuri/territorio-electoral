variable "name_prefix" {
  description = "Prefijo para nombrar los secretos (ej. territorio-electoral-prod)."
  type        = string
}

variable "secret_version" {
  description = "Disparador de rotacion de TODOS los secretos de este modulo (mismo patron que db_app_secret_version en modules/database): incrementar + `terraform apply` reescribe los 4 valores con nuevos aleatorios. Terraform no puede comparar un valor write-only anterior contra uno nuevo — por eso el disparador es este numero, no el contenido. Rotacion manual, no automatizada en esta fase."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada secreto, ademas de los default_tags del provider."
  type        = map(string)
  default     = {}
}
