from aws_cdk import (
    Stack,
    CfnOutput,
    Tags,
    aws_ec2 as ec2,
)
from constructs import Construct


class FlexiSecurityGroupsStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        name_prefix = config["namePrefix"]
        vpc_cidr = config.get("vpcCidr")
        if not vpc_cidr:
            raise ValueError("vpcCidr is required to restrict ALB ingress to the VPC")

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "Vpc",
            vpc_id=config["vpcId"],
            availability_zones=config["availabilityZones"],
            public_subnet_ids=config.get("publicSubnetIds", []),
            private_subnet_ids=config.get("privateSubnetIds", []),
        )

        # RDS SG
        self.rds_sg = ec2.SecurityGroup(
            self,
            "RdsSg",
            vpc=vpc,
            description="Flexicx Postgres",
            allow_all_outbound=True,
            security_group_name=f"{name_prefix}-rds-sg",
        )
        Tags.of(self.rds_sg).add("Name", f"{name_prefix}-rds-sg")

        # ECS app SG
        self.ecs_app_sg = ec2.SecurityGroup(
            self,
            "EcsAppSg",
            vpc=vpc,
            description="Flexicx ECS",
            allow_all_outbound=True,
            security_group_name=f"{name_prefix}-ecs-sg",
        )
        Tags.of(self.ecs_app_sg).add("Name", f"{name_prefix}-ecs-sg")

        # ALB SG
        self.alb_sg = ec2.SecurityGroup(
            self,
            "AlbSg",
            vpc=vpc,
            description="Flexicx ALB",
            allow_all_outbound=True,
            security_group_name=f"{name_prefix}-alb-sg",
        )
        Tags.of(self.alb_sg).add("Name", f"{name_prefix}-alb-sg")

        # Allow HTTP to ALB only from VPC CIDR
        self.alb_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc_cidr),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP to ALB from VPC CIDR",
        )

        # Allow Postgres from ECS
        self.rds_sg.add_ingress_rule(
            peer=self.ecs_app_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow Postgres from ECS",
        )

        # outputs
        CfnOutput(
            self,
            "RdsSgId",
            value=self.rds_sg.security_group_id,
            export_name=f"flexis-sg-{env_name}-rds-sg-id",
        )

        CfnOutput(
            self,
            "EcsAppSgId",
            value=self.ecs_app_sg.security_group_id,
            export_name=f"flexis-sg-{env_name}-ecs-sg-id",
        )

        CfnOutput(
            self,
            "AlbSgId",
            value=self.alb_sg.security_group_id,
            export_name=f"flexis-sg-{env_name}-alb-sg-id",
        )

        Tags.of(self).add("application", "flexicx")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexicx")
