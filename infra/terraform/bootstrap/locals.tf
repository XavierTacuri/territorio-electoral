locals {
  name_prefix = "${var.project}-${var.environment}"

  # Fallback a name_prefix-backend/-frontend cuando no se especifica un
  # nombre de repositorio ECR explicito — misma convencion project/
  # environment/proposito que el resto del repositorio (item 24, Fase 4D.1).
  backend_ecr_repository_name  = var.backend_ecr_repository_name != "" ? var.backend_ecr_repository_name : "${local.name_prefix}-backend"
  frontend_ecr_repository_name = var.frontend_ecr_repository_name != "" ? var.frontend_ecr_repository_name : "${local.name_prefix}-frontend"

  # Mismas tres tags que environments/prod (ver ese locals.tf) — ninguna
  # tag empresarial adicional inventada para este bootstrap.
  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags,
  )
}
