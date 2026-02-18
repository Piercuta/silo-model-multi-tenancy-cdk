import logging

from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from constructs import Construct

from config.base_config import EcsClusterConfig
from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class EcsCluster(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        ecs_cluster_config: EcsClusterConfig,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._vpc = vpc
        self._ecs_cluster_config = ecs_cluster_config
        self._infra_context = infra_context

        logger.info("Creating ECS cluster...")
        logger.info(f"ECS cluster parameters: {self._ecs_cluster_config}")

        self._ecs_cluster = self._create_ecs_cluster()

        logger.info("ECS cluster created successfully")

    @property
    def cluster(self) -> ecs.Cluster:
        return self._ecs_cluster

    def _create_ecs_cluster(self):
        cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=self._vpc,
            container_insights_v2=(
                ecs.ContainerInsights.ENHANCED
                if self._ecs_cluster_config.container_insights
                else ecs.ContainerInsights.DISABLED
            ),
            enable_fargate_capacity_providers=True,
        )

        cluster.add_default_capacity_provider_strategy(
            [
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE",
                    base=1,
                    weight=1,
                ),
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    base=0,
                    weight=1,
                ),
            ]
        )

        namespace_name = (
            self._ecs_cluster_config.namespace
            or self._infra_context.context.kebab_prefix("app") + ".local"
        )
        cluster.add_default_cloud_map_namespace(
            name=namespace_name,
            vpc=self._vpc,
            use_for_service_connect=True,
        )
        logger.info(f"Default Cloud Map namespace created successfully: {namespace_name}")

        return cluster
