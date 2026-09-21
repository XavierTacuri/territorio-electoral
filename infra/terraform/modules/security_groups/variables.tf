variable "name_prefix" {
  description = "Prefijo para nombrar los security groups (ej. territorio-electoral-prod)."
  type        = string
}

variable "vpc_id" {
  description = "ID de la VPC donde se crean los security groups."
  type        = string
}

variable "alb_ingress_cidr_blocks" {
  description = "Bloques CIDR permitidos para llegar al ALB por HTTPS/HTTP publico. Por defecto abierto a Internet (0.0.0.0/0), apropiado para un ALB publico que en una subfase posterior quedara detras de WAF."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "backend_container_port" {
  description = "Puerto en el que escucha el contenedor de la API (EXPOSE 8000 en backend/Dockerfile; ver tambien docker-compose*.yml)."
  type        = number
  default     = 8000
}

variable "db_port" {
  description = "Puerto de PostgreSQL."
  type        = number
  default     = 5432
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
