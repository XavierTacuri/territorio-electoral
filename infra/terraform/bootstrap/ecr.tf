# ==============================================================================
# ECR — repositorios separados para backend y frontend (Fase 4D.1). Ninguno
# usa "latest" como estrategia de deployment: los ECS Task Definitions
# (environments/prod) consumen repository_url:commit_sha o un digest —
# ver docs/aws/ECS_ALB_FOUNDATION.md, "Estrategia de imagenes".
# ==============================================================================

resource "aws_ecr_repository" "backend" {
  name                 = local.backend_ecr_repository_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.common_tags, {
    Name = local.backend_ecr_repository_name
  })
}

resource "aws_ecr_repository" "frontend" {
  name                 = local.frontend_ecr_repository_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.common_tags, {
    Name = local.frontend_ecr_repository_name
  })
}

# Lifecycle policy: DIFERIDA deliberadamente (item 19). Sin decision
# operativa todavia sobre cuantas imagenes/dias de ventana de rollback
# preservar — una lifecycle policy escrita sin esa evidencia arriesga borrar
# una imagen todavia necesaria para rollback. Ver docs/aws/AWS_BOOTSTRAP.md,
# "ECR lifecycle".
