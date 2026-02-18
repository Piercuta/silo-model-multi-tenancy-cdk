import logging

from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

from config.loader import InfrastructureContext
from lib.aurora_cluster import AuroraCluster
from lib.docdb_cluster import DocDBCluster
from lib.redis_cluster import RedisCluster

logger = logging.getLogger(__name__)


class DatabaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        doc_db_security_group: ec2.SecurityGroup,
        docdb_lambda_security_group: ec2.SecurityGroup,
        redis_security_group: ec2.SecurityGroup,
        rds_lambda_security_group: ec2.SecurityGroup,
        aurora_security_group: ec2.SecurityGroup,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating database stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._vpc = vpc
        self._doc_db_security_group = doc_db_security_group
        self._docdb_lambda_security_group = docdb_lambda_security_group
        self._redis_security_group = redis_security_group
        self._rds_lambda_security_group = rds_lambda_security_group
        self._aurora_security_group = aurora_security_group
        self._infra_context = infra_context

        self._docdb_cluster = self._create_docdb_cluster()
        self._redis_cluster = self._create_redis_cluster()
        self._aurora_cluster = self._create_aurora_cluster()

        logger.info(
            f"Database stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def docdb_cluster_endpoint(self) -> str:
        return self._docdb_cluster.cluster.cluster_endpoint.hostname

    @property
    def docdb_cluster_port(self) -> str:
        return str(self._docdb_cluster.cluster.cluster_endpoint.port)

    @property
    def docdb_cluster_secret_arn(self) -> str:
        return self._docdb_cluster.secret_arn

    @property
    def redis_cluster_endpoint(self) -> str:
        return self._redis_cluster.redis_endpoint_address

    @property
    def aurora_cluster_secret(self) -> sm.Secret:
        return self._aurora_cluster.secret

    @property
    def aurora_cluster_jdbc_url(self) -> str:
        return self._aurora_cluster.jdbc_url

    def _create_docdb_cluster(self) -> DocDBCluster:
        return DocDBCluster(
            self,
            "DocDBCluster",
            vpc=self._vpc,
            security_group=self._doc_db_security_group,
            docdb_lambda_security_group=self._docdb_lambda_security_group,
            docdb_config=self._infra_context.config.docdb,
        )

    def _create_redis_cluster(self) -> RedisCluster:
        return RedisCluster(
            self,
            "RedisCluster",
            vpc=self._vpc,
            security_group=self._redis_security_group,
            redis_config=self._infra_context.config.redis,
            context=self._infra_context.context,
        )

    def _create_aurora_cluster(self) -> AuroraCluster:
        return AuroraCluster(
            self,
            "AuroraCluster",
            vpc=self._vpc,
            security_group=self._aurora_security_group,
            rds_lambda_security_group=self._rds_lambda_security_group,
            aurora_cluster_config=self._infra_context.config.aurora_cluster,
        )
