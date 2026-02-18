# stacks/shared/frontend_source_bucket_eu_west_1_stack.py

import logging

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk.aws_s3 import CfnBucket
from constructs import Construct

logger = logging.getLogger(__name__)


class FrontendSourceMainBucketStack(Stack):
    """
    Stack for primary frontend source bucket in eu-west-1 with cross-region replication.

    Creates the primary bucket appfront-eu-west-1 and configures replication to:
    - appfront-eu-west-3 (replica in eu-west-3)
    - appfront-eu-central-1 (replica in eu-central-1)
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create IAM role for replication (must be created before bucket)
        self._replication_role = self._create_replication_role()

        # Primary bucket (eu-west-1) with replication configuration
        self._primary_bucket = self._create_primary_bucket()

    def _create_replication_role(self) -> iam.Role:
        """Create IAM role for S3 replication service."""
        logger.info("Creating IAM role for S3 replication...")

        role = iam.Role(
            self,
            "S3ReplicationRole",
            assumed_by=iam.ServicePrincipal("s3.amazonaws.com"),
            description="Role for S3 cross-region replication of frontend source buckets",
        )

        # Permissions for source bucket (eu-west-1)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetReplicationConfiguration",
                    "s3:ListBucket",
                ],
                resources=["arn:aws:s3:::appfront-eu-west-1"],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObjectVersionForReplication",
                    "s3:GetObjectVersionAcl",
                    "s3:GetObjectVersionTagging",
                ],
                resources=["arn:aws:s3:::appfront-eu-west-1/*"],
            )
        )

        # Permissions for replica buckets
        replica_buckets = [
            "appfront-eu-west-3",
            "appfront-eu-central-1",
        ]

        for bucket_name in replica_buckets:
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:ReplicateObject",
                        "s3:ReplicateDelete",
                        "s3:ReplicateTags",
                        "s3:GetObjectVersionTagging",
                    ],
                    resources=[f"arn:aws:s3:::{bucket_name}/*"],
                )
            )

            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:ObjectOwnerOverrideToBucketOwner"],
                    resources=[f"arn:aws:s3:::{bucket_name}/*"],
                )
            )

        logger.info("Replication role created successfully")
        return role

    def _create_primary_bucket(self) -> s3.Bucket:
        """Create the primary bucket in eu-west-1 with replication configuration."""
        logger.info("Creating primary frontend source bucket...")

        bucket = s3.Bucket(
            self,
            "PrimaryFrontendSourceBucket",
            bucket_name="appfront-eu-west-1",
            versioned=True,  # Required for replication
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Configure replication using CfnBucket (low-level construct)
        # Note: The destination buckets must exist before this stack is deployed
        # Using Replication V2 schema to support multiple destination buckets
        cfn_bucket = bucket.node.default_child
        if isinstance(cfn_bucket, CfnBucket):
            cfn_bucket.replication_configuration = CfnBucket.ReplicationConfigurationProperty(
                role=self._replication_role.role_arn,
                rules=[
                    CfnBucket.ReplicationRuleProperty(
                        id="ReplicateToEuWest3",
                        priority=1,  # Required for V2 schema
                        filter=CfnBucket.ReplicationRuleFilterProperty(
                            prefix="",  # Replicate all objects
                        ),
                        status="Enabled",
                        delete_marker_replication=CfnBucket.DeleteMarkerReplicationProperty(
                            status="Enabled"
                        ),
                        destination=CfnBucket.ReplicationDestinationProperty(
                            bucket="arn:aws:s3:::appfront-eu-west-3",
                            storage_class="STANDARD",
                        ),
                    ),
                    CfnBucket.ReplicationRuleProperty(
                        id="ReplicateToEuCentral1",
                        priority=2,  # Required for V2 schema
                        filter=CfnBucket.ReplicationRuleFilterProperty(
                            prefix="",  # Replicate all objects
                        ),
                        status="Enabled",
                        delete_marker_replication=CfnBucket.DeleteMarkerReplicationProperty(
                            status="Enabled"
                        ),
                        destination=CfnBucket.ReplicationDestinationProperty(
                            bucket="arn:aws:s3:::appfront-eu-central-1",
                            storage_class="STANDARD",
                        ),
                    ),
                ],
            )

        logger.info(f"Primary bucket created: {bucket.bucket_name}")
        logger.info("Replication configured to eu-west-3 and eu-central-1")
        return bucket

    @property
    def primary_bucket(self) -> s3.Bucket:
        """Returns the primary bucket."""
        return self._primary_bucket
