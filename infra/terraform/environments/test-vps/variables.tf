# Variables del entorno temporal test-vps (EC2 unica + Docker Compose).
# Entorno completamente separado de environments/prod — ver README.md de
# este directorio. Ningun secreto viaja por aqui: los secretos de la
# aplicacion (POSTGRES_PASSWORD, SECRET_KEY, etc.) se generan localmente en
# la propia EC2 en su primer arranque (ver user_data.sh.tpl), nunca via
# variables Terraform ni Secrets Manager.

variable "project" {
  description = "Nombre del proyecto. Mismo valor que environments/prod — un unico nombre de proyecto para todos los entornos."
  type        = string
  default     = "territorio-electoral"
}

variable "environment" {
  description = "Nombre de este entorno. Fijo en test-vps: identifica el proposito (prueba temporal tipo VPS) y lo separa de prod en tags/nombres de recursos."
  type        = string
  default     = "test-vps"

  validation {
    condition     = var.environment == "test-vps"
    error_message = "Este stack es exclusivamente para el entorno test-vps — no reutilizar para otro proposito sin revisar antes el README."
  }
}

variable "aws_region" {
  description = "Region de AWS. Debe coincidir con infra/terraform/bootstrap (mismos repositorios ECR, mismo bucket de state) — ver docs/aws/AWS_BOOTSTRAP.md."
  type        = string
  default     = "us-east-2"
}

variable "vpc_cidr" {
  description = "Bloque CIDR de la VPC de test-vps. Distinto del CIDR de environments/prod (10.20.0.0/16) para evitar cualquier ambiguedad entre ambos entornos, aunque nunca se peerean."
  type        = string
  default     = "10.30.0.0/16"
}

variable "allowed_http_cidr_blocks" {
  description = "Bloques CIDR permitidos hacia el puerto 80 publico. Por defecto Internet (0.0.0.0/0) — no hay WAF en esta fase de prueba."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "backend_ecr_repository_name" {
  description = "Nombre del repositorio ECR del backend YA EXISTENTE (creado por infra/terraform/bootstrap, ver terraform.tfvars de ese stack). test-vps solo LEE este repositorio — nunca lo crea ni le hace push."
  type        = string
  default     = "territorio-electoral-backend"
}

variable "frontend_ecr_repository_name" {
  description = "Nombre del repositorio ECR del frontend YA EXISTENTE (creado por infra/terraform/bootstrap, ver terraform.tfvars de ese stack). test-vps solo LEE este repositorio — nunca lo crea ni le hace push."
  type        = string
  default     = "territorio-electoral-frontend"
}

variable "backend_image_tag" {
  description = "Tag INMUTABLE de la imagen backend segura conocida a desplegar (verificar antes de aplicar que el tag sigue existiendo en ECR)."
  type        = string
  default     = "c53992c385f780f8172aefea0d3fe2b36ca466ac-amd64-sec1"
}

variable "frontend_image_tag" {
  description = "Tag INMUTABLE de la imagen frontend segura conocida a desplegar (verificar antes de aplicar que el tag sigue existiendo en ECR)."
  type        = string
  default     = "8a79e844183f1d6a6be0d44e29ccc24b2e94d566-amd64-sec3"
}

variable "instance_type" {
  description = "Tipo de instancia EC2. t3.small por defecto — cualquier valor mayor requiere justificacion explicita antes de aplicarse (ver reglas duras de la fase)."
  type        = string
  default     = "t3.small"
}

variable "root_volume_size_gb" {
  description = "Tamano del volumen raiz EBS (gp3) en GiB."
  type        = number
  default     = 20
}

variable "compose_version" {
  description = "Version fijada del binario Docker Compose (plugin CLI) instalado en el primer arranque — nunca 'latest', para que el arranque sea reproducible."
  type        = string
  default     = "v2.29.7"
}

variable "additional_tags" {
  description = "Tags adicionales especificas de este entorno, fusionadas con las tags comunes (Project/Environment/ManagedBy)."
  type        = map(string)
  default     = {}
}
