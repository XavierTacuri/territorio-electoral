# Fundacion de Fase 4C.1: red (VPC, subredes public/app/db en 2+ AZ, NAT,
# VPC endpoint S3) y security groups (limites ALB -> ECS -> RDS Proxy ->
# RDS). ALB, ECS/Fargate, RDS, RDS Proxy, WAF y CloudWatch se agregan en
# subfases posteriores de Fase 4C — ver docs/aws/TERRAFORM_FOUNDATION.md.

module "network" {
  source = "../../modules/network"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  az_count           = var.az_count
  single_nat_gateway = var.single_nat_gateway
}

module "security_groups" {
  source = "../../modules/security_groups"

  name_prefix             = local.name_prefix
  vpc_id                  = module.network.vpc_id
  alb_ingress_cidr_blocks = var.alb_ingress_cidr_blocks
  backend_container_port  = var.backend_container_port
  db_port                 = var.db_port
}
