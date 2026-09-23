# ==============================================================================
# Bucket S3 DEDICADO exclusivamente a Terraform state (Fase 4D.1). Separado
# por completo del bucket de artifacts de la aplicacion, de logs de ALB/WAF
# y de cualquier almacenamiento de evidencia/reports — ver
# docs/aws/AWS_BOOTSTRAP.md, "Remote state".
#
# El backend "s3" de environments/prod referenciara este bucket via
# configuracion PARCIAL (backend "s3" {} + `-backend-config` en
# `terraform init`) — nunca con el nombre real hardcodeado en el repo. Ver
# environments/prod/versions.tf.
# ==============================================================================

resource "aws_s3_bucket" "terraform_state" {
  bucket = var.state_bucket_name

  # El state bucket es el activo mas critico de todo este proyecto en AWS:
  # destruirlo por accidente deja sin forma segura de administrar el resto
  # de la infraestructura. Eliminacion INTENCIONAL: ver
  # docs/aws/AWS_BOOTSTRAP.md, "Eliminacion controlada del state bucket".
  lifecycle {
    prevent_destroy = true
  }

  tags = merge(local.common_tags, {
    Name = var.state_bucket_name
  })
}

# Versioning: Enabled, sin expiracion agresiva de versiones antiguas (item 7)
# — permite recuperar un tfstate anterior ante overwrite/corrupcion/error
# humano. Cleanup de versiones antiguas diferido: sin decision operativa
# tomada todavia sobre una retencion maxima.
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encryption at rest: SSE-S3 (AES256) — sin crear una CMK KMS unicamente por
# complejidad (item 8). Migracion futura a SSE-KMS: ver
# docs/aws/AWS_BOOTSTRAP.md, "Encryption".
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }

    bucket_key_enabled = true
  }
}

# BucketOwnerEnforced: deshabilita ACLs por completo (ningun objeto puede
# tener una ACL propia) — el mecanismo de ownership recomendado por AWS,
# compatible con el Public Access Block de abajo.
resource "aws_s3_bucket_ownership_controls" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Public Access Block: las 4 protecciones activas (item 9). Terraform state
# contiene informacion sensible de infraestructura — nunca debe ser publico.
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Secure transport: Deny explicito si aws:SecureTransport=false (item 10).
# Sin account IDs hardcodeados — el Principal "*" ya queda acotado por el
# Resource (este bucket especifico) y la condicion (solo trafico inseguro).
data "aws_iam_policy_document" "terraform_state_secure_transport" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
    ]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = data.aws_iam_policy_document.terraform_state_secure_transport.json

  depends_on = [aws_s3_bucket_public_access_block.terraform_state]
}
