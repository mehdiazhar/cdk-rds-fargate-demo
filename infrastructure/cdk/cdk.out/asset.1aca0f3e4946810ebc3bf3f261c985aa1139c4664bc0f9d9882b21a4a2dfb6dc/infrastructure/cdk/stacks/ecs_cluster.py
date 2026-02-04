from aws_cdk import (
    Stack,
    CfnOutput,
    Tags,
    aws_ec2 as ec2,
    aws_ecs as ecs,
)
from constructs import Construct


class FlexiEcsClusterStack(Stack):
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

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "Vpc",
            vpc_id=config["vpcId"],
            availability_zones=config["availabilityZones"],
            public_subnet_ids=config.get("publicSubnetIds", []),
            private_subnet_ids=config.get("privateSubnetIds", []),
        )

        cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=vpc,
            cluster_name=f"{name_prefix}-cluster",
        )

        CfnOutput(
            self,
            "ClusterArn",
            value=cluster.cluster_arn,
            export_name=f"flexis-ecs-{env_name}-cluster-arn",
        )
        CfnOutput(
            self,
            "ClusterName",
            value=cluster.cluster_name,
            export_name=f"flexis-ecs-{env_name}-cluster-name",
        )

        Tags.of(self).add("application", "flexischools")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexischools")
