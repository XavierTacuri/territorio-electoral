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

output "alb_arn_suffix" {
  description = "Sufijo de ARN del ALB (ej. app/<nombre>/<id>) — formato que exige la dimension LoadBalancer de las metricas CloudWatch AWS/ApplicationELB, distinto del ARN completo (Fase 4C.4)."
  value       = aws_lb.this.arn_suffix
}

output "backend_target_group_arn" {
  description = "ARN del target group del backend, para registrar el ECS service."
  value       = aws_lb_target_group.backend.arn
}

output "backend_target_group_arn_suffix" {
  description = "Sufijo de ARN del target group del backend — formato que exige la dimension TargetGroup de CloudWatch (Fase 4C.4)."
  value       = aws_lb_target_group.backend.arn_suffix
}

output "frontend_target_group_arn" {
  description = "ARN del target group del frontend, para registrar el ECS service."
  value       = aws_lb_target_group.frontend.arn
}

output "frontend_target_group_arn_suffix" {
  description = "Sufijo de ARN del target group del frontend — formato que exige la dimension TargetGroup de CloudWatch (Fase 4C.4)."
  value       = aws_lb_target_group.frontend.arn_suffix
}

output "http_listener_arn" {
  description = "ARN del listener HTTP :80."
  value       = aws_lb_listener.http.arn
}

output "https_listener_arn" {
  description = "ARN del listener HTTPS :443, o null si no se proveyo certificate_arn."
  value       = var.certificate_arn == "" ? null : aws_lb_listener.https[0].arn
}
