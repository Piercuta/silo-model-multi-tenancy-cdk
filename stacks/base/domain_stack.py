import logging
from pathlib import Path

from aws_cdk import CustomResource, Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_route53 as route53
from constructs import Construct

from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)

OSD_NAT_MAIN_ACCOUNT_ID = "111111111111"


class DomainStack(Stack):
    """
    Stack containing the Domain resources for the infrastructure.

    This stack creates the necessary Domain resources for the infrastructure.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating domain stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._vpc = vpc
        self._infra_context = infra_context

        self._hosted_zone, is_created_hosted_zone = self._create_get_hosted_zone()

        if (
            self._infra_context.config.domain.parent_hosted_zone_id
            and not self._infra_context.config.domain.hosted_zone_id
        ):
            self._parent_hosted_zone = self._get_parent_hosted_zone()
            if self._infra_context.config.aws.account == OSD_NAT_MAIN_ACCOUNT_ID:
                self._cloudfront_certificate = self._zone_delegation()
            else:
                self._cloudfront_certificate = self._cross_account_zone_delegation()

        self._alb_certificate = self._create_get_alb_certificate()

        # Create custom resource to clean up DNS validation records before hosted zone deletion
        # Only if we created the hosted zone (not if it's imported)
        if is_created_hosted_zone:
            self._create_dns_cleanup_custom_resource()

        logger.info(
            f"Domain stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def hosted_zone(self) -> route53.HostedZone:
        return self._hosted_zone

    @property
    def alb_certificate_arn(self) -> str:
        return self._alb_certificate.certificate_arn

    def _get_parent_hosted_zone(self) -> route53.HostedZone:
        logger.info(
            f"Getting parent hosted zone from ID: {self._infra_context.config.domain.parent_hosted_zone_id}"
        )
        return route53.HostedZone.from_hosted_zone_attributes(
            self,
            "ParentHostedZone",
            hosted_zone_id=self._infra_context.config.domain.parent_hosted_zone_id,
            zone_name=self._infra_context.config.domain.zone_name,
        )

    def _zone_delegation(self):
        logger.info(
            f"Creating zone delegation record for {self._infra_context.config.domain.zone_name}"
        )
        zone_delegation_record = route53.ZoneDelegationRecord(
            self,
            "ZoneDelegationRecord",
            name_servers=self._hosted_zone.hosted_zone_name_servers,
            zone=self._parent_hosted_zone,
            comment=f"Zone delegation record for {self._infra_context.config.domain.zone_name}",
            ttl=Duration.seconds(300),
            record_name=self._infra_context.config.domain.zone_name,
        )
        return zone_delegation_record

    def _cross_account_zone_delegation(self):
        """
        Create cross-account zone delegation record.

        Requires delegation_role_arn in config pointing to a role in the parent account
        that allows this account to assume it and modify the parent hosted zone.
        """
        if not self._infra_context.config.domain.delegation_role_arn:
            raise ValueError("delegation_role_arn is required for cross-account zone delegation")

        logger.info(
            f"Using delegation role: {self._infra_context.config.domain.delegation_role_arn}"
        )

        # Import the delegation role from parent account
        delegation_role = iam.Role.from_role_arn(
            self,
            "DelegationRole",
            self._infra_context.config.domain.delegation_role_arn,
        )

        # Create the cross-account zone delegation record
        route53.CrossAccountZoneDelegationRecord(
            self,
            "CrossAccountZoneDelegationRecord",
            delegated_zone=self._hosted_zone,
            parent_hosted_zone_id=self._parent_hosted_zone.hosted_zone_id,
            delegation_role=delegation_role,
            ttl=Duration.seconds(300),
        )

    def _create_get_alb_certificate(self) -> acm.Certificate:
        if self._infra_context.config.domain.alb_certificate_arn:
            logger.info(
                f"Getting ALB certificate from ARN: {self._infra_context.config.domain.alb_certificate_arn}"
            )
            alb_certificate = acm.Certificate.from_certificate_arn(
                self, "AlbCertificate", self._infra_context.config.domain.alb_certificate_arn
            )
        else:
            logger.info(
                f"Creating ALB certificate for domain: {self._infra_context.config.domain.zone_name}"
            )
            alb_certificate = acm.Certificate(
                self,
                "AlbCertificate",
                domain_name=self._infra_context.config.domain.zone_name,
                subject_alternative_names=[f"*.{self._infra_context.config.domain.zone_name}"],
                validation=acm.CertificateValidation.from_dns(self._hosted_zone),
            )
            # NOTE: Now we automatically delegate the certificate to the parent hosted zone, so we don't need to retain it
            # alb_certificate.apply_removal_policy(RemovalPolicy.RETAIN)
        return alb_certificate

    def _create_get_hosted_zone(self) -> tuple[route53.HostedZone, bool]:
        is_created_hosted_zone = False
        if self._infra_context.config.domain.hosted_zone_id:
            logger.info(
                f"Getting hosted zone from ID: {self._infra_context.config.domain.hosted_zone_id}"
            )
            hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "HostedZone",
                hosted_zone_id=self._infra_context.config.domain.hosted_zone_id,
                zone_name=self._infra_context.config.domain.zone_name,
            )
        else:
            logger.info(f"Creating hosted zone: {self._infra_context.config.domain.zone_name}")
            hosted_zone = route53.HostedZone(
                self, "HostedZone", zone_name=self._infra_context.config.domain.zone_name
            )
            is_created_hosted_zone = True
            # NOTE: Now we automatically delegate the hosted zone to the parent hosted zone, so we don't need to retain it
            # hosted_zone.apply_removal_policy(RemovalPolicy.RETAIN)
        return hosted_zone, is_created_hosted_zone

    def _create_dns_cleanup_custom_resource(self) -> None:
        """
        Create a custom resource with Lambda to clean up ACM DNS validation records
        before hosted zone deletion.

        This prevents HostedZoneNotEmptyException when deleting the hosted zone
        that contains ACM validation records.
        """
        logger.info("Creating DNS cleanup custom resource")
        LAMBDA_DIR = Path(__file__).resolve().parent.parent.parent / "lib" / "cleanup_dns_lambda"
        # Create Lambda function
        cleanup_lambda = lambda_.Function(
            self,
            "DnsCleanupLambda",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="cleanup_dns_validation_records.handler",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR)),
            timeout=Duration.minutes(2),
            memory_size=256,
        )

        # Grant permissions to the Lambda to manage Route53 records
        cleanup_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:ListResourceRecordSets",
                    "route53:ChangeResourceRecordSets",
                    "route53:GetChange",
                ],
                resources=[
                    f"arn:aws:route53:::hostedzone/{self._hosted_zone.hosted_zone_id}",
                    "arn:aws:route53:::change/*",
                ],
            )
        )

        # Create custom resource that triggers on stack deletion
        CustomResource(
            self,
            "DnsCleanupResource",
            service_token=cleanup_lambda.function_arn,
            properties={
                "HostedZoneId": self._hosted_zone.hosted_zone_id,
            },
            service_timeout=Duration.minutes(3),
        )

        # Ensure the hosted zone is deleted AFTER the cleanup resource
        # This ensures DNS validation records are cleaned up before hosted zone deletion
        # self._hosted_zone.node.add_dependency(cleanup_resource)

        logger.info("DNS cleanup custom resource created successfully")
