output "management_enabled" {
  description = "true si este modulo esta administrando activamente la configuracion del bucket (var.enabled=true y var.bucket_name no vacio)."
  value       = local.manage
}

output "versioning_enabled" {
  value = local.manage && var.enable_versioning
}

output "lifecycle_configuration_id" {
  description = "ID de la lifecycle configuration aplicada, o cadena vacia si no se administra."
  value       = local.manage ? aws_s3_bucket_lifecycle_configuration.this[0].id : ""
}
