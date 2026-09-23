# ==============================================================================
# IAM — Fase 4D.1. Este bootstrap define UNICAMENTE las dos policies cuyo
# alcance es enteramente conocido hoy (acceso al propio state bucket, push
# a los propios repositorios ECR). Deliberadamente NO define aqui:
#
#   - Un IAM Role de "Terraform deployment" sobre environments/prod (VPC,
#     ECS, RDS, WAF, CloudWatch, Secrets Manager...): sus permisos exactos
#     dependen del primer `terraform plan` real contra esos modulos, que
#     todavia no se ha ejecutado — inventar aqui un wildcard amplio (o peor,
#     AdministratorAccess/PowerUserAccess) para "resolverlo" seria exactamente
#     el atajo que esta fase prohibe. Ver docs/aws/AWS_BOOTSTRAP.md, "Modelo
#     IAM", para el modelo documentado (bootstrap identity -> deployment
#     role -> production resources) y como completarlo despues del primer
#     plan.
#   - Ningun aws_iam_openid_connect_provider/role de GitHub Actions OIDC:
#     ver docs/aws/AWS_BOOTSTRAP.md, "CI / GitHub OIDC" — documentado como
#     patron futuro, no habilitado en esta subfase.
#
# Ambas policies de abajo quedan sin adjuntar a ningun role/usuario todavia
# — se exponen como output (arn) para que el operador las adjunte a la
# identidad que corresponda cuando la decida.
# ==============================================================================

# ------------------------------------------------------------------------------
# Acceso minimo al bucket de Terraform state (item 33). Nunca s3:* sobre
# todos los buckets — unicamente GetObject/PutObject sobre el prefijo de
# state de este proyecto, y ademas DeleteObject sobre sus lockfiles
# (*.tflock, locking nativo del backend s3 con use_lockfile=true).
# ------------------------------------------------------------------------------

data "aws_iam_policy_document" "terraform_state_access" {
  statement {
    sid    = "TerraformStateList"
    effect = "Allow"

    actions = ["s3:ListBucket"]

    resources = [aws_s3_bucket.terraform_state.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.project}/*"]
    }
  }

  statement {
    sid    = "TerraformStateObjectReadWrite"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = ["${aws_s3_bucket.terraform_state.arn}/${var.project}/*"]
  }

  statement {
    sid    = "TerraformStateLockfile"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = ["${aws_s3_bucket.terraform_state.arn}/${var.project}/*.tflock"]
  }
}

resource "aws_iam_policy" "terraform_state_access" {
  name        = "${local.name_prefix}-terraform-state-access"
  description = "Acceso minimo de lectura/escritura al bucket de Terraform state (${var.state_bucket_name}, prefijo ${var.project}/*) y a sus lockfiles (*.tflock). Sin permisos sobre ningun otro recurso AWS."
  policy      = data.aws_iam_policy_document.terraform_state_access.json

  tags = local.common_tags
}

# ------------------------------------------------------------------------------
# Push/pull unicamente sobre los dos repositorios ECR de este proyecto
# (nunca sobre todos los repositorios de la cuenta). ecr:GetAuthorizationToken
# exige Resource="*" por diseño de la API de ECR (no hay ARN de recurso mas
# especifico posible para esa accion) — es el unico wildcard de este
# archivo, y esta acotado a una unica accion de autenticacion, no a acceso.
# ------------------------------------------------------------------------------

data "aws_iam_policy_document" "ecr_push" {
  statement {
    sid    = "EcrAuthToken"
    effect = "Allow"

    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPushPull"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]

    resources = [
      aws_ecr_repository.backend.arn,
      aws_ecr_repository.frontend.arn,
    ]
  }
}

resource "aws_iam_policy" "ecr_push" {
  name        = "${local.name_prefix}-ecr-push"
  description = "Push/pull de imagenes unicamente sobre los repositorios ECR de este proyecto (${local.backend_ecr_repository_name}, ${local.frontend_ecr_repository_name})."
  policy      = data.aws_iam_policy_document.ecr_push.json

  tags = local.common_tags
}
