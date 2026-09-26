# ==============================================================================
# Bucket S3 DEDICADO exclusivamente a artifacts de aplicacion (evidencia de
# actas, informes generados) — separado por completo del bucket de Terraform
# state (infra/terraform/bootstrap/state_bucket.tf), de logs de ALB/WAF y de
# cualquier snapshot/backup de RDS. Ver docs/aws/BACKUP_DR_FOUNDATION.md,
# "Ownership del bucket de artifacts" (seccion 2-3, separacion de
# responsabilidades) y seccion 4 (por que este modulo ahora SI declara
# aws_s3_bucket, a diferencia del diseno anterior).
#
# Mismo patron ya aprobado y en uso para el state bucket
# (infra/terraform/bootstrap/state_bucket.tf) — bucket + ownership controls
# BucketOwnerEnforced + versioning + encryption + public access block 4/4 +
# bucket policy SecureTransport, sin account IDs hardcodeados.
# ==============================================================================

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  # Igual que el state bucket: destruir por accidente el bucket de evidencia
  # de actas/informes es inaceptable en produccion. Eliminacion INTENCIONAL:
  # comentar/eliminar este bloque, exactamente el mismo procedimiento
  # documentado para el state bucket (docs/aws/AWS_BOOTSTRAP.md, "Eliminacion
  # controlada del state bucket").
  lifecycle {
    prevent_destroy = true
  }

  tags = merge(var.tags, {
    Name = var.bucket_name
  })
}

# BucketOwnerEnforced: deshabilita ACLs por completo (ningun objeto puede
# tener una ACL propia) — mecanismo de ownership recomendado por AWS,
# compatible con el Public Access Block de abajo. La aplicacion nunca usa
# ACLs (S3ArtifactStorage sube via put_object/presigned POST autenticados,
# nunca con x-amz-acl) — verificado en backend/app/services/artifact_storage.py.
resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Versioning: protege evidencia/informes de overwrite o delete accidental.
# modules/s3_lifecycle usa el mismo valor (pasado como su propio
# enable_versioning) para decidir si sus reglas de lifecycle incluyen
# noncurrent_version_* — este recurso es la UNICA fuente que realmente
# habilita/deshabilita versioning en el bucket.
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

# Encryption por defecto — la aplicacion ya envia su propio header de
# encryption en cada put_object/presigned POST (S3ArtifactStorage._encryption_args,
# ver backend/app/services/artifact_storage.py), esto es defensa en
# profundidad para cualquier objeto escrito sin ese header (ej. subida manual
# via consola/CLI).
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_mode
      kms_master_key_id = var.sse_mode == "aws:kms" ? var.kms_key_id : null
    }
  }
}

# Public Access Block: las 4 protecciones SIEMPRE activas, sin variable de
# interruptor — el bucket de artifacts nunca debe ser publico bajo ninguna
# circunstancia. Los uploads/downloads directos usan URLs firmadas
# (S3ArtifactStorage.download/presign_upload), nunca ACLs ni policies
# publicas.
resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Secure transport: Deny explicito si aws:SecureTransport=false. Sin account
# IDs hardcodeados — el Principal "*" ya queda acotado por el Resource (este
# bucket especifico) y la condicion (solo trafico inseguro). Antes (Fase
# 4C.5) esto NO se implementaba porque el bucket era externo y una bucket
# policy administrada por Terraform habria podido sobrescribir silenciosamente
# la policy real del propietario — ahora que este modulo posee el bucket
# (aws_s3_bucket.this arriba), esa razon ya no aplica. Mismo patron exacto
# que aws_s3_bucket_policy.terraform_state en infra/terraform/bootstrap/state_bucket.tf.
data "aws_iam_policy_document" "secure_transport" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.this.arn,
      "${aws_s3_bucket.this.arn}/*",
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

resource "aws_s3_bucket_policy" "secure_transport" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.secure_transport.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}
