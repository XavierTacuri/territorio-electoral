variable "name_prefix" {
  description = "Prefijo para nombrar todos los recursos de red (ej. territorio-electoral-prod)."
  type        = string
}

variable "vpc_cidr" {
  description = "Bloque CIDR de la VPC. Debe ser lo bastante grande para 3 niveles de subred x N zonas de disponibilidad (cada subred se deriva como /24 dentro de este bloque)."
  type        = string
}

variable "az_count" {
  description = "Numero de zonas de disponibilidad a utilizar. RDS Multi-AZ, el ALB y ECS/Fargate requieren un minimo de dos."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2
    error_message = "az_count debe ser al menos 2: RDS Multi-AZ, ALB y ECS requieren un minimo de dos zonas de disponibilidad."
  }

  validation {
    # Los indices de cidrsubnet() en main.tf reservan 0-9 para public,
    # 10-19 para app y 20-29 para db. Un az_count > 10 haria que el indice
    # de una subred app/db coincida con el de una subred public y produzca
    # CIDRs solapados.
    condition     = var.az_count <= 10
    error_message = "az_count debe ser 10 o menos: los rangos de subred de este modulo (public/app/db) se solapan por encima de ese valor. Ver modules/network/main.tf."
  }
}

variable "single_nat_gateway" {
  description = "true: un unico NAT Gateway compartido por todas las subredes privadas de aplicacion (menor costo fijo, pero punto unico de fallo de salida a Internet si esa AZ tiene un problema). false: un NAT Gateway por zona de disponibilidad (alta disponibilidad, costo proporcional al numero de AZs). Ver docs/aws/TERRAFORM_FOUNDATION.md, seccion de costos."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags adicionales a fusionar en cada recurso, ademas de los default_tags configurados en el provider."
  type        = map(string)
  default     = {}
}
