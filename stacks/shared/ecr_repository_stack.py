# stacks/shared/ecr_repository_stack.py

import logging
from typing import List, Optional

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from constructs import Construct

logger = logging.getLogger(__name__)


class EcrRepositoryStack(Stack):
    """
    Generic stack for creating ECR repositories in a specific region.

    This stack can be instantiated multiple times for different regions.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        region: str,
        repository_names: Optional[List[str]] = None,
        accounts: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._region = region
        self._repository_names = repository_names or []
        self._accounts = accounts
        self._repositories = self._create_repositories()
        # self._add_lifecycle_policies()

    def _create_repositories(self) -> dict[str, ecr.Repository]:
        """Create ECR repositories in the specified region."""
        repositories = {}
        logger.info(f"Creating ECR repositories in {self._region}...")

        for repo_name in self._repository_names:
            # Create repository with image scanning and encryption
            repository = ecr.Repository(
                self,
                f"EcrRepository{self._sanitize_name(repo_name)}",
                repository_name=repo_name,
                image_scan_on_push=True,
                encryption=ecr.RepositoryEncryption.AES_256,
                removal_policy=RemovalPolicy.DESTROY,
                empty_on_delete=True,
            )

            # Add cross-account policy to allow pull access from specified accounts
            if self._accounts:
                # Create list of principal ARNs for all allowed accounts
                principal_arns = [
                    f"arn:aws:iam::{account_id}:root" for account_id in self._accounts
                ]

                repository.add_to_resource_policy(
                    iam.PolicyStatement(
                        sid="CrossAccountPull",
                        effect=iam.Effect.ALLOW,
                        principals=[iam.ArnPrincipal(arn) for arn in principal_arns],
                        actions=[
                            "ecr:BatchCheckLayerAvailability",
                            "ecr:BatchGetImage",
                            "ecr:GetDownloadUrlForLayer",
                        ],
                    )
                )
                logger.info(
                    f"Added cross-account pull permissions for {len(self._accounts)} accounts: {self._accounts}"
                )
            repositories[repo_name] = repository
            logger.info(f"ECR repository created: {repo_name} in {self._region}")

        logger.info(f"Created {len(repositories)} ECR repositories in {self._region}")
        return repositories

    def _add_lifecycle_policies(self) -> None:
        """Add lifecycle policies to all repositories to manage image retention."""
        logger.info("Adding lifecycle policies to ECR repositories...")

        for repo_name, repository in self._repositories.items():
            # Delete untagged images older than 1 day (lower priority)
            repository.add_lifecycle_rule(
                description="Delete untagged images older than 1 day",
                max_image_age=Duration.days(1),
                tag_status=ecr.TagStatus.UNTAGGED,
                rule_priority=1,
            )

            # Keep last 10 images, delete older ones (TagStatus.ANY must have highest priority = highest number)
            repository.add_lifecycle_rule(
                description="Keep last 10 images",
                max_image_count=10,
                rule_priority=2,
            )

        logger.info("Lifecycle policies added successfully")

    def _sanitize_name(self, name: str) -> str:
        """Sanitize repository name for use in construct ID."""
        # Replace slashes and hyphens with underscores, capitalize first letter of each word
        sanitized = name.replace("/", "").replace("-", "").title().replace(" ", "")
        return sanitized

    @property
    def repositories(self) -> dict[str, ecr.Repository]:
        """Returns a dictionary of ECR repositories by name."""
        return self._repositories

    def get_repository(self, repository_name: str) -> Optional[ecr.Repository]:
        """Get a specific repository by name."""
        return self._repositories.get(repository_name)
