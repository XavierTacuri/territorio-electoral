output "bucket_name" {
  description = "Nombre real del bucket creado — usar como var.s3_artifact_bucket en modules/ecs y como bucket_name en modules/s3_lifecycle. Nunca un string inventado: siempre el valor real devuelto por el recurso aws_s3_bucket."
  value       = aws_s3_bucket.this.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}

output "versioning_enabled" {
  description = "true si versioning esta Enabled en el bucket real (var.enable_versioning)."
  value       = var.enable_versioning
}
