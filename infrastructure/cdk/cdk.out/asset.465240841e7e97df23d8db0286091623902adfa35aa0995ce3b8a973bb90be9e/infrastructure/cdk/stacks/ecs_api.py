from pathlib import Path
from typing import Mapping, Any

from aws_cdk import (
    RemovalPolicy,
    Stack,
    CfnOutput,
    Fn,
    IgnoreMode,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
    aws_sqs as sqs,
    aws_secretsmanager as secretsmanager,
    Tags,
)
from constructs import Construct

from stacks.lb import create_public_alb


class FlexiOrderApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: Mapping[str, Any],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        name_prefix = config["namePrefix"]

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "Vpc",
            vpc_id=config["vpcId"],
            availability_zones=config["availabilityZones"],
            public_subnet_ids=config.get("publicSubnetIds", []),
            private_subnet_ids=config.get("privateSubnetIds", []),
        )

        public_subnets = [
            ec2.Subnet.from_subnet_id(self, f"PublicSubnet{i+1}", sid)
            for i, sid in enumerate(config.get("publicSubnetIds", []))
        ]
        private_subnets = [
            ec2.Subnet.from_subnet_id(self, f"PrivateSubnet{i+1}", sid)
            for i, sid in enumerate(config.get("privateSubnetIds", []))
        ]

        cluster_arn = Fn.import_value(f"flexis-ecs-{env_name}-cluster-arn")
        cluster_name = Fn.import_value(f"flexis-ecs-{env_name}-cluster-name")
        cluster = ecs.Cluster.from_cluster_attributes(
            self,
            "Cluster",
            vpc=vpc,
            cluster_name=cluster_name,
            cluster_arn=cluster_arn,
        )

        ecs_app_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "ImportedEcsAppSg",
            security_group_id=Fn.import_value(f"flexis-sg-{env_name}-ecs-sg-id"),
            mutable=True,
        )
        alb_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "ImportedAlbSg",
            security_group_id=Fn.import_value(f"flexis-sg-{env_name}-alb-sg-id"),
            mutable=False,
        )

        db_host = Fn.import_value(f"flexis-rds-{env_name}-endpoint")
        db_port = Fn.import_value(f"flexis-rds-{env_name}-port")
        db_name = Fn.import_value(f"flexis-rds-{env_name}-dbname")
        db_secret_arn = Fn.import_value(f"flexis-rds-{env_name}-secret-arn")

        db_secret = secretsmanager.Secret.from_secret_complete_arn(
            self,
            "DbSecret",
            secret_complete_arn=db_secret_arn,
        )

        api_cfg = config.get("api", {})
        cpu = int(api_cfg.get("cpu", 256))
        memory = int(api_cfg.get("memory", 512))
        desired_count = int(api_cfg.get("desiredCount", 1))
        container_port = int(api_cfg.get("port", 8080))
        enable_exec = bool(api_cfg.get("enableExecuteCommand", False))
        enable_cb = bool(api_cfg.get("enableCircuitBreaker", True))
        cb_rollback = bool(api_cfg.get("circuitBreakerRollback", False))

        queue_arn = Fn.import_value(f"flexis-orders-{env_name}-queue-arn")
        queue_url = Fn.import_value(f"flexis-orders-{env_name}-queue-url")
        queue = sqs.Queue.from_queue_attributes(
            self,
            "OrdersQueue",
            queue_arn=queue_arn,
            queue_url=queue_url,
        )

        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        queue.grant_consume_messages(task_role)
        queue.grant_send_messages(task_role)

        execution_role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonECSTaskExecutionRolePolicy"
            )
        )
        db_secret.grant_read(execution_role)

        task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            cpu=cpu,
            memory_limit_mib=memory,
            task_role=task_role,
            execution_role=execution_role,
        )

        image_override = api_cfg.get("image")
        if image_override:
            container_image = ecs.ContainerImage.from_registry(image_override)
        else:
            app_root = Path(__file__).resolve().parents[3]
            container_image = ecs.ContainerImage.from_asset(
                directory=str(app_root),
                file="infrastructure/docker/Dockerfile",
                exclude=[
                    "**/cdk.out/**",
                    "**/.venv/**",
                    "**/__pycache__/**",
                    "**/.git/**",
                ],
                ignore_mode=IgnoreMode.GLOB,
            )

        log_group = logs.LogGroup(
            self,
            "OrdersLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        container = task_definition.add_container(
            "api",
            image=container_image,
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="orders",
                log_group=log_group,
            ),
            environment={
                "DB_HOST": db_host,
                "DB_PORT": db_port,
                "DB_NAME": db_name,
                "DB_USER": config.get("dbUser", "flexis_admin"),
                "SQS_QUEUE_URL": queue_url,
            },
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, field="password"),
            },
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=container_port)
        )

        service = ecs.FargateService(
            self,
            "OrdersService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            enable_execute_command=enable_exec,
            security_groups=[ecs_app_sg],
            vpc_subnets=ec2.SubnetSelection(subnets=private_subnets),
            deployment_circuit_breaker=ecs.DeploymentCircuitBreaker(
                enable=enable_cb,
                rollback=cb_rollback,
            ),
        )

        alb = create_public_alb(
            self,
            name_prefix=name_prefix,
            vpc=vpc,
            public_subnets=public_subnets,
            alb_sg=alb_sg,
            ecs_app_sg=ecs_app_sg,
            service=service,
            container_port=container_port,
        )

        CfnOutput(
            self,
            "AlbDns",
            value=alb.load_balancer_dns_name,
            export_name=f"flexis-orders-{env_name}-alb-dns",
        )
        Tags.of(self).add("application", "flexischools")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexischools")
