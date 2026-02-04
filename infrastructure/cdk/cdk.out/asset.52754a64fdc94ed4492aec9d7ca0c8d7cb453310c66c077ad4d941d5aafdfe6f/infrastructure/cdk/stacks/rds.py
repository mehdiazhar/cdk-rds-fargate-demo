from typing import Mapping, Any, Sequence

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    Fn,
    Tags,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_logs as logs,
)
from constructs import Construct


class FlexiPostgresStack(Stack):
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

        vpc_id: str = config["vpcId"]
        subnet_ids: Sequence[str] = config["privateSubnetIds"]
        availability_zones = config["availabilityZones"]

        db_name = config.get("dbName", "flexisorders")
        db_user = config.get("dbUser", "flexis_admin")

        backup_days = int(config.get("backupDays", 7))
        deletion_protection = bool(config.get("deletionProtection", False))

        instance_class = config.get("dbInstanceClass", "T3").upper()
        instance_size = config.get("dbInstanceSize", "MEDIUM").upper()

        engine_full = str(config.get("engineFullVersion", config.get("dbEngineVersion", "17.7")))
        engine_major = str(config.get("engineMajorVersion", engine_full.split(".")[0]))

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "Vpc",
            vpc_id=vpc_id,
            availability_zones=availability_zones,
            private_subnet_ids=subnet_ids,
        )

        subnets = [
            ec2.Subnet.from_subnet_id(self, f"PrivateSubnet{i+1}", sid)
            for i, sid in enumerate(subnet_ids)
        ]

        rds_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "ImportedRdsSg",
            security_group_id=Fn.import_value(f"flexis-sg-{env_name}-rds-sg-id"),
            mutable=False,
        )

        engine = rds.DatabaseClusterEngine.aurora_postgres(
            version=rds.AuroraPostgresEngineVersion.of(
                engine_full,
                engine_major,
            )
        )

        base_parameters: dict[str, str] = {
            "rds.force_ssl": "1",
            "log_connections": "1",
            "log_disconnections": "1",
            "log_min_duration_statement": "1000",
        }

        config_params = config.get("clusterParameters", {}) or {}
        if not isinstance(config_params, dict):
            raise ValueError("clusterParameters in config must be a mapping of string-to-string")

        parameters: dict[str, str] = {
            **base_parameters,
            **{str(k): str(v) for k, v in config_params.items()},
        }

        parameter_group = rds.ParameterGroup(
            self,
            "ClusterParameterGroup",
            engine=engine,
            description=f"flexischools aurora postgres {env_name} cluster parameters",
            parameters=parameters,
        )

        credentials = rds.Credentials.from_generated_secret(
            username=db_user,
            secret_name=f"flexischools/{env_name}/aurora-postgres/admin",
        )

        instance_type = ec2.InstanceType.of(
            getattr(ec2.InstanceClass, instance_class),
            getattr(ec2.InstanceSize, instance_size),
        )

        removal_policy = (
            RemovalPolicy.SNAPSHOT
            if env_name in ("staging", "production")
            else RemovalPolicy.DESTROY
        )

        writer = rds.ClusterInstance.provisioned(
            "Writer",
            instance_identifier=f"flexis-aurora-{env_name}-writer",
            instance_type=instance_type,
            publicly_accessible=False,
        )

        cluster = rds.DatabaseCluster(
            self,
            "FlexiAuroraPostgres",
            engine=engine,
            writer=writer,
            credentials=credentials,
            default_database_name=db_name,
            cluster_identifier=f"flexis-aurora-postgres-{env_name}",
            parameter_group=parameter_group,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=subnets),
            security_groups=[rds_sg],
            backup=rds.BackupProps(
                retention=Duration.days(backup_days),
            ),
            cloudwatch_logs_exports=["postgresql"],
            cloudwatch_logs_retention=logs.RetentionDays.ONE_WEEK,
            deletion_protection=deletion_protection,
            removal_policy=removal_policy,
        )

        CfnOutput(
            self,
            "DbEndpoint",
            value=cluster.cluster_endpoint.hostname,
            export_name=f"flexis-rds-{env_name}-endpoint",
        )
        CfnOutput(
            self,
            "DbPort",
            value=str(cluster.cluster_endpoint.port),
            export_name=f"flexis-rds-{env_name}-port",
        )
        CfnOutput(
            self,
            "DbName",
            value=db_name,
            export_name=f"flexis-rds-{env_name}-dbname",
        )
        if cluster.secret is not None:
            CfnOutput(
                self,
                "DbSecretArn",
                value=cluster.secret.secret_arn,
                export_name=f"flexis-rds-{env_name}-secret-arn",
            )

        CfnOutput(
            self,
            "DbClusterId",
            value=cluster.cluster_identifier,
            export_name=f"flexis-rds-{env_name}-cluster-id",
        )

        Tags.of(self).add("application", "flexischools")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexischools")
