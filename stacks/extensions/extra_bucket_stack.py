import logging

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class ExtraBucketStack(Stack):
    """
    Example of extension stack for a tenant.
    Stack containing S3 buckets.

    This stack creates two S3 buckets for data storage purposes.
    """

    def __init__(
        self, scope: Construct, construct_id: str, *, infra_context: InfrastructureContext, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._infra_context = infra_context
        self._create_buckets()
        self._create_outputs()

    def _create_buckets(self) -> None:
        """Create S3 buckets."""
        logger.info("Creating data bucket")

        # First bucket: Data storage
        self._data_bucket = s3.Bucket(
            self,
            "DataBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # Keep data on stack deletion
            enforce_ssl=True,
        )

        logger.info("Creating archive bucket")

        # Second bucket: Archive storage
        self._archive_bucket = s3.Bucket(
            self,
            "ArchiveBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        logger.info("Buckets created successfully")

    @property
    def data_bucket(self) -> s3.Bucket:
        """Returns the data bucket."""
        return self._data_bucket

    @property
    def archive_bucket(self) -> s3.Bucket:
        """Returns the archive bucket."""
        return self._archive_bucket

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs."""
        CfnOutput(
            self,
            "DataBucketName",
            value=self._data_bucket.bucket_name,
            description="Name of the data bucket",
            export_name=self._infra_context.context.pascal_prefix("DataBucketName"),
        )

        CfnOutput(
            self,
            "DataBucketArn",
            value=self._data_bucket.bucket_arn,
            description="ARN of the data bucket",
        )

        CfnOutput(
            self,
            "ArchiveBucketName",
            value=self._archive_bucket.bucket_name,
            description="Name of the archive bucket",
            export_name=self._infra_context.context.pascal_prefix("ArchiveBucketName"),
        )

        CfnOutput(
            self,
            "ArchiveBucketArn",
            value=self._archive_bucket.bucket_arn,
            description="ARN of the archive bucket",
        )
