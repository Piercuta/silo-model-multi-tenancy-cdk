import logging

from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2  # Duration,
from constructs import Construct

from config.loader import InfrastructureContext
from lib.security_group import SecurityGroup

logger = logging.getLogger(__name__)


class SecurityStack(Stack):
    """
    Stack containing the security resources for the infrastructure.

    This stack creates the necessary security groups for the infrastructure.
    It also creates the necessary ingress rules for the infrastructure.
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
            f"Creating security stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._infra_context = infra_context
        self._vpc = vpc

        self._create_security_groups()
        self._create_ingress_rules()

        logger.info(
            f"Security stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def alb_sg(self) -> ec2.SecurityGroup:
        return self._alb_sg.sg

    @property
    def rds_sg(self) -> ec2.SecurityGroup:
        return self._rds_sg.sg

    @property
    def docdb_sg(self) -> ec2.SecurityGroup:
        return self._docdb_sg.sg

    @property
    def redis_sg(self) -> ec2.SecurityGroup:
        return self._redis_sg.sg

    @property
    def osd_api_sg(self) -> ec2.SecurityGroup:
        return self._osd_api_sg.sg

    @property
    def ecs_shared_sg(self) -> ec2.SecurityGroup:
        return self._ecs_shared_sg.sg

    @property
    def keycloak_sg(self) -> ec2.SecurityGroup:
        return self._keycloak_sg.sg

    @property
    def rds_lambda_sg(self) -> ec2.SecurityGroup:
        return self._rds_lambda_sg.sg

    @property
    def docdb_lambda_sg(self) -> ec2.SecurityGroup:
        return self._docdb_lambda_sg.sg

    def _create_security_groups(self) -> None:
        logger.info("Creating security groups")
        # Create security groups
        self._alb_sg = SecurityGroup(
            self,
            "AlbSg",
            security_group_name=self._infra_context.context.prefix("alb-sg"),
            vpc=self._vpc,
            allow_all_outbound=True,
        )

        self._rds_sg = SecurityGroup(
            self,
            "RdsSg",
            security_group_name=self._infra_context.context.prefix("rds-sg"),
            vpc=self._vpc,
            allow_all_outbound=True,
        )

        self._docdb_sg = SecurityGroup(
            self,
            "DocdbSg",
            security_group_name=self._infra_context.context.prefix("docdb-sg"),
            vpc=self._vpc,
            allow_all_outbound=True,
        )

        self._redis_sg = SecurityGroup(
            self,
            "RedisSg",
            security_group_name=self._infra_context.context.prefix("redis-sg"),
            vpc=self._vpc,
            allow_all_outbound=True,
        )

        self._osd_api_sg = SecurityGroup(
            self,
            "OsdApiSg",
            vpc=self._vpc,
            security_group_name=self._infra_context.context.prefix("osd-api-sg"),
            allow_all_outbound=True,
        )

        self._ecs_shared_sg = SecurityGroup(
            self,
            "EcsSharedSg",
            vpc=self._vpc,
            security_group_name=self._infra_context.context.prefix("ecs-shared-sg"),
            allow_all_outbound=True,
        )

        self._keycloak_sg = SecurityGroup(
            self,
            "KeycloakSg",
            vpc=self._vpc,
            security_group_name=self._infra_context.context.prefix("keycloak-sg"),
            allow_all_outbound=True,
        )

        self._rds_lambda_sg = SecurityGroup(
            self,
            "AuroraLambdaSg",
            vpc=self._vpc,
            security_group_name=self._infra_context.context.prefix("aurora-lambda-sg"),
            allow_all_outbound=True,
        )

        self._docdb_lambda_sg = SecurityGroup(
            self,
            "DocDBLambdaSg",
            vpc=self._vpc,
            security_group_name=self._infra_context.context.prefix("docdb-lambda-sg"),
            allow_all_outbound=True,
        )

        logger.info("Security groups created successfully")

    def _create_ingress_rules(self) -> None:
        logger.info("Creating ingress rules for security groups")
        # Create ingress rules
        # ALB ingress rules
        self.alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "Allow HTTP traffic from any IP address"
        )
        self.alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "Allow HTTPS traffic from any IP address"
        )

        # Aurora RDS ingress rules
        # self.rds_sg.add_ingress_rule(
        #     ec2.Peer.security_group_id(self.osd_api_sg.security_group_id),
        #     ec2.Port.tcp(3306),
        #     "Allow MySQL traffic from OSD API security group",
        # )

        # self.rds_sg.add_ingress_rule(
        #     self.keycloak_sg,
        #     ec2.Port.tcp(5432),
        #     "Allow PostgreSQL traffic from Keycloak security group",
        # )

        self.rds_sg.add_ingress_rule(
            self.keycloak_sg,
            ec2.Port.tcp(3306),
            "Allow MySQL traffic from Keycloak security group",
        )

        self.rds_sg.add_ingress_rule(
            self.rds_lambda_sg,
            ec2.Port.tcp(3306),
            "Allow MySQL traffic from Aurora Lambda security group",
        )

        # OSD API ingress rules
        self.osd_api_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(8080),
            "Allow HTTP traffic from ALB security group",
        )

        self.osd_api_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(2112),
            "Allow HTTP traffic from ALB security group",
        )
        logger.info("Ingress rules created successfully")

        # Keycloak ingress rules
        self.keycloak_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(8080),
            "Allow HTTP traffic from ALB security group",
        )
        self.keycloak_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(9000),
            "Allow HTTP traffic from ALB security group for target group health checks",
        )

        self.docdb_sg.add_ingress_rule(
            self.osd_api_sg,
            ec2.Port.tcp(27017),
            "Allow MongoDB traffic from OSD API security group",
        )

        self.docdb_sg.add_ingress_rule(
            self.docdb_lambda_sg,
            ec2.Port.tcp(27017),
            "Allow MongoDB traffic from DocDB Lambda security group",
        )

        self.redis_sg.add_ingress_rule(
            self.osd_api_sg,
            ec2.Port.tcp(6379),
            "Allow Redis traffic from OSD API security group",
        )

        self.ecs_shared_sg.add_ingress_rule(
            peer=self.ecs_shared_sg,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic within the same security group",
        )
