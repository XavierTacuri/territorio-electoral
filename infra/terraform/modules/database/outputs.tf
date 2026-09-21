output "db_instance_id" {
  description = "Identificador de la instancia RDS."
  value       = aws_db_instance.this.id
}

output "db_endpoint" {
  description = "Endpoint DIRECTO de RDS (host:port) — uso administrativo unicamente. La aplicacion (backend/migration task) debe usar proxy_endpoint, nunca este valor directamente, para no saltarse el pooling de RDS Proxy."
  value       = aws_db_instance.this.endpoint
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "db_username" {
  description = "Usuario MAESTRO (no sensible por si solo, sin la contrasenia) — reservado para bootstrap/migraciones, nunca usado por el ECS backend en runtime. La contrasenia nunca se expone como output — ver master_user_secret_arn."
  value       = aws_db_instance.this.username
}

output "master_user_secret_arn" {
  description = "ARN del secreto de Secrets Manager (gestionado por RDS, no por Terraform) con la contrasenia del usuario MAESTRO. Solo lo consumen las tasks de bootstrap y migracion — nunca el ECS Service del backend. Referenciar como \"<este-arn>:password::\" en la seccion `secrets` de una ECS Task Definition — nunca leer/mostrar su contenido aqui."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "db_app_username" {
  description = "Usuario de APLICACION (no sensible por si solo) — el que usa el ECS Service del backend en runtime. La contrasenia nunca se expone como output — ver app_user_secret_arn."
  value       = var.db_app_username
}

output "app_user_secret_arn" {
  description = "ARN del secreto de Secrets Manager (creado por este Terraform) con la contrasenia del usuario de APLICACION. Lo consume el ECS Service del backend en runtime. Referenciar como \"<este-arn>:password::\" en la seccion `secrets` de una ECS Task Definition — nunca leer/mostrar su contenido aqui."
  value       = aws_secretsmanager_secret.app_user.arn
}

output "proxy_endpoint" {
  description = "Endpoint de RDS Proxy — este es el host que debe usar la aplicacion (POSTGRES_HOST del backend, la migration task y la bootstrap task). RDS Proxy identifica que credencial (maestra o de aplicacion) se esta usando por el username de cada conexion."
  value       = aws_db_proxy.this.endpoint
}

output "proxy_arn" {
  value = aws_db_proxy.this.arn
}

output "proxy_role_arn" {
  description = "ARN del IAM Role que usa RDS Proxy para leer los secretos maestro y de aplicacion."
  value       = aws_iam_role.proxy.arn
}
