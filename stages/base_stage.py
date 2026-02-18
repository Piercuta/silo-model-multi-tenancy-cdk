import logging

from aws_cdk import Environment, Stage
from constructs import Construct

from config.loader import InfrastructureContext
from stacks.base.application_stack import ApplicationStack
from stacks.base.cloudfront_certificate_stack import CloudFrontCertificateStack
from stacks.base.database_stack import DatabaseStack
from stacks.base.domain_stack import DomainStack
from stacks.base.front_end_stack import FrontEndStack
from stacks.base.network_stack import NetworkStack
from stacks.base.security_stack import SecurityStack
from stacks.base.storage_stack import StorageStack

logger = logging.getLogger(__name__)


class BaseStage(Stage):
    def __init__(
        self, scope: Construct, construct_id: str, *, infra_context: InfrastructureContext, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._infra_context = infra_context

        logger.info(
            "Creating stage for environment: %s, tenant: %s (account: %s, region: %s)",
            self._infra_context.context.env_name,
            self._infra_context.context.tenant_name,
            self._infra_context.config.aws.account,
            self._infra_context.config.aws.region_str,
        )

        self._create_base_stacks()
        # NOTE: It is important to tag the stage, it will propagate to all resources created.
        self._infra_context.context.add_stage_global_tags(self)

        logger.info(
            "Stage created successfully for environment: %s, tenant: %s (account: %s, region: %s)",
            self._infra_context.context.env_name,
            self._infra_context.context.tenant_name,
            self._infra_context.config.aws.account,
            self._infra_context.config.aws.region_str,
        )

    @property
    def infra_context(self) -> InfrastructureContext:
        return self._infra_context

    @property
    def network_stack(self) -> NetworkStack:
        return self._network_stack

    @property
    def security_stack(self) -> SecurityStack:
        return self._security_stack

    @property
    def storage_stack(self) -> StorageStack:
        return self._storage_stack

    @property
    def domain_stack(self) -> DomainStack:
        return self._domain_stack

    @property
    def database_stack(self) -> DatabaseStack:
        return self._database_stack

    @property
    def application_stack(self) -> ApplicationStack:
        return self._application_stack

    @property
    def front_end_stack(self) -> FrontEndStack:
        return self._front_end_stack

    @property
    def cloudfront_certificate_stack(self) -> CloudFrontCertificateStack:
        return self._cloudfront_certificate_stack

    def _create_base_stacks(self):
        self._network_stack = NetworkStack(
            self,
            "NetworkStack",
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        self._security_stack = SecurityStack(
            self,
            "SecurityStack",
            vpc=self._network_stack.vpc,
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        self._database_stack = DatabaseStack(
            self,
            "DatabaseStack",
            vpc=self._network_stack.vpc,
            doc_db_security_group=self._security_stack.docdb_sg,
            docdb_lambda_security_group=self._security_stack.docdb_lambda_sg,
            redis_security_group=self._security_stack.redis_sg,
            rds_lambda_security_group=self._security_stack.rds_lambda_sg,
            aurora_security_group=self._security_stack.rds_sg,
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        self._storage_stack = StorageStack(
            self,
            "StorageStack",
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        self._domain_stack = DomainStack(
            self,
            "DomainStack",
            vpc=self._network_stack.vpc,
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        if self._infra_context.config.aws.region_str != "us-east-1":
            self._cloudfront_certificate_stack = CloudFrontCertificateStack(
                self,
                "CloudFrontCertificateStack",
                hosted_zone=self._domain_stack.hosted_zone,
                infra_context=self._infra_context,
                env=Environment(
                    account=self._infra_context.config.aws.account,
                    region="us-east-1",
                ),
                cross_region_references=True,
            )
        else:
            # us-east-1 does not need a cloudfront certificate, already created with the domain stack
            self._cloudfront_certificate_stack = None

        self._application_stack = ApplicationStack(
            self,
            "ApplicationStack",
            vpc=self._network_stack.vpc,
            # Security groups
            alb_sg=self._security_stack.alb_sg,
            ecs_shared_sg=self._security_stack.ecs_shared_sg,
            osd_api_sg=self._security_stack.osd_api_sg,
            keycloak_sg=self._security_stack.keycloak_sg,
            # Storage outputs
            osd_storage_bucket_name=self._storage_stack.osd_storage_bucket_name,
            # Database outputs
            docdb_cluster_endpoint=self._database_stack.docdb_cluster_endpoint,
            docdb_cluster_port=self._database_stack.docdb_cluster_port,
            docdb_cluster_secret_arn=self._database_stack.docdb_cluster_secret_arn,
            redis_cluster_endpoint=self._database_stack.redis_cluster_endpoint,
            aurora_cluster_secret=self._database_stack.aurora_cluster_secret,
            aurora_cluster_jdbc_url=self._database_stack.aurora_cluster_jdbc_url,
            # Domain outputs
            alb_certificate_arn=self._domain_stack.alb_certificate_arn,
            hosted_zone=self._domain_stack.hosted_zone,
            # Config
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region=self._infra_context.config.aws.region_str,
            ),
        )

        self._front_end_stack = FrontEndStack(
            self,
            "FrontEndStack",
            hosted_zone=self._domain_stack.hosted_zone,
            cloudfront_certificate_arn=(
                self._cloudfront_certificate_stack.cloudfront_certificate_arn
                if self._cloudfront_certificate_stack
                else self._domain_stack.alb_certificate_arn
            ),
            infra_context=self._infra_context,
            env=Environment(
                account=self._infra_context.config.aws.account,
                region="us-east-1",
            ),
            cross_region_references=True,
        )
