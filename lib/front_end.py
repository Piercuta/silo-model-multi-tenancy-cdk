import logging

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config.base_config import FrontEndConfig
from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class FrontEnd(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        cloudfront_certificate_arn: str,
        front_end_config: FrontEndConfig,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # self._alb = alb
        self._cloudfront_certificate_arn = cloudfront_certificate_arn
        self._front_end_config = front_end_config
        self._infra_context = infra_context

        logger.info("Creating front end...")
        logger.info(f"Front end parameters: {front_end_config}")

        self._bucket = self._create_get_bucket()
        self._cloudfront_distribution = self._create_cloudfront_distribution()
        logger.info("Front end created successfully")

    @property
    def cloudfront_distribution(self) -> cloudfront.Distribution:
        return self._cloudfront_distribution

    @property
    def bucket(self) -> s3.Bucket:
        return self._bucket

    def _create_get_bucket(self) -> s3.Bucket:
        if self._front_end_config.bucket_name:
            logger.info("Retrieving bucket...")
            bucket = s3.Bucket.from_bucket_name(
                self,
                "FrontEndBucket",
                self._front_end_config.bucket_name,
            )
            logger.info("Bucket retrieved successfully")
        else:
            logger.info("Creating bucket...")
            bucket = s3.Bucket(
                self,
                "FrontEndBucket",
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                encryption=s3.BucketEncryption.S3_MANAGED,
                enforce_ssl=True,
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,  # Automatically delete objects when bucket is deleted
            )
            logger.info("Bucket created successfully")
        return bucket

    def _create_cloudfront_distribution(self) -> cloudfront.Distribution:
        logger.info("Creating cloudfront distribution...")

        oac = cloudfront.S3OriginAccessControl(
            self, "FrontEndOAC", signing=cloudfront.Signing.SIGV4_NO_OVERRIDE
        )

        cors_policy = cloudfront.ResponseHeadersPolicy(
            self,
            "CorsPolicy",
            cors_behavior=cloudfront.ResponseHeadersCorsBehavior(
                access_control_allow_credentials=False,
                access_control_allow_headers=["*"],
                access_control_allow_methods=["GET", "HEAD", "OPTIONS"],
                access_control_allow_origins=["*"],
                origin_override=True,
            ),
            comment="Allow CORS from any origin",
        )

        alternate_domain_names = self._front_end_config.domain_names + [
            self._infra_context.config.domain.records["front_domain_name"]
        ]
        logger.info(f"Alternate domain names: {alternate_domain_names}")

        bucket_origin = origins.S3BucketOrigin.with_origin_access_control(
            self._bucket, origin_access_control=oac, origin_path="/osd"
        )
        # Create CloudFront Distribution
        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment=self._front_end_config.comment,
            default_behavior=cloudfront.BehaviorOptions(
                origin=bucket_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                compress=True,
                response_headers_policy=cors_policy,
            ),
            additional_behaviors={
                "index.html": cloudfront.BehaviorOptions(
                    origin=bucket_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                    compress=True,
                    response_headers_policy=cors_policy,
                ),
            },
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                )
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            domain_names=alternate_domain_names,
            certificate=acm.Certificate.from_certificate_arn(
                self, "ImportedCert", self._cloudfront_certificate_arn
            ),
        )
        if self._front_end_config.delivery_destination_arn:
            delivery_source = logs.CfnDeliverySource(
                self,
                "CloudfrontLogSource",
                name=f"cloudfront-log-source-{distribution.distribution_id}",
                resource_arn=distribution.distribution_arn,
                log_type="ACCESS_LOGS",
            )

            delivery = logs.CfnDelivery(
                self,
                "CloudfrontLogDelivery",
                delivery_source_name=delivery_source.name,
                delivery_destination_arn=self._front_end_config.delivery_destination_arn,
                # s3_enable_hive_compatible_path=FRCloudfrontConstants.HIVE_COMPATIBLE_PATH,
            )

            # Add dependencies to ensure proper resource creation order
            delivery.node.add_dependency(delivery_source)

        logger.info("Cloudfront distribution created successfully")
        return distribution
