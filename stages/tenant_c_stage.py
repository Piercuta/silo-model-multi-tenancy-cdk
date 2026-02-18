import logging

from aws_cdk import Environment
from constructs import Construct

from config.loader import InfrastructureContext
from stacks.extensions.extra_bucket_stack import ExtraBucketStack
from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


class TenantCStage(BaseStage):
    """
    Custom stage for Tenant C with additional bucket storage.

    This stage inherits all base stacks (Network, Security) from BaseStage
    and adds a BucketStack with two S3 buckets for data and archive storage.
    """

    def __init__(
        self, scope: Construct, construct_id: str, *, infra_context: InfrastructureContext, **kwargs
    ) -> None:
        # First create base stacks (Network, Security)
        super().__init__(scope, construct_id, infra_context=infra_context, **kwargs)

        # Then add tenant-specific stacks
        self._extra_bucket_stack = None
        self._create_tenant_c_stacks()

    @property
    def extra_bucket_stack(self) -> ExtraBucketStack:
        if self._extra_bucket_stack is None:
            raise ValueError("Extra bucket stack not initialized")
        return self._extra_bucket_stack

    def _create_tenant_c_stacks(self) -> ExtraBucketStack:
        """Create additional stacks specific to Tenant B."""
        logger.info(
            f"Creating extra bucket stack (environment: {self._infra_context.context.env_name}, tenant: {self._infra_context.context.tenant_name})"
        )

        logger.info("Retrieving network and security stack information from base stage")
        logging.info(f"VPC ID: {self.network_stack.vpc.vpc_id}")
        logging.info(f"ALB security group id: {self.security_stack.alb_sg.security_group_id}")
        logging.info(f"RDS security group id: {self.security_stack.rds_sg.security_group_id}")

        self._extra_bucket_stack = ExtraBucketStack(
            self,
            "ExtraBucketStack",
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        # NOTE: Add bucket naming aspect for all bukcets in the extra bucket stack
        # Aspects.of(self._extra_bucket_stack).add(BucketNamingAspect())

        logger.info(
            f"Extra bucket stack created successfully (environment: {self._infra_context.context.env_name}, tenant: {self._infra_context.context.tenant_name})"
        )
        return self._extra_bucket_stack
