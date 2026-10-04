# Rol de instancia minimo: SSM Session Manager (acceso administrativo sin
# SSH/puerto 22) + pull de solo lectura sobre los dos repositorios ECR
# existentes (backend/frontend de prod, ver data.tf). Ningun permiso de
# escritura ECR, ningun permiso fuera de estos dos propositos.

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${local.name_prefix}-instance-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# ecr:GetAuthorizationToken no admite restriccion por recurso (la API de ECR
# lo exige sobre "*") — el pull real de capas/imagenes si queda acotado a
# los dos repositorios exactos mas abajo.
data "aws_iam_policy_document" "ecr_read_only" {
  statement {
    sid       = "EcrAuthToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPullBackendFrontendOnly"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [
      data.aws_ecr_repository.backend.arn,
      data.aws_ecr_repository.frontend.arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecr_read_only" {
  name   = "${local.name_prefix}-ecr-read-only"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.ecr_read_only.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.name_prefix}-instance-profile"
  role = aws_iam_role.instance.name
}
