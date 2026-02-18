import logging
from typing import Optional

import boto3
from aws_cdk import CfnOutput, Duration, SecretValue, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

from config.loader import InfrastructureContext
from lib.alb_https_target_group import AlbHttpsTargetGroup
from lib.ecs_cluster import EcsCluster
from lib.ecs_service import EcsService
from utils.naming import to_pascal

logger = logging.getLogger(__name__)


class ApplicationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        # Security groups
        alb_sg: ec2.SecurityGroup,
        ecs_shared_sg: ec2.SecurityGroup,
        osd_api_sg: ec2.SecurityGroup,
        keycloak_sg: ec2.SecurityGroup,
        # Storage outputs
        osd_storage_bucket_name: str,
        # Database outputs
        docdb_cluster_endpoint: str,
        docdb_cluster_port: str,
        docdb_cluster_secret_arn: str,
        redis_cluster_endpoint: str,
        aurora_cluster_secret: sm.Secret,
        aurora_cluster_jdbc_url: str,
        # domain outputs
        hosted_zone: route53.HostedZone,
        alb_certificate_arn: str,
        # Config
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating application stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._vpc = vpc
        # Security groups
        self._alb_sg = alb_sg
        self._osd_api_sg = osd_api_sg
        self._ecs_shared_sg = ecs_shared_sg
        self._keycloak_sg = keycloak_sg
        # Database outputs
        self._docdb_cluster_endpoint = docdb_cluster_endpoint
        self._docdb_cluster_port = docdb_cluster_port
        self._docdb_cluster_secret_arn = docdb_cluster_secret_arn
        self._redis_cluster_endpoint = redis_cluster_endpoint
        self._aurora_cluster_secret = aurora_cluster_secret
        self._aurora_cluster_jdbc_url = aurora_cluster_jdbc_url
        # Storage outputs
        self._osd_storage_bucket_name = osd_storage_bucket_name
        # certificate outputs
        self._alb_certificate_arn = alb_certificate_arn
        self._hosted_zone = hosted_zone
        # Config
        self._infra_context = infra_context

        self._alb_https_target_group = self._create_alb_https_target_group()
        self._create_application_dns_records()
        self._ecs_cluster = self._create_ecs_cluster()
        self._secret = self._retrieve_ecs_secret()
       
        self._ecs_services = self._create_ecs_services()

        logger.info(
            f"Application stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def ecs_cluster(self) -> ecs.Cluster:
        return self._ecs_cluster.cluster

    def _create_alb_https_target_group(self) -> AlbHttpsTargetGroup:
        return AlbHttpsTargetGroup(
            self,
            "AlbHttpsTargetGroup",
            vpc=self._vpc,
            security_group=self._alb_sg,
            alb_config=self._infra_context.config.alb,
            alb_certificate_arn=self._alb_certificate_arn,
            domain_config=self._infra_context.config.domain,
            infra_context=self._infra_context,
        )

    def _create_ecs_cluster(self) -> EcsCluster:
        return EcsCluster(
            self,
            "EcsCluster",
            vpc=self._vpc,
            ecs_cluster_config=self._infra_context.config.ecs_cluster,
            infra_context=self._infra_context,
        )

    def _create_keycloak_service(self) -> EcsService:
        keycloak_service_config = self._infra_context.config.ecs_services.get("keycloak")

        secrets = {
            "KC_DB_USERNAME": ecs.Secret.from_secrets_manager(
                self._aurora_cluster_secret, "username"
            ),
            "KC_DB_PASSWORD": ecs.Secret.from_secrets_manager(
                self._aurora_cluster_secret, "password"
            ),
            "KC_BOOTSTRAP_ADMIN_PASSWORD": ecs.Secret.from_secrets_manager(
                self._secret,
                "KC_BOOTSTRAP_ADMIN_PASSWORD",
            ),
            "OSD_REALM_USERS_OSD_ADMIN_SECRET_DATA_SALT": ecs.Secret.from_secrets_manager(
                self._secret,
                "OSD_REALM_USERS_OSD_ADMIN_SECRET_DATA_SALT",
            ),
            "OSD_REALM_USERS_OSD_ADMIN_SECRET_DATA_VAULT": ecs.Secret.from_secrets_manager(
                self._secret,
                "OSD_REALM_USERS_OSD_ADMIN_SECRET_DATA_VAULT",
            ),
            "OSD_REALM_SMTP_SERVER_USER": ecs.Secret.from_secrets_manager(
                self._secret,
                "OSD_REALM_SMTP_SERVER_USER",
            ),
            "OSD_REALM_SMTP_SERVER_PASSWORD": ecs.Secret.from_secrets_manager(
                self._secret,
                "OSD_REALM_SMTP_SERVER_PASSWORD",
            ),
            "OSD_REALM_OSD_CLIENT_CLIENT_SECRET": ecs.Secret.from_secrets_manager(
                self._secret,
                "OSD_REALM_OSD_CLIENT_CLIENT_SECRET",
            ),
            "MASTER_REALM_IDP_CLIENT_SECRET": ecs.Secret.from_secrets_manager(
                self._secret,
                "MASTER_REALM_IDP_CLIENT_SECRET",
            ),
            "MASTER_REALM_SMTP_SERVER_USER": ecs.Secret.from_secrets_manager(
                self._secret,
                "MASTER_REALM_SMTP_SERVER_USER",
            ),
            "MASTER_REALM_SMTP_SERVER_PASSWORD": ecs.Secret.from_secrets_manager(
                self._secret,
                "MASTER_REALM_SMTP_SERVER_PASSWORD",
            ),
        }
        logger.info("Adding secrets to KeycloakService...")

        additional_environment = {
            "KC_DB_URL": self._aurora_cluster_jdbc_url,
            "KC_HOSTNAME": self._infra_context.config.domain.records["sso_domain_name"],
            "KC_HEALTH_ENABLED": "true",
            "OSD_REALM_ATTRIBUTES_SSO_URL": f"https://{self._infra_context.config.domain.records['front_domain_name']}",
            "OSD_REALM_ATTRIBUTES_FRONTEND_URL": f"https://{self._infra_context.config.domain.records['sso_domain_name']}",
            "OSD_REALM_OSD_CLIENT_ROOT_URL": f"https://{self._infra_context.config.domain.records['api_domain_name']}",
            "OSD_REALM_OSD_CLIENT_REDIRECT_URI_1": f"https://{self._infra_context.config.domain.records['api_domain_name']}/*",
            "OSD_REALM_OSD_CLIENT_REDIRECT_URI_2": f"https://{self._infra_context.config.domain.records['front_domain_name']}/*",
            "OSD_REALM_OSD_CLIENT_ATTRIBUTES_POST_LOGOUT_REDIRECT_URIS": f"https://{self._infra_context.config.domain.records['front_domain_name']}/*##https://{self._infra_context.config.domain.records['api_domain_name']}/*##https://{self._infra_context.config.domain.records['sso_domain_name']}/*",
            "OSD_REALM_OSD_CLIENT_ADMIN_URL": f"https://{self._infra_context.config.domain.records['front_domain_name']}",
            "OSD_REALM_OSD_CLIENT_BASE_URL": f"https://{self._infra_context.config.domain.records['front_domain_name']}",
            "OSD_REALM_OSD_CLIENT_WEB_ORIGIN_1": f"https://{self._infra_context.config.domain.records['front_domain_name']}",
            "OSD_REALM_OSD_CLIENT_WEB_ORIGIN_2": f"https://{self._infra_context.config.domain.records['sso_domain_name']}",
        }
        logger.info(f"Adding additional environment to KeycloakService: {additional_environment}")

        keycloak_ecs_service = EcsService(
            self,
            "KeycloakService",
            vpc=self._vpc,
            security_groups=[self._keycloak_sg, self._ecs_shared_sg],
            ecs_cluster=self.ecs_cluster,
            secrets=secrets,
            additional_environment=additional_environment,
            ecs_service_config=keycloak_service_config,
        )
        logger.info(
            f"Attaching KeycloakService to ALB HTTPS Target Group: {self._alb_https_target_group.target_group_keycloak.target_group_arn}"
        )
        # NOTE: Attach KeycloakService to ALB HTTPS Target Group this way to avoid useless ingress rules in shared security group
        cfn_service = keycloak_ecs_service.service.node.default_child
        cfn_service.load_balancers = [
            ecs.CfnService.LoadBalancerProperty(
                container_name=keycloak_service_config.containers[0].container_name,
                container_port=keycloak_service_config.containers[0]
                .port_mappings[0]
                .container_port,
                target_group_arn=self._alb_https_target_group.target_group_keycloak.target_group_arn,
            )
        ]
        # NOTE: Add dependency between KeycloakService and ALB HTTPS Target Group HTTPS Listener to avoid service creation before listener and target group are linked
        cfn_service.node.add_dependency(self._alb_https_target_group.https_listener)
        # NOTE: Retest this method with target group https and port 9000
        # keycloak_ecs_service.service.attach_to_application_target_group(
        #     self._alb_https_target_group.target_group_keycloak,
        # )
        logger.info(
            f"KeycloakService created successfully with ARN: {keycloak_ecs_service.service_arn} "
        )
        return keycloak_ecs_service

    def _create_osd_api_service(self) -> EcsService:
        osd_api_service_config = self._infra_context.config.ecs_services.get("osd_api")

        secrets = {
            "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET": ecs.Secret.from_secrets_manager(
                self._secret,
                "OSD_REALM_OSD_CLIENT_CLIENT_SECRET",
            ),
        }
        logger.info("Adding secrets to OsdApiService...")

        additionnal_environment = {
            "DOCUMENTDB_PORT": self._docdb_cluster_port,
            "DOCUMENTDB_HOST": self._docdb_cluster_endpoint,
            "DOCUMENTDB_SECRET_ID": self._docdb_cluster_secret_arn,
            "S3_OSD_BUCKET": self._osd_storage_bucket_name,
            "S3_OSD_REGION": self._infra_context.config.aws.region_str,
            "SPRING_DATA_REDIS_HOST": self._redis_cluster_endpoint,
            "OSD_PLUGINS_AWS_CLOUD_SERVICES_REGION": self._infra_context.config.aws.region_str,
            "SSO_FRONT_END_URL": f"https://{self._infra_context.config.domain.records['front_domain_name']}",
            "SSO_APP_ROOT_URL": f"https://{self._infra_context.config.domain.records['api_domain_name']}",
            "SSO_LOGOUT_URL": f"https://{self._infra_context.config.domain.records['sso_domain_name']}/realms/osd/protocol/openid-connect/logout",
            "OSD_SPA_FRONT_END_URL": f"https://{self._infra_context.config.domain.records['front_domain_name']}",
            "OSD_SETTINGS_CMS_URL": f"https://{self._infra_context.config.domain.records['api_domain_name']}",
            "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI": f"https://{self._infra_context.config.domain.records['sso_domain_name']}/realms/osd",
        }
        logger.info(f"Adding additional environment to OsdApiService: {additionnal_environment}")

        if self._get_parameter_store_value("OsdApi"):
            ecr_image_osd_api_uri = self._get_parameter_store_value("OsdApi")
        else:
            ecr_image_osd_api_uri = self.node.try_get_context("ecr_image_osd_api_uri")
        logger.info(f"Osd Api ecr image uri: {ecr_image_osd_api_uri}")

        osd_api_ecs_service = EcsService(
            self,
            "OsdApiService",
            vpc=self._vpc,
            security_groups=[self._osd_api_sg, self._ecs_shared_sg],
            ecs_cluster=self.ecs_cluster,
            additional_environment=additionnal_environment,
            ecs_service_config=osd_api_service_config,
            secrets=secrets,
            ecr_image_uri=ecr_image_osd_api_uri,
        )
        logger.info(
            f"Attaching OsdApiService to ALB HTTPS Target Group: {self._alb_https_target_group.target_group_osd_api.target_group_arn}"
        )
        # NOTE: Attach OsdApiService to ALB HTTPS Target Group this way to avoid useless ingress rules in shared security group
        cfn_service = osd_api_ecs_service.service.node.default_child
        cfn_service.load_balancers = [
            ecs.CfnService.LoadBalancerProperty(
                container_name=osd_api_service_config.containers[0].container_name,
                container_port=osd_api_service_config.containers[0].port_mappings[0].container_port,
                target_group_arn=self._alb_https_target_group.target_group_osd_api.target_group_arn,
            )
        ]
        # NOTE: Add dependency between OsdApiService and ALB HTTPS Target Group HTTPS Listener to avoid service creation before listener and target group are linked
        cfn_service.node.add_dependency(self._alb_https_target_group.https_listener)
        # osd_api_ecs_service.service.attach_to_application_target_group(
        #     self._alb_https_target_group.target_group_osd_api,
        # )
        logger.info(
            f"OsdApiService created successfully with ARN: {osd_api_ecs_service.service_arn} "
        )

        return osd_api_ecs_service

    def _create_ecs_services(self):
        # Check if ecs_services exists
        if not self._infra_context.config.ecs_services:
            logger.warning("No ECS services configured, skipping service creation")
            return
        ecs_services = {}
        keycloak_active = self._infra_context.config.ecs_services.get("keycloak")
        if keycloak_active:
            ecs_services["keycloak"] = self._create_keycloak_service()
            # NOTE: Add dependency between KeycloakService and ECS Cluster to avoid stack destroy failed cause capacity provider strategy is not removed
            ecs_services["keycloak"].node.add_dependency(self._ecs_cluster)
        ecs_services["osd_api"] = self._create_osd_api_service()

        logger.info(f"Creating Fonto ECS services: {self._infra_context.config.ecs_services}")
        for service_name, service_config in self._infra_context.config.ecs_services.items():
            if service_name in ["osd_api", "keycloak"]:
                continue
            ecs_service = EcsService(
                self,
                f"{to_pascal(service_name)}Service",
                vpc=self._vpc,
                security_groups=[self._ecs_shared_sg],
                ecs_cluster=self.ecs_cluster,
                ecs_service_config=service_config,
            )
            logger.info(
                f"{to_pascal(service_name)}Service created successfully with ARN: {ecs_service.service_arn} "
            )
            ecs_services[service_name] = ecs_service

        # NOTE: Service Connect deployment order
        #
        # ECS Service Connect populates /etc/hosts at task creation time.
        # Each service only sees services registered BEFORE it in the Cloud Map namespace.
        # Dependencies ensure the correct deployment order so all services can communicate.
        #
        #   ┌───────────┐     ┌────────┐
        #   │ keycloak  │     │  xslt  │
        #   └─────┬─────┘     └───┬────┘
        #         │               │
        #         └───────┬───────┘
        #                 ▼
        #          ┌─────────────┐
        #          │   osd-api   │
        #          └──────┬──────┘
        #                 │
        #     ┌───────────┼───────────┐
        #     ▼           ▼           ▼
        # ┌────────┐ ┌────────┐ ┌──────────┐
        # │ review │ │ content│ │ document │
        # │        │ │quality │ │ history  │
        # └────────┘ └────────┘ └──────────┘
        #
        if keycloak_active:
            ecs_services["osd_api"].node.add_dependency(ecs_services["keycloak"])

        if "xslt" in ecs_services:
            ecs_services["osd_api"].node.add_dependency(ecs_services["xslt"])

        for service_name in ecs_services:
            if service_name not in ["osd_api", "keycloak", "xslt"]:
                ecs_services[service_name].node.add_dependency(ecs_services["osd_api"])

        return ecs_services

    def _create_application_dns_records(self):
        logger.info("Creating application DNS records")
        # Create OSD API DNS records
        route53.CnameRecord(
            self,
            "ApiDnsRecord",
            zone=self._hosted_zone,
            record_name=self._infra_context.config.domain.records["api_domain_name"],
            domain_name=self._alb_https_target_group.alb_dns_name,
            ttl=Duration.minutes(5),
        )
        logger.info("Application DNS records created successfully")

        # Create Keycloak DNS records
        route53.CnameRecord(
            self,
            "KeycloakDnsRecord",
            zone=self._hosted_zone,
            record_name=self._infra_context.config.domain.records["sso_domain_name"],
            domain_name=self._alb_https_target_group.alb_dns_name,
            ttl=Duration.minutes(5),
        )

        CfnOutput(
            self,
            "OsdApiRecord",
            value=self._infra_context.config.domain.records["api_domain_name"],
            description="OSD API DNS record",
        )
        CfnOutput(
            self,
            "KeycloakRecord",
            value=self._infra_context.config.domain.records["sso_domain_name"],
            description="Keycloak DNS record",
        )
        logger.info("Application DNS records created successfully")

    def _retrieve_ecs_secret(self) -> sm.Secret:
        arn = self._infra_context.config.secrets.secret_ecs_complete_arn
        ctx = self._infra_context.context

        if ctx.env_name not in arn or ctx.tenant_name not in arn:
            raise ValueError(
                f"Secret ARN '{arn}' does not contain expected environment "
                f"('{ctx.env_name}') and/or tenant ('{ctx.tenant_name}'). "
                "The secret naming is likely incorrect."
            )

        logger.info(f"Retrieving ECS secret from ARN: {arn}")
        secret = sm.Secret.from_secret_complete_arn(
            self,
            "EcsSecret",
            secret_complete_arn=self._infra_context.config.secrets.secret_ecs_complete_arn,
        )
        return secret

    def _get_parameter_store_value(self, service_name: str) -> Optional[str]:
        # NOTE: get the default session.
        # should be located in the main account and region (it-ops, eu-west-1)
        client_ssm = boto3.client("ssm")
        tenant_name = self._infra_context.context.tenant_name.capitalize()
        env_name = self._infra_context.context.env_name.capitalize()
        parameter_name = f"/Osd/{service_name}/{tenant_name}/{env_name}/EcrImageUri"
        try:
            res = client_ssm.get_parameter(Name=parameter_name)
            logger.info(f"{parameter_name} value: {res['Parameter']['Value']}")
            return res["Parameter"]["Value"]
        except Exception as e:
            logger.info(f"Error while retrieveing parameter from SSM: {parameter_name} - {e}")
            return None
