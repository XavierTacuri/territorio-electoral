variable "name_prefix" {
  description = "Prefijo para nombrar todos los recursos del ALB (ej. territorio-electoral-prod)."
  type        = string
}

variable "vpc_id" {
  description = "ID de la VPC (modulo network de Fase 4C.1)."
  type        = string
}

variable "public_subnet_ids" {
  description = "Subredes publicas donde se coloca el ALB (modulo network de Fase 4C.1)."
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group del ALB, ya creado en Fase 4C.1 (modulo security_groups)."
  type        = string
}

variable "backend_container_port" {
  description = "Puerto del contenedor de la API (EXPOSE 8000 en backend/Dockerfile)."
  type        = number
}

variable "frontend_container_port" {
  description = "Puerto del contenedor del frontend (EXPOSE 8080 en frontend/Dockerfile)."
  type        = number
}

variable "certificate_arn" {
  description = "ARN de un certificado ACM ya emitido. Vacio (por defecto): solo se crea el listener HTTP, sin redirigir. No se crea ni se inventa ningun certificado ni dominio en este modulo — ver docs/aws/ECS_ALB_FOUNDATION.md."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
