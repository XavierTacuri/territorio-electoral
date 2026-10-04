# Datos de solo lectura: ningun recurso de aqui crea ni modifica nada fuera
# de este stack. En particular, los dos repositorios ECR son propiedad de
# infra/terraform/bootstrap — este stack unicamente los referencia por
# nombre para construir la URI de imagen y los ARNs que necesita la policy
# IAM de solo lectura (ver iam.tf).

data "aws_ecr_repository" "backend" {
  name = var.backend_ecr_repository_name
}

data "aws_ecr_repository" "frontend" {
  name = var.frontend_ecr_repository_name
}

data "aws_availability_zones" "available" {
  state = "available"
}

# AMI Amazon Linux 2023, x86_64 — resuelta via el parametro publico de SSM
# que AWS mantiene siempre apuntando a la ultima AMI AL2023 valida de esa
# arquitectura, en vez de fijar un AMI ID que AWS puede desregistrar con el
# tiempo. Reproducible EN EL MOMENTO de cada plan/apply (Terraform resuelve
# el valor una sola vez por operacion), que es lo que pide la regla "fijar
# una version estable" del arranque (item 9 de la fase) para Docker/Compose
# -- no aplica al AMI, cuyo ciclo de vida lo gestiona AWS, no este stack.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
