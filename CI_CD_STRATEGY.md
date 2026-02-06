# CI/CD Strategy (Azure DevOps)

## Goals
- Repeatable, auditable deploys with a clear promotion path (dev -> staging -> prod).
- Immutable artifacts (image tag + CDK synth output) promoted across environments.
- Safe database migrations and least-privilege secrets access.

## Pipeline shape
1) Validate
   - Lint/unit tests
   - `cdk synth` to validate infra
2) Build
   - Build Docker image
   - Push to ECR with commit SHA tag
3) Deploy
   - `cdk deploy` with explicit image tag
   - Environment approvals for staging/prod

## Database migrations (safe)
- Run migrations as a **pre-deploy step** (one-off ECS task or Lambda).
- Only **backward-compatible** changes (add columns/tables first, avoid breaking changes).
- Use a **migration lock** to prevent concurrent runs.
- Cleanup (drop/rename) in a later release after traffic is on the new schema.

## Secrets management
- Store DB credentials and API keys in **AWS Secrets Manager**.
- ECS task role has **least-privilege** `secretsmanager:GetSecretValue` on specific ARNs.
- Pipeline uses an AWS service connection (assume-role/OIDC) instead of static keys.
- No secrets in repo, config files, or pipeline variables.

## Example Azure DevOps pipeline (simple)
```yaml
trigger:
  branches:
    include:
      - main

variables:
  AWS_REGION: ap-southeast-2
  ENV: development
  ECR_REPO: flexicx-orders
  IMAGE_TAG: $(Build.SourceVersion)
  CDK_DIR: flexicx/infrastructure/cdk

stages:
- stage: Validate
  jobs:
  - job: Synth
    pool:
      vmImage: ubuntu-latest
    steps:
    - checkout: self
    - script: |
        python -m venv .venv
        source .venv/bin/activate
        pip install -r $(CDK_DIR)/requirements.txt
        cdk synth -c env=$(ENV)
      displayName: "CDK synth"

- stage: Build
  dependsOn: Validate
  jobs:
  - job: BuildAndPush
    pool:
      vmImage: ubuntu-latest
    steps:
    - checkout: self
    - script: |
        aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
        docker build -t $(ECR_REPO):$(IMAGE_TAG) -f flexicx/infrastructure/docker/Dockerfile flexicx
        docker tag $(ECR_REPO):$(IMAGE_TAG) $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO):$(IMAGE_TAG)
        docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO):$(IMAGE_TAG)
      displayName: "Build & push image"

- stage: DeployDev
  dependsOn: Build
  jobs:
  - deployment: Deploy
    environment: dev
    pool:
      vmImage: ubuntu-latest
    strategy:
      runOnce:
        deploy:
          steps:
          - checkout: self
          - script: |
              python -m venv .venv
              source .venv/bin/activate
              pip install -r $(CDK_DIR)/requirements.txt
              cdk deploy --all -c env=$(ENV) -c api_image=$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO):$(IMAGE_TAG) --require-approval never
            displayName: "Deploy CDK"
```


Notes:
- Replace `AWS_ACCOUNT_ID` and ensure the pipeline has an AWS service connection.
- Add manual approvals for staging/prod via Azure DevOps Environments.
