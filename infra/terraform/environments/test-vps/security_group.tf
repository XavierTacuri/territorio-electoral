# Security group unico para la EC2. A diferencia de modules/security_groups
# (4 SGs que se referencian entre si — ver nota de cabecera de ese archivo
# sobre por que ahi las reglas van en recursos separados), aqui solo existe
# un SG que no se referencia a si mismo, asi que no hay riesgo de ciclo:
# las reglas inline son seguras y mas simples para un recurso temporal.
#
# Ingress: solo TCP 80 publico. Ni 22 (sin SSH — acceso administrativo via
# SSM Session Manager, ver iam.tf), ni 5432 (Postgres), ni 8000 (backend):
# ambos quedan accesibles unicamente dentro de la red Docker interna de la
# instancia, nunca en el security group de la VPC.
resource "aws_security_group" "instance" {
  name        = "${local.name_prefix}-instance"
  description = "EC2 unica de test-vps: solo recibe HTTP publico (80); Postgres/backend quedan dentro de la red Docker, nunca en este SG."
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTP publico hacia nginx (unico punto de entrada: frontend + /api/v1 proxy)."
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = var.allowed_http_cidr_blocks
  }

  egress {
    description = "Salida HTTPS/HTTP para pull de ECR, SSM, y APIs de AWS."
    protocol    = "tcp"
    from_port   = 0
    to_port     = 65535
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-instance" })
}
