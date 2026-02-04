from typing import Mapping, Any

from aws_cdk import (
    Duration,
    Stack,
    CfnOutput,
    Tags,
    aws_sqs as sqs,
)
from constructs import Construct


class FlexiSqsStack(Stack):
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
        queue_cfg = config.get("sqs", {})
        queue_name = queue_cfg.get("queueName", f"{name_prefix}-orders")
        visibility_timeout = int(queue_cfg.get("visibilityTimeout", 30))
        retention_days = int(queue_cfg.get("retentionDays", 4))

        queue = sqs.Queue(
            self,
            "OrdersQueue",
            queue_name=queue_name,
            visibility_timeout=Duration.seconds(visibility_timeout),
            retention_period=Duration.days(retention_days),
        )

        CfnOutput(
            self,
            "QueueUrl",
            value=queue.queue_url,
            export_name=f"flexis-orders-{env_name}-queue-url",
        )
        CfnOutput(
            self,
            "QueueArn",
            value=queue.queue_arn,
            export_name=f"flexis-orders-{env_name}-queue-arn",
        )

        Tags.of(self).add("application", "flexischools")
        Tags.of(self).add("environment", env_name)
        Tags.of(self).add("product", "flexischools")
