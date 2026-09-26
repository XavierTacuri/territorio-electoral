output "management_enabled" {
  description = "true si este modulo esta administrando activamente la lifecycle configuration del bucket (var.enabled=true y var.bucket_name no vacio). Ya no cubre versioning/encryption/public-access-block — ver modules/s3_artifact_bucket para el estado real de esos tres."
  value       = local.manage
}

output "lifecycle_configuration_id" {
  description = "ID de la lifecycle configuration aplicada, o cadena vacia si no se administra."
  value       = local.manage ? aws_s3_bucket_lifecycle_configuration.this[0].id : ""
}
