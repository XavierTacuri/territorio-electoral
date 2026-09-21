output "vpc_id" {
  description = "ID de la VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "Bloque CIDR de la VPC."
  value       = aws_vpc.this.cidr_block
}

output "availability_zones" {
  description = "Zonas de disponibilidad utilizadas, en el mismo orden que las listas de subredes."
  value       = local.azs
}

output "public_subnet_ids" {
  description = "IDs de las subredes publicas (destino futuro: ALB)."
  value       = aws_subnet.public[*].id
}

output "app_subnet_ids" {
  description = "IDs de las subredes privadas de aplicacion (destino futuro: ECS/Fargate)."
  value       = aws_subnet.app[*].id
}

output "db_subnet_ids" {
  description = "IDs de las subredes privadas de base de datos (destino futuro: RDS, RDS Proxy)."
  value       = aws_subnet.db[*].id
}

output "internet_gateway_id" {
  description = "ID del Internet Gateway."
  value       = aws_internet_gateway.this.id
}

output "nat_gateway_ids" {
  description = "IDs del/los NAT Gateway(s) creados."
  value       = aws_nat_gateway.this[*].id
}

output "public_route_table_id" {
  description = "ID de la route table publica."
  value       = aws_route_table.public.id
}

output "app_route_table_ids" {
  description = "IDs de las route tables de aplicacion (una por AZ)."
  value       = aws_route_table.app[*].id
}

output "db_route_table_id" {
  description = "ID de la route table de base de datos (sin ruta a Internet)."
  value       = aws_route_table.db.id
}

output "s3_vpc_endpoint_id" {
  description = "ID del VPC Endpoint (Gateway) hacia S3."
  value       = aws_vpc_endpoint.s3.id
}
