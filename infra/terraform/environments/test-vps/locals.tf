locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags,
  )

  backend_image  = "${data.aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
  frontend_image = "${data.aws_ecr_repository.frontend.repository_url}:${var.frontend_image_tag}"

  # Host del registro ECR (sin repo/tag) — necesario para `docker login`
  # dentro de start.sh. Mismo valor para backend y frontend: un unico
  # registro por cuenta/region, solo el nombre del repositorio difiere.
  ecr_registry_host = split("/", data.aws_ecr_repository.backend.repository_url)[0]
}
