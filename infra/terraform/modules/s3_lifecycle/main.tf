# Todos los recursos de este archivo actuan sobre var.bucket_name POR
# NOMBRE — ninguno de ellos declara ni administra un recurso aws_s3_bucket.
# Ver variables.tf ("Ownership del bucket") para el razonamiento completo y
# docs/aws/BACKUP_DR_FOUNDATION.md para la version documentada.

locals {
  # Redundante con la validation de var.enabled (que ya exige
  # bucket_configuration_managed_by_this_stack y bucket_dedicated_to_project
  # cuando enabled=true) — se repite aqui explicitamente para que ningun
  # recurso de este archivo dependa de una sola variable, ni siquiera
  # indirectamente.
  manage = (
    var.enabled &&
    var.bucket_name != "" &&
    var.bucket_configuration_managed_by_this_stack &&
    var.bucket_dedicated_to_project
  )

  # Evita que aws_s3_bucket_lifecycle_configuration reciba una "rule" sin
  # ninguna accion (AWS la rechaza): cada uno de estos dos grupos de reglas
  # combina varias acciones opcionales en un unico rule por prefijo — si
  # enable_versioning=false Y ninguna de sus acciones "current" esta
  # habilitada, la regla completa se omite via dynamic "rule" en vez de
  # crearse vacia. pending-cleanup no necesita este guard: su
  # expiration.days es incondicional.
  evidence_final_rule_active = var.evidence_final_transition_enabled || var.enable_versioning
  reports_rule_active        = var.reports_expiration_days > 0 || var.reports_transition_enabled || var.enable_versioning
}

# ============================================================================
# Versioning
# ============================================================================

resource "aws_s3_bucket_versioning" "this" {
  count = local.manage && var.enable_versioning ? 1 : 0

  bucket = var.bucket_name

  versioning_configuration {
    status = "Enabled"
  }
}

# ============================================================================
# Lifecycle
# ============================================================================
# Cada regla tiene su propio `filter { prefix = ... }` y una intencion unica
# — nunca dos reglas con filtros que se solapen de forma ambigua. Los tres
# prefijos reales (evidence/pending/, evidence/final/, reports/) tienen cada
# uno su propia regla, con su propia retencion noncurrent independiente (ver
# variables.tf sobre por que pending usa una retencion mucho mas corta que
# evidence/final y reports/). Las dos reglas bucket-wide (abort multipart,
# delete marker cleanup) son deliberadamente las UNICAS sin filtro por
# prefijo — justificado unicamente por var.bucket_dedicated_to_project.

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count = local.manage ? 1 : 0

  bucket = var.bucket_name

  # -- Pending (evidence/pending/): expiration CURRENT incondicional +
  # retencion noncurrent CORTA e independiente (ver variables.tf) --
  rule {
    id     = "pending-cleanup"
    status = "Enabled"

    filter {
      prefix = "${var.evidence_prefix}/pending/"
    }

    expiration {
      days = var.pending_expiration_days
    }

    dynamic "noncurrent_version_expiration" {
      for_each = var.enable_versioning ? [1] : []

      content {
        noncurrent_days = var.pending_noncurrent_expiration_days
      }
    }
  }

  # -- Evidencia final (evidence/final/): SIN expiration current, nunca.
  # Transicion current opcional + retencion noncurrent LARGA orientada a
  # recuperacion, independiente de pending y de reports. --
  dynamic "rule" {
    for_each = local.evidence_final_rule_active ? [1] : []

    content {
      id     = "evidence-final-lifecycle"
      status = "Enabled"

      filter {
        prefix = "${var.evidence_prefix}/final/"
      }

      dynamic "transition" {
        for_each = var.evidence_final_transition_enabled ? [1] : []

        content {
          days          = var.evidence_final_transition_days
          storage_class = var.evidence_final_transition_storage_class
        }
      }

      dynamic "noncurrent_version_transition" {
        for_each = var.enable_versioning && var.evidence_final_noncurrent_transition_enabled ? [1] : []

        content {
          noncurrent_days = var.evidence_final_noncurrent_transition_days
          storage_class   = var.evidence_final_noncurrent_transition_storage_class
        }
      }

      dynamic "noncurrent_version_expiration" {
        for_each = var.enable_versioning ? [1] : []

        content {
          noncurrent_days = var.evidence_final_noncurrent_expiration_days
        }
      }
    }
  }

  # -- Informes (reports/): expiration current OPCIONAL (deshabilitada por
  # defecto — ver variables.tf sobre el hallazgo de cleanup_generated_reports.py),
  # transicion current opcional, retencion noncurrent propia independiente
  # de evidence/pending y evidence/final. --
  dynamic "rule" {
    for_each = local.reports_rule_active ? [1] : []

    content {
      id     = "reports-lifecycle"
      status = "Enabled"

      filter {
        prefix = "${var.report_prefix}/"
      }

      dynamic "expiration" {
        for_each = var.reports_expiration_days > 0 ? [1] : []

        content {
          days = var.reports_expiration_days
        }
      }

      dynamic "transition" {
        for_each = var.reports_transition_enabled ? [1] : []

        content {
          days          = var.reports_transition_days
          storage_class = var.reports_transition_storage_class
        }
      }

      dynamic "noncurrent_version_transition" {
        for_each = var.enable_versioning && var.reports_noncurrent_transition_enabled ? [1] : []

        content {
          noncurrent_days = var.reports_noncurrent_transition_days
          storage_class   = var.reports_noncurrent_transition_storage_class
        }
      }

      dynamic "noncurrent_version_expiration" {
        for_each = var.enable_versioning ? [1] : []

        content {
          noncurrent_days = var.reports_noncurrent_expiration_days
        }
      }
    }
  }

  # -- Delete markers huerfanos: bucket-wide, solo con versioning (ver
  # variables.tf, "Alcance de multipart cleanup y delete marker cleanup") --
  dynamic "rule" {
    for_each = var.enable_versioning && var.expired_object_delete_marker_cleanup_enabled ? [1] : []

    content {
      id     = "expired-delete-marker-cleanup"
      status = "Enabled"

      filter {
        prefix = ""
      }

      expiration {
        expired_object_delete_marker = true
      }
    }
  }

  # -- Multipart incompleto: bucket-wide (misma justificacion que arriba) --
  rule {
    id     = "abort-incomplete-multipart-upload"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = var.abort_incomplete_multipart_upload_days
    }
  }
}

# ============================================================================
# Encryption por defecto (defensa en profundidad — ver variables.tf)
# ============================================================================

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  count = local.manage && var.enable_default_encryption ? 1 : 0

  bucket = var.bucket_name

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_mode
      kms_master_key_id = var.sse_mode == "aws:kms" ? var.kms_key_id : null
    }
  }
}

# ============================================================================
# Public Access Block
# ============================================================================

resource "aws_s3_bucket_public_access_block" "this" {
  count = local.manage && var.enable_public_access_block ? 1 : 0

  bucket = var.bucket_name

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
