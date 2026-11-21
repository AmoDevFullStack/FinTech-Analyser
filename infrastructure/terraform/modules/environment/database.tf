resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

# Alphanumeric only: the password is embedded in DATABASE_URL, where /, @, : and # would
# need URL-encoding. 40 characters of [A-Za-z0-9] is still ~238 bits.
resource "random_password" "db" {
  length  = 40
  special = false
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = var.db_max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "fdt"
  username = "fdt"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  # Times are UTC: 01:00-02:00 and Sunday 02:30 are 03:00 and 04:30 SAST.
  backup_retention_period    = var.db_backup_retention_days
  backup_window              = "01:00-02:00"
  maintenance_window         = "sun:02:30-sun:03:30"
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${local.name}-final" : null

  # PostgreSQL 16 on RDS enforces TLS by default (rds.force_ssl = 1); DATABASE_URL asks for
  # sslmode=require to match.
  apply_immediately = false

  tags = { Name = local.name }
}
