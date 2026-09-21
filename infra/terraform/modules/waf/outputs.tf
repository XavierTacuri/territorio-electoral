output "web_acl_arn" {
  description = "ARN del Web ACL."
  value       = aws_wafv2_web_acl.this.arn
}

output "web_acl_id" {
  description = "ID del Web ACL."
  value       = aws_wafv2_web_acl.this.id
}

output "web_acl_name" {
  value = aws_wafv2_web_acl.this.name
}

output "association_id" {
  description = "ID de la asociacion Web ACL <-> ALB."
  value       = aws_wafv2_web_acl_association.this.id
}

output "log_group_name" {
  description = "Nombre del log group de WAF, o null si waf_logging_enabled=false."
  value       = var.waf_logging_enabled ? aws_cloudwatch_log_group.waf[0].name : null
}
