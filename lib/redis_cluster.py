import logging
import re

from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticache as cache
from aws_cdk import aws_elasticache_alpha as elasticache
from constructs import Construct

from config.base_config import RedisConfig
from config.loader import Context

logger = logging.getLogger(__name__)


class RedisCluster(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        security_group: ec2.SecurityGroup,
        redis_config: RedisConfig,
        context: Context = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._redis_config = redis_config
        self._context = context
        self._vpc = vpc
        self._security_group = security_group

        logger.info("Creating Redis cluster...")
        logger.info(f"Redis cluster parameters: {self._redis_config}")

        if self._redis_config.serverless_cache_enabled:
            self._cluster = self._create_serverless_redis_cluster()
        else:
            self._cluster = self._create_redis_cluster()

        logger.info("Redis cluster created successfully")

    @property
    def redis_endpoint_address(self) -> str:
        if self._redis_config.serverless_cache_enabled:
            return self._cluster.serverless_cache_endpoint_address
        else:
            return self._cluster.attr_redis_endpoint_address

    def _generate_name(self) -> str:
        """
        Generate a deterministic short cache name (max 40 chars) based on tenant and environment.
        This ensures the name is stable across deployments for in-place updates.
        """
        # Generate: {tenant}-{env}-redis (truncated to 40 chars)
        tenant = self._context.tenant_name.lower()[:10]  # Limit tenant to 10 chars
        env = self._context.env_name.lower()[:3]  # Limit env to 3 chars
        name = f"{tenant}-{env}-redis"

        # Truncate to 40 chars
        name = name[:40]

        # Replace invalid characters with '-'
        name = re.sub(r"[^a-z0-9-]", "-", name)

        # Remove trailing hyphens
        name = name.rstrip("-")

        # Remove leading hyphens
        name = name.lstrip("-")

        # Replace double hyphens with single ones
        while "--" in name:
            name = name.replace("--", "-")

        # Ensure it starts with a letter (AWS requirement)
        if not name or not name[0].isalpha():
            name = "a" + name

        # Truncate again after cleanup (in case we added 'a')
        return name[:40]

    def _create_serverless_redis_cluster(self) -> elasticache.ServerlessCache:
        redis_cache = elasticache.ServerlessCache(
            self,
            "ServerlessRedisCluster",
            vpc=self._vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=self._vpc.isolated_subnets),
            security_groups=[self._security_group],
            engine=elasticache.CacheEngine.REDIS_LATEST,
            serverless_cache_name=self._redis_config.serverless_cache_name or self._generate_name(),
            backup=elasticache.BackupSettings(
                backup_retention_limit=self._redis_config.backup_retention,
                # backup_arns_to_restore=self._redis_config.backup_arns_to_restore,
                # backup_name_before_deletion=""
            ),
        )

        return redis_cache

    def _create_redis_cluster(self) -> cache.CfnCacheCluster:
        subnet_group = cache.CfnSubnetGroup(
            self,
            "RedisSubnetGroup",
            description="Redis Subnet Group for Redis Cluster",
            subnet_ids=self._vpc.select_subnets(subnets=self._vpc.isolated_subnets).subnet_ids,
        )

        redis_cache = cache.CfnCacheCluster(
            self,
            "RedisCluster",
            cache_node_type=self._redis_config.cache_node_type,
            engine="redis",
            cluster_name=self._generate_name(),
            num_cache_nodes=self._redis_config.num_cache_nodes,
            cache_subnet_group_name=subnet_group.ref,
            cache_parameter_group_name=self._redis_config.cache_parameter_group_name,
            engine_version=self._redis_config.cache_engine_version,
            port=6379,
            vpc_security_group_ids=[self._security_group.security_group_id],
            transit_encryption_enabled=False,
        )

        return redis_cache
