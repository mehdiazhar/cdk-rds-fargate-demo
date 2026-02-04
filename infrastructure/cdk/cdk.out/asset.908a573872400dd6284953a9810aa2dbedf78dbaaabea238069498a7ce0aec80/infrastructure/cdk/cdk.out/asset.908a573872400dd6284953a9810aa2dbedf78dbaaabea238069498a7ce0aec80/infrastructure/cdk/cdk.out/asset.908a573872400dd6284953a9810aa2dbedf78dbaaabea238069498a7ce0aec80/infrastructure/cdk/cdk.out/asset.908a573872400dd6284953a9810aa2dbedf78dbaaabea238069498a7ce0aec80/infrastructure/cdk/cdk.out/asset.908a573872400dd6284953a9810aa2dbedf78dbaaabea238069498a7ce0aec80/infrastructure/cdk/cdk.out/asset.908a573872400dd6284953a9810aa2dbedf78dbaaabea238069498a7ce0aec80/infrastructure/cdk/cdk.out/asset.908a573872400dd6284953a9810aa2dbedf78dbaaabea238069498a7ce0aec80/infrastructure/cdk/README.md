# flexischools order processing cdk

This CDK app provisions a simple sandbox stack set for Flexischools:
- RDS Postgres instance
- ECS Fargate service + ALB
- SQS queue
- VPC (foundation)

Config is YAML-based to keep environment settings easy to edit.

## Layout

```text
flexischools/infrastructure/cdk/
  app.py
  cdk.json
  stacks/
    vpc.py
    ecs_api.py
    ecs_cluster.py
    lb.py
    rds.py
    sqs.py
    sgs.py
  config/
    development.yaml
```
