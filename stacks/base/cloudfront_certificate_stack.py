import logging

from aws_cdk import Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct

from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class CloudFrontCertificateStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        hosted_zone: route53.HostedZone,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating cloudfront certificate stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._hosted_zone = hosted_zone
        self._infra_context = infra_context

        self._cloudfront_certificate = self._create_cloudfront_certificate()

        logger.info(
            f"Cloudfront certificate stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def cloudfront_certificate_arn(self) -> str:
        return self._cloudfront_certificate.certificate_arn

    def _create_cloudfront_certificate(self) -> acm.Certificate:
        if self._infra_context.config.domain.cloudfront_certificate_arn:
            logger.info(
                f"Getting CloudFront certificate from ARN: {self._infra_context.config.domain.cloudfront_certificate_arn}"
            )
            cloudfront_certificate = acm.Certificate.from_certificate_arn(
                self,
                "CloudFrontCertificate",
                self._infra_context.config.domain.cloudfront_certificate_arn,
            )
        else:
            logger.info(
                f"Creating CloudFront certificate for domain: {self._infra_context.config.domain.zone_name}"
            )
            cloudfront_certificate = acm.Certificate(
                self,
                "CloudFrontCertificate",
                domain_name=self._infra_context.config.domain.zone_name,
                subject_alternative_names=[f"*.{self._infra_context.config.domain.zone_name}"],
                validation=acm.CertificateValidation.from_dns(self._hosted_zone),
            )
            # NOTE: Now we automatically delegate the certificate to the parent hosted zone, so we don't need to retain it
            # cloudfront_certificate.apply_removal_policy(RemovalPolicy.RETAIN)
        return cloudfront_certificate
