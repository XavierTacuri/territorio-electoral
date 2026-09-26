output "secret_arns" {
  description = "Mapa nombre-de-variable-de-entorno -> ARN de Secrets Manager, con la MISMA forma que espera module.ecs.secrets_manager_secret_arns — listo para pasar directo o fusionar (merge) con overrides manuales del operador. El ARN en si no es sensible; el contenido del secreto nunca se expone aqui."
  value       = { for name, secret in aws_secretsmanager_secret.this : name => secret.arn }
}
