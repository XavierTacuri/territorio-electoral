locals {
  name_prefix = "${var.project}-${var.environment}"

  # Tags comunes que todo recurso hereda via default_tags del provider AWS
  # (ver providers.tf) — item 11 de Fase 4C.1. Los modulos anaden ademas un
  # tag Name especifico por recurso.
  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags,
  )
}
