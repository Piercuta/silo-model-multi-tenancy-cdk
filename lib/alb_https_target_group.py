import logging

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config.base_config import AlbConfig, DomainConfig
from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class AlbHttpsTargetGroup(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        security_group: ec2.SecurityGroup,
        alb_certificate_arn: str,
        alb_config: AlbConfig,
        domain_config: DomainConfig,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._vpc = vpc
        self._security_group = security_group
        self._alb_config = alb_config
        self._alb_certificate_arn = alb_certificate_arn
        self._domain_config = domain_config
        self._infra_context = infra_context
        logger.info("Creating ALB HTTPS target group...")
        self._log_bucket = self._create_log_bucket()
        self._alb = self._create_load_balancer()
        self._target_group_osd_api = self._create_target_group_osd_api()
        self._target_group_keycloak = self._create_target_group_keycloak()
        self._create_listeners()
        self._enable_access_logs()
        self._enable_connection_logs()
        if self._alb_config.enable_log_replication:
            self._configure_log_replication()
        logger.info("ALB HTTPS target group created successfully")

    @property
    def target_group_osd_api(self) -> elbv2.ApplicationTargetGroup:
        return self._target_group_osd_api

    @property
    def target_group_keycloak(self) -> elbv2.ApplicationTargetGroup:
        return self._target_group_keycloak

    @property
    def alb_dns_name(self) -> str:
        return self._alb.load_balancer_dns_name

    @property
    def log_bucket(self) -> s3.IBucket:
        return self._log_bucket

    @property
    def https_listener(self) -> elbv2.ApplicationListener:
        return self._https_listener

    def _create_log_bucket(self) -> s3.IBucket:
        """Create or retrieve S3 bucket for ALB access logs."""

        logger.info("Creating log bucket...")

        # Versioning is required for S3 cross-account replication
        enable_versioning = self._alb_config.enable_log_replication

        lifecycle_rules = [
            s3.LifecycleRule(
                id="DeleteOldLogs",
                expiration=Duration.days(90),
                enabled=True,
            ),
        ]
        # When versioning is enabled, expire noncurrent versions to avoid storage bloat
        if enable_versioning:
            lifecycle_rules.append(
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True,
                )
            )

        bucket = s3.Bucket(
            self,
            "AlbLogBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=enable_versioning,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,  # Automatically delete objects when bucket is deleted
            lifecycle_rules=lifecycle_rules,
        )
        logger.info("Log bucket created successfully")
        return bucket

    def _create_load_balancer(self):
        if self._alb_config.internet_facing:
            vpc_subnets = ec2.SubnetSelection(subnets=self._vpc.public_subnets)
        else:
            vpc_subnets = ec2.SubnetSelection(subnets=self._vpc.private_subnets)

        return elbv2.ApplicationLoadBalancer(
            self,
            "ALB",
            vpc=self._vpc,
            vpc_subnets=vpc_subnets,
            security_group=self._security_group,
            internet_facing=self._alb_config.internet_facing,
        )

    def _create_target_group_osd_api(self):
        target_group = elbv2.ApplicationTargetGroup(
            self,
            "TargetGroupOsdApi",
            vpc=self._vpc,
            port=self._alb_config.target_group_osd_api.port,
            protocol=elbv2.ApplicationProtocol(self._alb_config.target_group_osd_api.protocol),
            target_type=elbv2.TargetType.IP,
            deregistration_delay=Duration.seconds(
                self._alb_config.target_group_osd_api.deregistration_delay
            ),
            health_check=elbv2.HealthCheck(
                enabled=True,
                path=self._alb_config.target_group_osd_api.health_check.path,
                port=self._alb_config.target_group_osd_api.health_check.port,
                protocol=elbv2.Protocol(
                    self._alb_config.target_group_osd_api.health_check.protocol
                ),
                interval=Duration.seconds(
                    self._alb_config.target_group_osd_api.health_check.interval
                ),
                healthy_threshold_count=self._alb_config.target_group_osd_api.health_check.retries,
                unhealthy_threshold_count=self._alb_config.target_group_osd_api.health_check.retries,
                timeout=Duration.seconds(
                    self._alb_config.target_group_osd_api.health_check.timeout
                ),
                healthy_http_codes=self._alb_config.target_group_osd_api.health_check.success_codes,
            ),
            stickiness_cookie_duration=Duration.days(7),
        )

        return target_group

    def _create_target_group_keycloak(self):
        target_group = elbv2.ApplicationTargetGroup(
            self,
            "TargetGroupKeycloak",
            vpc=self._vpc,
            port=self._alb_config.target_group_keycloak.port,
            protocol=elbv2.ApplicationProtocol(self._alb_config.target_group_keycloak.protocol),
            target_type=elbv2.TargetType.IP,
            deregistration_delay=Duration.seconds(
                self._alb_config.target_group_osd_api.deregistration_delay
            ),
            health_check=elbv2.HealthCheck(
                enabled=True,
                path=self._alb_config.target_group_keycloak.health_check.path,
                port=self._alb_config.target_group_keycloak.health_check.port,
                protocol=elbv2.Protocol(
                    self._alb_config.target_group_keycloak.health_check.protocol
                ),
                interval=Duration.seconds(
                    self._alb_config.target_group_keycloak.health_check.interval
                ),
                healthy_threshold_count=self._alb_config.target_group_keycloak.health_check.retries,
                unhealthy_threshold_count=self._alb_config.target_group_keycloak.health_check.retries,
                timeout=Duration.seconds(
                    self._alb_config.target_group_keycloak.health_check.timeout
                ),
                healthy_http_codes=self._alb_config.target_group_keycloak.health_check.success_codes,
            ),
            stickiness_cookie_duration=Duration.days(7),
        )

        return target_group

    def _create_listeners(self):
        self._http_listener = self._alb.add_listener(
            "HTTPListener",
            port=80,
            open=True,
        )

        # configure http redirect to htps
        self._http_listener.add_action(
            "RedirectToHTTPS",
            action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True,
            ),
        )

        self._https_listener = self._alb.add_listener(
            "HTTPSListener",
            port=443,
            open=True,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificates=[
                acm.Certificate.from_certificate_arn(
                    self, "ImportedCertificate", self._alb_certificate_arn
                )
            ],
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404, content_type="text/plain", message_body="Not Found"
            ),
            ssl_policy=elbv2.SslPolicy.RECOMMENDED_TLS,
        )

        self._https_listener.add_action(
            "OsdApiRule",
            priority=1,
            conditions=[
                elbv2.ListenerCondition.host_headers(
                    [self._domain_config.records["api_domain_name"]]
                )
            ],
            action=elbv2.ListenerAction.forward([self._target_group_osd_api]),
        )

        if self._infra_context.context.env_name in ["dev"]:
            self._https_listener.add_action(
                "KeycloakRuleSourceIps",
                priority=3,
                conditions=[
                    elbv2.ListenerCondition.host_headers(
                        [self._domain_config.records["sso_domain_name"]]
                    ),
                    elbv2.ListenerCondition.source_ips(
                        values=[
                            "194.230.73.32/29",  # contains office and vpn ips
                            "194.158.244.90/32",
                            "212.203.79.34/32",
                            "194.158.251.199/32",
                        ],
                    ),
                ],
                action=elbv2.ListenerAction.forward([self._target_group_keycloak]),
            )

            eips = []
            for subnet in self._vpc.public_subnets:
                eip = subnet.node.try_find_child("EIP")
                if eip is not None:
                    eips.append(f"{eip.attr_public_ip}/32")
            if eips:
                self._https_listener.add_action(
                    "KeycloakRuleSourceIpsNatEip",
                    priority=4,
                    conditions=[
                        elbv2.ListenerCondition.host_headers(
                            [self._domain_config.records["sso_domain_name"]]
                        ),
                        elbv2.ListenerCondition.source_ips(
                            values=eips,
                        ),
                    ],
                    action=elbv2.ListenerAction.forward([self._target_group_keycloak]),
                )

            self._https_listener.add_action(
                "KeycloakDenyOthers",
                priority=99,
                conditions=[
                    elbv2.ListenerCondition.host_headers(
                        [self._domain_config.records["sso_domain_name"]]
                    ),
                ],
                action=elbv2.ListenerAction.fixed_response(
                    status_code=403,
                    content_type="text/plain",
                    message_body="Forbidden",
                ),
            )
        else:
            self._https_listener.add_action(
                "KeycloakRule",
                priority=2,
                conditions=[
                    elbv2.ListenerCondition.host_headers(
                        [self._domain_config.records["sso_domain_name"]]
                    )
                ],
                action=elbv2.ListenerAction.forward([self._target_group_keycloak]),
            )
        logger.info(
            f"Created listeners: {self._http_listener.listener_arn} and {self._https_listener.listener_arn}"
        )

    def _enable_access_logs(self):
        """Enable access logs for the ALB to S3 bucket."""
        logger.info("Enabling ALB access logs...")

        # Grant permissions to ALB service to write logs to the bucket
        self._log_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("elasticloadbalancing.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{self._log_bucket.bucket_arn}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control",
                    }
                },
            )
        )

        # Enable access logs on the ALB
        self._alb.log_access_logs(
            bucket=self._log_bucket,
            prefix="osd/alb-access-logs",
        )

        logger.info("ALB access logs enabled successfully")

    def _enable_connection_logs(self):
        """Enable connection logs for the ALB listeners to S3 bucket."""
        logger.info("Enabling ALB connection logs...")

        self._alb.log_connection_logs(
            bucket=self._log_bucket,
            prefix="osd/alb-connection-logs",
        )

        logger.info("ALB connection logs enabled successfully")

    def _configure_log_replication(self):
        """Configure S3 cross-account replication of ALB logs to the monitoring bucket.

        Replicates objects under prefixes:
        - osd/alb-access-logs
        - osd/alb-connection-logs

        Destination: s3://alb-logs-monitoring-org (account 000000000000)
        """
        logger.info("Configuring ALB log replication to monitoring account...")

        destination_bucket_arn = "arn:aws:s3:::alb-logs-monitoring-org"
        destination_account_id = "000000000000"

        # IAM role for S3 replication service
        replication_role = iam.Role(
            self,
            "AlbLogReplicationRole",
            assumed_by=iam.ServicePrincipal("s3.amazonaws.com"),
            description="Role for ALB log bucket replication to monitoring account",
        )

        # Source bucket permissions
        replication_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetReplicationConfiguration",
                    "s3:ListBucket",
                ],
                resources=[self._log_bucket.bucket_arn],
            )
        )
        replication_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObjectVersion",
                    "s3:GetObjectVersionForReplication",
                    "s3:GetObjectVersionAcl",
                    "s3:GetObjectVersionTagging",
                ],
                resources=[f"{self._log_bucket.bucket_arn}/*"],
            )
        )

        # Destination bucket permissions
        replication_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:ReplicateObject",
                    "s3:ReplicateDelete",
                    "s3:ReplicateTags",
                    "s3:ObjectOwnerOverrideToBucketOwner",
                ],
                resources=[f"{destination_bucket_arn}/*"],
            )
        )

        # Configure replication rules on the underlying CfnBucket
        cfn_bucket = self._log_bucket.node.default_child
        if isinstance(cfn_bucket, s3.CfnBucket):
            cfn_bucket.replication_configuration = s3.CfnBucket.ReplicationConfigurationProperty(
                role=replication_role.role_arn,
                rules=[
                    s3.CfnBucket.ReplicationRuleProperty(
                        id="ReplicateAccessLogs",
                        priority=1,
                        filter=s3.CfnBucket.ReplicationRuleFilterProperty(
                            prefix="osd/alb-access-logs",
                        ),
                        status="Enabled",
                        delete_marker_replication=s3.CfnBucket.DeleteMarkerReplicationProperty(
                            status="Disabled"
                        ),
                        destination=s3.CfnBucket.ReplicationDestinationProperty(
                            bucket=destination_bucket_arn,
                            account=destination_account_id,
                            access_control_translation=s3.CfnBucket.AccessControlTranslationProperty(
                                owner="Destination"
                            ),
                        ),
                    ),
                    s3.CfnBucket.ReplicationRuleProperty(
                        id="ReplicateConnectionLogs",
                        priority=2,
                        filter=s3.CfnBucket.ReplicationRuleFilterProperty(
                            prefix="osd/alb-connection-logs",
                        ),
                        status="Enabled",
                        delete_marker_replication=s3.CfnBucket.DeleteMarkerReplicationProperty(
                            status="Disabled"
                        ),
                        destination=s3.CfnBucket.ReplicationDestinationProperty(
                            bucket=destination_bucket_arn,
                            account=destination_account_id,
                            access_control_translation=s3.CfnBucket.AccessControlTranslationProperty(
                                owner="Destination"
                            ),
                        ),
                    ),
                ],
            )

        logger.info("ALB log replication configured successfully")
