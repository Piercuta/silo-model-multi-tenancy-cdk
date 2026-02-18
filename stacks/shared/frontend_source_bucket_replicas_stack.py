# stacks/shared/frontend_source_bucket_replicas_stack.py

import logging
from typing import List, Optional

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

logger = logging.getLogger(__name__)

# Default list of allowed account IDs for cross-account access
DEFAULT_ALLOWED_ACCOUNT_IDS = [
    "333333333333",
    "999999999999",
    "888888888888",
]


class FrontendSourceBucketReplicaStack(Stack):
    """
    Generic stack for creating a frontend source bucket replica in a specific region.

    This stack can be instantiated multiple times for different regions.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        region: str,
        allowed_account_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._region = region
        self._allowed_account_ids = allowed_account_ids or DEFAULT_ALLOWED_ACCOUNT_IDS
        self._bucket = self._create_bucket()
        self._add_cross_account_policy()

    def _create_bucket(self) -> s3.Bucket:
        """Create a replica bucket in the specified region."""
        bucket_name = f"appfront-{self._region}"
        logger.info(f"Creating frontend source bucket replica in {self._region}...")

        bucket = s3.Bucket(
            self,
            "FrontendSourceBucket",
            bucket_name=bucket_name,
            versioned=True,  # Required for replication
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        logger.info(f"Bucket created: {bucket.bucket_name}")
        return bucket

    def _add_cross_account_policy(self) -> None:
        """Add bucket policy to allow cross-account access from other accounts."""
        if not self._allowed_account_ids:
            logger.info("No allowed account IDs specified, skipping cross-account policy")
            return

        logger.info(f"Adding cross-account policy for accounts: {self._allowed_account_ids}")

        # Create bucket policy document
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": [
                            f"arn:aws:iam::{account_id}:root"
                            for account_id in self._allowed_account_ids
                        ]
                    },
                    "Action": [
                        "s3:GetObject",
                        "s3:GetObjectVersion",
                        "s3:GetBucketVersioning",
                        "s3:ListBucket",
                    ],
                    "Resource": [
                        f"arn:aws:s3:::{self._bucket.bucket_name}",
                        f"arn:aws:s3:::{self._bucket.bucket_name}/*",
                    ],
                }
            ],
        }

        # Add bucket policy
        self._bucket.add_to_resource_policy(
            iam.PolicyStatement.from_json(policy_document["Statement"][0])
        )

        logger.info("Cross-account bucket policy added successfully")

    @property
    def bucket(self) -> s3.Bucket:
        """Returns the bucket."""
        return self._bucket
