output "vpc_id" {
  description = "The ID of the VPC"
  value       = module.vpc.vpc_id
}

output "security_group" {
  description = "The security group for the service"
  value       = aws_security_group.this.id
}

output "cluster_id" {
  description = "The ECS Cluster ID"
  value       = aws_ecs_cluster.this.id
}

output "dns" {
  description = "The DNS address for the load balancer"
  value       = aws_lb.this.dns_name
}

output "registry" {
  description = "The ECR registry"
  value       = aws_ecr_repository.this.repository_url
}
