import logging

from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from config.base_config import InfrastructureConfig

logger = logging.getLogger(__name__)


class OsdEcsApp(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        config: InfrastructureConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._config = config
        self._vpc = vpc
