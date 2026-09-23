output "state_bucket_name" {
  description = "Nombre del bucket S3 de Terraform state — usar como valor de -backend-config=\"bucket=...\" en environments/prod."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "state_bucket_arn" {
  value = aws_s3_bucket.terraform_state.arn
}

output "backend_ecr_repository_url" {
  description = "URI del repositorio ECR del backend (sin tag) — usar como prefijo de var.backend_image en environments/prod."
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_ecr_repository_arn" {
  value = aws_ecr_repository.backend.arn
}

output "frontend_ecr_repository_url" {
  description = "URI del repositorio ECR del frontend (sin tag) — usar como prefijo de var.frontend_image en environments/prod."
  value       = aws_ecr_repository.frontend.repository_url
}

output "frontend_ecr_repository_arn" {
  value = aws_ecr_repository.frontend.arn
}

output "terraform_state_access_policy_arn" {
  description = "ARN de la policy de acceso minimo al state bucket (sin adjuntar a ningun role/usuario todavia — ver docs/aws/AWS_BOOTSTRAP.md, \"Modelo IAM\")."
  value       = aws_iam_policy.terraform_state_access.arn
}

output "ecr_push_policy_arn" {
  description = "ARN de la policy de push/pull de ECR (sin adjuntar a ningun role/usuario todavia)."
  value       = aws_iam_policy.ecr_push.arn
}
