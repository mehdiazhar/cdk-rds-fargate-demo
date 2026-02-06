# Observability & Security Plan

## Observability (CloudWatch + ALB logs)
- **ALB**: access logs to S3, 4xx/5xx alarms, target response time alarm.
- **ECS/Fargate**: container logs to CloudWatch, task health alarms, CPU/memory alarms.
- **RDS/Aurora**: log exports enabled (postgresql), CPU/conn/disk alarms, slow query logging via parameter group.
- **SQS**: queue depth, age of oldest message, and DLQ message count alarms.
- **Dashboards**: one shared CloudWatch dashboard with ALB, ECS, RDS, SQS widgets.

## Security (Well-Architected aligned)
- **Network isolation**: VPC with private subnets for ECS/RDS; internal ALB only.
- **Least privilege**: ECS task role scoped to required Secrets Manager + SQS actions.
- **Secrets**: DB creds in Secrets Manager, rotation enabled where applicable.
- **Encryption**: RDS encrypted at rest (AWS-managed KMS), SQS server-side encryption, S3 logs encrypted.
- **Ingress control**: ALB security group limited to VPC CIDR; no public DB access.
- **Change control**: CDK + CI/CD, no manual changes in console.
- **Auditability**: CloudTrail enabled in the account for API actions.

## Security risks & mitigations
- **Public exposure of service** -> Keep ALB internal; if public is required, add WAF, auth, and IP/rate limits.
- **Over-privileged IAM** -> Scope ECS task role to exact SQS + Secrets Manager ARNs.
- **Secret leakage** -> Store in Secrets Manager only; never in env files or CI vars.
- **Data exfiltration** -> RDS in private subnets, SGs allow only ECS SG, no public access.
- **Poison messages** -> DLQ + maxReceiveCount; alert on DLQ depth.
- **Unlogged access** -> Enable ALB access logs + CloudTrail + CloudWatch logs/alarms.
- **No HTTPS in transit** -> Add ACM cert + HTTPS listener; redirect HTTP to HTTPS.
- **Uncontrolled changes** -> CDK-only changes with CI/CD approvals; deny console changes.
