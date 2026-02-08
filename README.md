# Flexicx Order Processing (Sandbox)

This folder contains a minimal order-processing demo (Flask) plus a Python CDK app that provisions:
- RDS Postgres (single instance)
- SQS queue
- ECS Fargate service
- Application Load Balancer

## Layout

```
flexicx/
  app.py
  requirements.txt
  infrastructure/
    docker/
      Dockerfile
      docker-compose.yml
    cdk/
      app.py
      cdk.json
      config/
      stacks/
```

## Deploy (CDK)

1. Update the VPC settings in `flexicx/infrastructure/cdk/config/development.yaml` (CIDR, AZs, NAT, subnet masks).
2. Install dependencies:
   ```sh
   cd flexicx/infrastructure/cdk
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Bootstrap the sandbox account (first time only):
   ```sh
   cdk bootstrap aws://12345678610/ap-southeast-2
   ```
4. Deploy:
   ```sh
   cdk deploy -c env=development
   ```

Optional: override the container image instead of building locally:
```sh
cdk deploy -c env=development -c api_image=public.ecr.aws/your/image:tag
```

## Local run

```sh
cd flexicx
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Or with Docker:
```sh
cd flexicx/infrastructure/docker
docker compose up --build
```

## Notes

- The ALB DNS name and SQS queue URL are printed as stack outputs after deployment.
- RDS credentials are stored in Secrets Manager and injected into the ECS task.
