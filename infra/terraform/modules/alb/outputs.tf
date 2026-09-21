output "alb_arn" {
  description = "ARN del Application Load Balancer."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "Nombre DNS del ALB (destino de un futuro registro CNAME/ALIAS del dominio real)."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Hosted zone ID del ALB (para un futuro registro Route 53 ALIAS)."
  value       = aws_lb.this.zone_id
}

output "backend_target_group_arn" {
  description = "ARN del target group del backend, para registrar el ECS service."
  value       = aws_lb_target_group.backend.arn
}

output "frontend_target_group_arn" {
  description = "ARN del target group del frontend, para registrar el ECS service."
  value       = aws_lb_target_group.frontend.arn
}

output "http_listener_arn" {
  description = "ARN del listener HTTP :80."
  value       = aws_lb_listener.http.arn
}

output "https_listener_arn" {
  description = "ARN del listener HTTPS :443, o null si no se proveyo certificate_arn."
  value       = var.certificate_arn == "" ? null : aws_lb_listener.https[0].arn
}
