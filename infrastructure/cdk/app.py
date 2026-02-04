#!/usr/bin/env python3

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import Environment, Tags
import yaml

from stacks.vpc import FlexiVpcStack
from stacks.sgs import FlexiSecurityGroupsStack
from stacks.rds import FlexiPostgresStack
from stacks.ecs_cluster import FlexiEcsClusterStack
from stacks.sqs import FlexiSqsStack
from stacks.ecs_api import FlexiOrderApiStack


app = cdk.App()

# env comes from: -c env=development|staging|production
env_name = app.node.try_get_context("env")
if not env_name:
    raise ValueError("missing context value: -c env=development|staging|production")

base_dir = Path(__file__).parent
config_path = base_dir / "config" / f"{env_name}.yaml"

if not config_path.exists():
    raise FileNotFoundError(f"config file not found for env '{env_name}': {config_path}")

with config_path.open() as f:
    config = yaml.safe_load(f)

required_keys = [
    "account",
    "region",
    "namePrefix",
    "vpcCidr",
]
missing = [k for k in required_keys if k not in config]
if missing:
    raise ValueError(f"missing required config keys in {config_path}: {missing}")

env = Environment(
    account=config["account"],
    region=config["region"],
)

# VPC stack (foundation)
vpc_stack = FlexiVpcStack(
    app,
    f"flexis-vpc-{env_name}",
    env_name=env_name,
    config=config,
    env=env,
)
config["vpcId"] = vpc_stack.vpc.vpc_id
config["publicSubnetIds"] = [s.subnet_id for s in vpc_stack.public_subnets]
config["privateSubnetIds"] = [s.subnet_id for s in vpc_stack.private_subnets]
config["availabilityZones"] = vpc_stack.vpc.availability_zones

# security groups stack (foundation)
sgs_stack = FlexiSecurityGroupsStack(
    app,
    f"flexis-sgs-{env_name}",
    env_name=env_name,
    config=config,
    env=env,
)

# RDS stack (foundation)
rds_stack = FlexiPostgresStack(
    app,
    f"flexis-rds-{env_name}",
    env_name=env_name,
    config=config,
    env=env,
)

# ECS cluster stack (foundation)
ecs_cluster_stack = FlexiEcsClusterStack(
    app,
    f"flexis-ecs-cluster-{env_name}",
    env_name=env_name,
    config=config,
    env=env,
)

# SQS stack (foundation)
sqs_stack = FlexiSqsStack(
    app,
    f"flexis-sqs-{env_name}",
    env_name=env_name,
    config=config,
    env=env,
)

# ECS service stack
api_image = app.node.try_get_context("api_image")
if api_image:
    if "api" not in config or config["api"] is None:
        config["api"] = {}
    config["api"]["image"] = api_image

api_stack = FlexiOrderApiStack(
    app,
    f"flexis-orders-{env_name}",
    env_name=env_name,
    config=config,
    env=env,
)

api_stack.add_dependency(sgs_stack)
api_stack.add_dependency(rds_stack)
api_stack.add_dependency(ecs_cluster_stack)
api_stack.add_dependency(sqs_stack)

sgs_stack.add_dependency(vpc_stack)
rds_stack.add_dependency(vpc_stack)
rds_stack.add_dependency(sgs_stack)
ecs_cluster_stack.add_dependency(vpc_stack)
sqs_stack.add_dependency(vpc_stack)
api_stack.add_dependency(vpc_stack)

# app-level tags (single source of truth)
Tags.of(app).add("application", "flexischools")
Tags.of(app).add("product", "flexischools")
Tags.of(app).add("environment", env_name)
Tags.of(app).add("owner", "devops@flexischools.com")

app.synth()
