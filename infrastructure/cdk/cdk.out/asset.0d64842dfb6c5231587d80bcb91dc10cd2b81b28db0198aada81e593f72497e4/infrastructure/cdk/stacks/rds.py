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
        instance_size = config.get("dbInstanceSize", "MICRO").upper()
        engine_version = str(config.get("dbEngineVersion", "15.4"))
        allocated_storage = int(config.get("dbAllocatedStorage", 20))
        max_allocated_storage = int(config.get("dbMaxAllocatedStorage", 100))

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

        version_key = f"VER_{engine_version.replace('.', '_')}"
        try:
            engine_version_enum = getattr(rds.PostgresEngineVersion, version_key)
        except AttributeError as exc:
            raise ValueError(f"unsupported Postgres version: {engine_version}") from exc

        engine = rds.DatabaseInstanceEngine.postgres(
            version=engine_version_enum
        )

        base_parameters: dict[str, str] = {
            "rds.force_ssl": "1",
        }

        config_params = config.get("dbParameters", {}) or {}
        if not isinstance(config_params, dict):
            raise ValueError("dbParameters in config must be a mapping of string-to-string")

        parameters: dict[str, str] = {
            **base_parameters,
            **{str(k): str(v) for k, v in config_params.items()},
        }

        parameter_group = rds.ParameterGroup(
            self,
            "DbParameterGroup",
            engine=engine,
            description=f"flexischools postgres {env_name} parameter group",
            parameters=parameters,
        )

        credentials = rds.Credentials.from_generated_secret(
            username=db_user,
            secret_name=f"flexischools/{env_name}/rds/admin",
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

        instance = rds.DatabaseInstance(
            self,
            "FlexiPostgres",
            engine=engine,
            instance_type=instance_type,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=subnets),
            security_groups=[rds_sg],
            credentials=credentials,
            database_name=db_name,
            allocated_storage=allocated_storage,
            max_allocated_storage=max_allocated_storage,
            backup_retention=Duration.days(backup_days),
            deletion_protection=deletion_protection,
            parameter_group=parameter_group,
            publicly_accessible=False,
            multi_az=False,
            removal_policy=removal_policy,
        )

        CfnOutput(
            self,
            "DbEndpoint",
            value=instance.db_instance_endpoint_address,
            export_name=f"flexis-rds-{env_name}-endpoint",
        )
        CfnOutput(
            self,
            "DbPort",
            value=str(instance.db_instance_endpoint_port),
            export_name=f"flexis-rds-{env_name}-port",
        )
        CfnOutput(
            self,
            "DbName",
            value=db_name,
            export_name=f"flexis-rds-{env_name}-dbname",
        )
        if instance.secret is not None:
            CfnOutput(
                self,
                "DbSecretArn",
                value=instance.secret.secret_arn,
                export_name=f"flexis-rds-{env_name}-secret-arn",
            )

        CfnOutput(
            self,
            "DbInstanceId",
            value=instance.instance_identifier,
            export_name=f"flexis-rds-{env_name}-instance-id",
        )

        Tags.of(self).add("application", "flexischools")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexischools")
