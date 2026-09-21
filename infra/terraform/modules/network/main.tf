data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_region" "current" {}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # 3 niveles (public / app / db) x N AZs, derivados de un unico CIDR base
  # como /24 cada uno, para evitar solapamientos manuales entre subredes.
  public_subnet_cidrs = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
  app_subnet_cidrs    = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 10)]
  db_subnet_cidrs     = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 20)]

  nat_gateway_count = var.single_nat_gateway ? 1 : var.az_count
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

# --- Subredes ----------------------------------------------------------------
# public: destino futuro del ALB.
# app: destino futuro de las tasks ECS/Fargate. Sin IP publica, salida via NAT.
# db: destino futuro de RDS / RDS Proxy. Sin ruta a Internet en ninguna direccion.

resource "aws_subnet" "public" {
  count = var.az_count

  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_subnet_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-public-${local.azs[count.index]}"
    Tier = "public"
  })
}

resource "aws_subnet" "app" {
  count = var.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = local.app_subnet_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-app-${local.azs[count.index]}"
    Tier = "application-private"
  })
}

resource "aws_subnet" "db" {
  count = var.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = local.db_subnet_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-${local.azs[count.index]}"
    Tier = "database-private"
  })
}

# --- NAT ----------------------------------------------------------------------

resource "aws_eip" "nat" {
  count = local.nat_gateway_count

  domain = "vpc"

  tags = merge(var.tags, { Name = "${var.name_prefix}-nat-eip-${count.index}" })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count = local.nat_gateway_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = merge(var.tags, { Name = "${var.name_prefix}-nat-${count.index}" })

  depends_on = [aws_internet_gateway.this]
}

# --- Routing: publico -----------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-public-rt" })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = var.az_count

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- Routing: aplicacion (privada, salida via NAT) -------------------------
# Una route table por AZ para que, con single_nat_gateway = false, cada AZ
# salga por su propio NAT (evita trafico cross-AZ innecesario). Con
# single_nat_gateway = true, todas apuntan al mismo NAT Gateway.

resource "aws_route_table" "app" {
  count = var.az_count

  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-app-rt-${local.azs[count.index]}" })
}

resource "aws_route" "app_nat" {
  count = var.az_count

  route_table_id         = aws_route_table.app[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = var.single_nat_gateway ? aws_nat_gateway.this[0].id : aws_nat_gateway.this[count.index].id
}

resource "aws_route_table_association" "app" {
  count = var.az_count

  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.app[count.index].id
}

# --- Routing: base de datos (privada, sin salida a Internet) ---------------
# Sin ruta 0.0.0.0/0: la unica ruta presente es la "local" que AWS agrega
# automaticamente a toda route table para el CIDR de la VPC, suficiente para
# que RDS/RDS Proxy sean alcanzables desde la capa de aplicacion sin exponer
# ninguna salida a Internet.

resource "aws_route_table" "db" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-rt" })
}

resource "aws_route_table_association" "db" {
  count = var.az_count

  subnet_id      = aws_subnet.db[count.index].id
  route_table_id = aws_route_table.db.id
}

# --- VPC Endpoint hacia S3 --------------------------------------------------
# Trafico ECS/Fargate -> S3 (evidencia, actas, informes - ver
# docs/aws/PRODUCTION_ARCHITECTURE.md) permanece dentro de la red de AWS en
# vez de salir por el NAT Gateway. Un Gateway Endpoint no tiene costo por
# hora ni por GB propio (a diferencia de un Interface Endpoint), y ademas
# reduce el trafico facturable del NAT Gateway.

resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.this.id
  service_name = "com.amazonaws.${data.aws_region.current.name}.s3"

  route_table_ids = concat(
    aws_route_table.app[*].id,
    [aws_route_table.db.id],
  )

  tags = merge(var.tags, { Name = "${var.name_prefix}-s3-endpoint" })
}
