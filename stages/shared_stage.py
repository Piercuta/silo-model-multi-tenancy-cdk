# stages/shared_stage.py

import logging
from typing import List

from aws_cdk import Environment, Stage
from constructs import Construct

from stacks.shared.ecr_repository_stack import EcrRepositoryStack
from stacks.shared.frontend_source_bucket_replicas_stack import FrontendSourceBucketReplicaStack
from stacks.shared.frontend_source_main_bucket_stack import FrontendSourceMainBucketStack

logger = logging.getLogger(__name__)

# Default list of ECR repository names to create
DEFAULT_REPOSITORY_BASE_NAME = "osd"
DEFAULT_REPOSITORY_NAMES = [
    f"{DEFAULT_REPOSITORY_BASE_NAME}/osd-api",
    f"{DEFAULT_REPOSITORY_BASE_NAME}/xslt-processor",
    f"{DEFAULT_REPOSITORY_BASE_NAME}/keycloak",
    f"{DEFAULT_REPOSITORY_BASE_NAME}/fonto/review",
    f"{DEFAULT_REPOSITORY_BASE_NAME}/fonto/content-quality",
    f"{DEFAULT_REPOSITORY_BASE_NAME}/fonto/document-history",
]


class SharedStage(Stage):
    """
    Stage for deploying shared infrastructure resources across multiple regions.

    This stage deploys:
    - Frontend source buckets with cross-region replication:
      * Primary bucket in eu-west-1
      * Replica buckets in eu-west-3 and eu-central-1 (created via loop)
    - ECR repositories in all regions (main region + replication regions):
      * osd/osd-api
      * osd/xslt-processor
      * osd/keycloak
      * osd/fonto/review
      * osd/fonto/content-quality
      * osd/fonto/document-history
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        main_account_id: str,
        main_account_region: str,
        # replication_regions: List[str],
        tenants: List[str],
        accounts: List[str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(f"Creating shared stage (account: {main_account_id})")

        self._main_account_id = main_account_id
        self._main_account_region = main_account_region
        # self._replication_regions = replication_regions
        self._tenants = tenants
        self._accounts = accounts
        self._create_shared_stacks()

        logger.info("Shared stage created successfully")

    def _create_shared_stacks(self) -> None:
        """Create shared stacks in their respective regions."""

        # self._create_buckets_frontend()
        self._create_ecr_repositories()

        logger.info("All shared stacks created")

    def _create_ecr_repositories(self) -> None:
        """Create ECR repositories in all regions (main region + replication regions)."""
        self._ecr_stacks = {}

        repository_osd_api_names = [
            f"{DEFAULT_REPOSITORY_BASE_NAME}/osd-api-{tenant}" for tenant in self._tenants
        ]

        # Create ECR repositories in main region
        main_stack_id = "EcrRepositoriesStack"
        main_stack = EcrRepositoryStack(
            self,
            main_stack_id,
            region=self._main_account_region,
            env=Environment(account=self._main_account_id, region=self._main_account_region),
            repository_names=repository_osd_api_names + DEFAULT_REPOSITORY_NAMES,
            accounts=self._accounts,
        )
        self._ecr_stacks[self._main_account_region] = main_stack
        logger.info(f"Created ECR repository stack for main region: {self._main_account_region}")

    def _create_buckets_frontend(self) -> None:
        # Create replica bucket stacks for each replication region (via loop)
        # Must be created before the main bucket
        self._replica_stacks = {}
        for region in self._replication_regions:
            stack_id = f"FrontendSourceBucketReplica{region.replace('-', '').title()}Stack"
            stack = FrontendSourceBucketReplicaStack(
                self,
                stack_id,
                region=region,
                env=Environment(account=self._main_account_id, region=region),
            )
            self._replica_stacks[region] = stack
            logger.info(f"Created replica bucket stack for region: {region}")

        # Primary bucket in eu-west-1 with replication configuration
        # This must be created after the replica buckets exist
        self._main_bucket_stack = FrontendSourceMainBucketStack(
            self,
            "FrontendSourceMainBucketStack",
            env=Environment(account=self._main_account_id, region=self._main_account_region),
        )
        # Add dependencies to ensure replica buckets are created before main bucket
        for replica_stack in self._replica_stacks.values():
            self._main_bucket_stack.node.add_dependency(replica_stack)

    @property
    def main_bucket_stack(self) -> FrontendSourceMainBucketStack:
        """Returns the main bucket stack in eu-west-1."""
        return self._main_bucket_stack

    @property
    def replica_stacks(self) -> dict[str, FrontendSourceBucketReplicaStack]:
        """Returns a dictionary of replica bucket stacks by region."""
        return self._replica_stacks

    @property
    def ecr_stacks(self) -> dict[str, EcrRepositoryStack]:
        """Returns a dictionary of ECR repository stacks by region."""
        return self._ecr_stacks
