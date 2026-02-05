from typing import Mapping, Any

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    Fn,
    Tags,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3 as s3,
)
from constructs import Construct


class FlexiAlbStack(Stack):
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
        suffix = self.node.addr[:8]

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "Vpc",
            vpc_id=config["vpcId"],
            availability_zones=config["availabilityZones"],
            private_subnet_ids=config.get("privateSubnetIds", []),
        )

        private_subnets = [
            ec2.Subnet.from_subnet_id(self, f"PrivateSubnet{i+1}", sid)
            for i, sid in enumerate(config.get("privateSubnetIds", []))
        ]

        alb_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "AlbSg",
            security_group_id=Fn.import_value(f"flexis-sg-{env_name}-alb-sg-id"),
            mutable=False,
        )

        ecs_app_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "EcsAppSg",
            security_group_id=Fn.import_value(f"flexis-sg-{env_name}-ecs-sg-id"),
            mutable=True,
        )

        logs_bucket = s3.Bucket(
            self,
            "AlbLogsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(30),
                )
            ],
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "OrdersAlb",
            vpc=vpc,
            internet_facing=False,
            load_balancer_name=f"{name_prefix}-alb-{suffix}",
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnets=private_subnets),
        )

        alb.log_access_logs(logs_bucket)

        listener = alb.add_listener(
            "HttpListener",
            port=80,
            open=False,
        )

        target_group = elbv2.ApplicationTargetGroup(
            self,
            "OrdersTargetGroup",
            vpc=vpc,
            target_group_name=f"{name_prefix}-tg-{suffix}",
            port=int(config.get("api", {}).get("port", 8080)),
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200",
            ),
        )

        listener.add_target_groups(
            "OrdersTargetGroups",
            target_groups=[target_group],
        )

        ecs_app_sg.add_ingress_rule(
            peer=alb_sg,
            connection=ec2.Port.tcp(int(config.get("api", {}).get("port", 8080))),
            description="Allow ALB to reach ECS service",
        )

        CfnOutput(
            self,
            "AlbDns",
            value=alb.load_balancer_dns_name,
            export_name=f"flexis-orders-{env_name}-alb-dns",
        )
        CfnOutput(
            self,
            "TargetGroupArn",
            value=target_group.target_group_arn,
            export_name=f"flexis-orders-{env_name}-tg-arn",
        )

        Tags.of(self).add("application", "flexicx")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexicx")
