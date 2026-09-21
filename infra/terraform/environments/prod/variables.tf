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
  description = "Region de AWS donde se despliega la infraestructura."
  type        = string
  default     = "us-east-1"
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
