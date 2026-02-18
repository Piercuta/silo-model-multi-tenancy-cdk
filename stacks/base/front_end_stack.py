import logging

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from constructs import Construct

from config.loader import InfrastructureContext
from lib.angular_pipeline import AngularPipeline
from lib.front_end import FrontEnd

logger = logging.getLogger(__name__)


class FrontEndStack(Stack):
    """
    Stack containing the front end resources for the infrastructure.

    This stack creates the necessary front end resources for the infrastructure.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        hosted_zone: route53.HostedZone,
        cloudfront_certificate_arn: str,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating front end stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._hosted_zone = hosted_zone
        self._cloudfront_certificate_arn = cloudfront_certificate_arn
        self._infra_context = infra_context

        self._front_end = self._create_front_end()
        self._create_front_end_dns_record()
        # self._build_angular()

        logger.info(
            f"Front end stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    def _create_front_end(self) -> FrontEnd:
        logger.info("Creating front end...")
        front_end = FrontEnd(
            self,
            "FrontEnd",
            # alb=self._alb,
            cloudfront_certificate_arn=self._cloudfront_certificate_arn,
            front_end_config=self._infra_context.config.front_end,
            infra_context=self._infra_context,
        )
        logger.info("Front end created successfully")

        return front_end

    def _build_angular(self) -> None:
        logger.info("Building Angular...")
        angular_pipeline = AngularPipeline(
            self,
            "AngularPipeline",
            cloudfront_bucket_name=self._front_end.bucket.bucket_name,
            cloudfront_distribution_id=self._front_end.cloudfront_distribution.distribution_id,
            angular_build_config=self._infra_context.config.front_end.angular_build,
            infra_context=self._infra_context,
        )
        logger.info("Angular built successfully")
        return angular_pipeline

    def _create_front_end_dns_record(self) -> route53.RecordSet:
        logger.info("Creating front end DNS record...")
        record = route53.ARecord(
            self,
            "FrontEndDnsRecord",
            zone=self._hosted_zone,
            record_name=self._infra_context.config.domain.records["front_domain_name"],
            target=route53.RecordTarget.from_alias(
                targets.CloudFrontTarget(self._front_end.cloudfront_distribution)
            ),
            ttl=Duration.minutes(5),
        )

        CfnOutput(
            self,
            "OsdFrontRecord",
            value=self._infra_context.config.domain.records["front_domain_name"],
            description="OSD Front DNS record",
        )

        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self._front_end.cloudfront_distribution.distribution_id,
            description="CloudFront Distribution ID",
        )

        CfnOutput(
            self,
            "FrontEndBucketName",
            value=self._front_end.bucket.bucket_name,
            description="Frontend S3 Bucket Name",
        )

        logger.info("Front end DNS record created successfully")
        return record
