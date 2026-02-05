from typing import Mapping, Any

from aws_cdk import (
    Stack,
    CfnOutput,
    Tags,
    aws_ec2 as ec2,
)
from constructs import Construct


class FlexiVpcStack(Stack):
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
        vpc_cidr = config.get("vpcCidr", "10.20.0.0/16")
        max_azs = int(config.get("maxAzs", 2))
        nat_gateways = int(config.get("natGateways", 1))
        public_mask = int(config.get("publicSubnetMask", 24))
        private_mask = int(config.get("privateSubnetMask", 24))

        vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=f"{name_prefix}-vpc",
            ip_addresses=ec2.IpAddresses.cidr(vpc_cidr),
            max_azs=max_azs,
            nat_gateways=nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"{name_prefix}-public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=public_mask,
                ),
                ec2.SubnetConfiguration(
                    name=f"{name_prefix}-private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=private_mask,
                ),
            ],
        )

        self.vpc = vpc
        self.public_subnets = vpc.public_subnets
        self.private_subnets = vpc.private_subnets

        CfnOutput(
            self,
            "VpcId",
            value=vpc.vpc_id,
            export_name=f"flexis-vpc-{env_name}-vpc-id",
        )
        CfnOutput(
            self,
            "PublicSubnetIds",
            value=",".join([s.subnet_id for s in vpc.public_subnets]),
            export_name=f"flexis-vpc-{env_name}-public-subnet-ids",
        )
        CfnOutput(
            self,
            "PrivateSubnetIds",
            value=",".join([s.subnet_id for s in vpc.private_subnets]),
            export_name=f"flexis-vpc-{env_name}-private-subnet-ids",
        )

        Tags.of(self).add("application", "flexicx")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexicx")
