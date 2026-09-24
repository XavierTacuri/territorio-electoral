# Variables minimas del bootstrap (Fase 4D.1) — ver docs/aws/AWS_BOOTSTRAP.md.
# Sin passwords, access keys ni secret keys en ningun lugar de este archivo.

variable "project" {
  description = "Nombre del proyecto. Mismo valor que environments/prod/variables.tf — un unico bootstrap sirve a todos los entornos futuros."
  type        = string
  default     = "territorio-electoral"

  validation {
    condition     = length(var.project) > 0
    error_message = "project no puede estar vacio."
  }
}

variable "environment" {
  description = "Entorno objetivo de este bootstrap. Hoy solo existe prod — no se inventan staging/dev ficticios (misma razon que environments/prod/variables.tf)."
  type        = string
  default     = "prod"

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment no puede estar vacio."
  }
}

variable "aws_region" {
  description = "Region de AWS del bootstrap. Debe ser la MISMA region que usara environments/prod (var.aws_region alli) — un certificado ACM regional y varios recursos regionales exigen coincidencia. Default us-east-2 (Ohio): region habilitada en la cuenta AWS disponible para el primer deployment real — us-east-1 (N. Virginia) exigiria activar caracteristicas avanzadas de la cuenta que no se van a activar para esta prueba. Sigue siendo una decision explicita y overridable, no silenciosa (ver docs/aws/AWS_BOOTSTRAP.md, \"AWS region\")."
  type        = string
  default     = "us-east-2"

  validation {
    condition     = length(var.aws_region) > 0
    error_message = "aws_region no puede estar vacio."
  }
}

variable "state_bucket_name" {
  description = "Nombre del bucket S3 DEDICADO a Terraform state (nunca el bucket de artifacts de la aplicacion). Debe ser globalmente unico en S3, no solo en la cuenta. Sin default: nunca se inventa un nombre de bucket real."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "state_bucket_name debe cumplir las reglas de nombre de bucket S3: 3-63 caracteres, minusculas, digitos, puntos o guiones, sin empezar/terminar en punto o guion."
  }
}

variable "backend_ecr_repository_name" {
  description = "Nombre del repositorio ECR del backend. Por defecto reutiliza name_prefix (misma convencion que environments/prod)."
  type        = string
  default     = ""

  validation {
    condition     = var.backend_ecr_repository_name == "" || can(regex("^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$", var.backend_ecr_repository_name))
    error_message = "backend_ecr_repository_name debe cumplir las reglas de nombre de repositorio ECR (minusculas, digitos, guiones, guiones bajos, puntos o barras, sin empezar/terminar en separador)."
  }
}

variable "frontend_ecr_repository_name" {
  description = "Nombre del repositorio ECR del frontend. Por defecto reutiliza name_prefix (misma convencion que environments/prod)."
  type        = string
  default     = ""

  validation {
    condition     = var.frontend_ecr_repository_name == "" || can(regex("^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$", var.frontend_ecr_repository_name))
    error_message = "frontend_ecr_repository_name debe cumplir las reglas de nombre de repositorio ECR (minusculas, digitos, guiones, guiones bajos, puntos o barras, sin empezar/terminar en separador)."
  }
}

variable "additional_tags" {
  description = "Tags adicionales especificas de este bootstrap, fusionadas con las tags comunes (Project/Environment/ManagedBy). Misma semantica que environments/prod/variables.tf."
  type        = map(string)
  default     = {}
}
