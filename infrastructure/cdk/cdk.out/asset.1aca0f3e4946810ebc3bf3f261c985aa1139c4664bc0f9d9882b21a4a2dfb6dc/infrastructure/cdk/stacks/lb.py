from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
)
from typing import Sequence

from constructs import Construct


def create_public_alb(
    scope: Construct,
    *,
    name_prefix: str,
    vpc: ec2.IVpc,
    public_subnets: Sequence[ec2.ISubnet],
    alb_sg: ec2.ISecurityGroup,
    ecs_app_sg: ec2.ISecurityGroup,
    service: ecs.FargateService,
    container_port: int,
) -> elbv2.ApplicationLoadBalancer:
    alb = elbv2.ApplicationLoadBalancer(
        scope,
        "OrdersAlb",
        vpc=vpc,
        internet_facing=True,
        load_balancer_name=f"{name_prefix}-alb",
        security_group=alb_sg,
        vpc_subnets=ec2.SubnetSelection(subnets=public_subnets),
    )

    listener = alb.add_listener(
        "HttpListener",
        port=80,
        open=False,
    )

    target_group = elbv2.ApplicationTargetGroup(
        scope,
        "OrdersTargetGroup",
        vpc=vpc,
        target_group_name=f"{name_prefix}-tg",
        port=container_port,
        protocol=elbv2.ApplicationProtocol.HTTP,
        target_type=elbv2.TargetType.IP,
        health_check=elbv2.HealthCheck(
            path="/health",
            healthy_http_codes="200",
        ),
    )

    target_group.add_target(
        service.load_balancer_target(
            container_name="api",
            container_port=container_port,
        )
    )

    listener.add_target_groups(
        "OrdersTargetGroups",
        target_groups=[target_group],
    )

    ecs_app_sg.add_ingress_rule(
        peer=alb_sg,
        connection=ec2.Port.tcp(container_port),
        description="Allow ALB to reach ECS service",
    )

    return alb
