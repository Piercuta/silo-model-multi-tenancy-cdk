import logging

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class StorageStack(Stack):
    """
    Stack containing the storage resources for the infrastructure.

    This stack creates the necessary storage resources for the infrastructure.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating storage stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._infra_context = infra_context

        self._osd_storage_bucket = self._create_get_osd_storage_bucket()

        logger.info(
            f"Storage stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def osd_storage_bucket_name(self) -> str:
        return self._osd_storage_bucket.bucket_name

    def _create_get_osd_storage_bucket(self) -> s3.Bucket:
        """Create S3 buckets."""

        logger.info("Creating OSD storage bucket")
        # First bucket: Data storage
        if self._infra_context.config.storage.osd_bucket_name:
            osd_bucket = s3.Bucket.from_bucket_name(
                self,
                "OSDStorage",
                self._infra_context.config.storage.osd_bucket_name,
            )
            logger.info("OSD storage bucket retrieved successfully")
        else:
            osd_bucket = s3.Bucket(
                self,
                "OSDStorage",
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                encryption=s3.BucketEncryption.S3_MANAGED,
                enforce_ssl=True,
                versioned=True,
                removal_policy=(
                    RemovalPolicy.DESTROY
                    if self._infra_context.context.env_name in ["dev"]
                    else RemovalPolicy.RETAIN
                ),
                auto_delete_objects=(
                    True if self._infra_context.context.env_name in ["dev"] else False
                ),
            )
            logger.info("OSD storage bucket created successfully")
        return osd_bucket
