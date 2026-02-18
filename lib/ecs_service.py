import logging
from typing import Dict, List, Optional

from aws_cdk import Duration
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct

from config.base_config import ContainerDefinitionConfig, EcsServiceConfig

logger = logging.getLogger(__name__)


class EcsService(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        security_groups: List[ec2.SecurityGroup],
        ecs_cluster: ecs.Cluster,
        additional_environment: Optional[Dict[str, str]] = None,
        secrets: Optional[Dict[str, ecs.Secret]] = None,
        ecs_service_config: EcsServiceConfig,
        ecr_image_uri: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._vpc = vpc
        self._security_groups = security_groups
        self._ecs_cluster = ecs_cluster
        self._additional_environment = additional_environment
        self._secrets = secrets
        self._ecs_service_config = ecs_service_config
        self._ecr_image_uri = ecr_image_uri
        logger.info("Creating ECS service...")
        logger.info(f"ECS service parameters: {self._ecs_service_config}")

        self._task_definition = self._create_task_definition()
        self._create_container_definitions()
        self._fargate_service = self._create_fargate_service()

        logger.info("ECS service created successfully")

    @property
    def service(self) -> ecs.FargateService:
        return self._fargate_service

    @property
    def service_arn(self) -> str:
        return self._fargate_service.service_arn

    def _create_fargate_service(self) -> ecs.FargateService:
        service_parameters = {
            "cluster": self._ecs_cluster,
            "security_groups": self._security_groups,
            "task_definition": self._task_definition,
            "vpc_subnets": ec2.SubnetSelection(subnets=self._vpc.private_subnets),
            "propagate_tags": ecs.PropagatedTagSource.TASK_DEFINITION,
            "desired_count": self._ecs_service_config.desired_count,
            "enable_execute_command": True,
        }

        if self._ecs_service_config.capacity_provider_strategies:
            capacity_provider_strategies = [
                ecs.CapacityProviderStrategy(
                    capacity_provider=capacity_provider_strategy.capacity_provider,
                    base=capacity_provider_strategy.base,
                    weight=capacity_provider_strategy.weight,
                )
                for capacity_provider_strategy in self._ecs_service_config.capacity_provider_strategies
            ]
            service_parameters["capacity_provider_strategies"] = capacity_provider_strategies

        fargate_service = ecs.FargateService(self, "EcsService", **service_parameters)

        service_connect_services = [
            ecs.ServiceConnectService(
                port_mapping_name=service_connect_service.port_mapping_name,
                dns_name=service_connect_service.dns_name,
                port=service_connect_service.port,
                per_request_timeout=Duration.seconds(60),
            )
            for service_connect_service in self._ecs_service_config.service_connect_services
        ]
        if service_connect_services:
            fargate_service.enable_service_connect(
                namespace=self._ecs_cluster.default_cloud_map_namespace.namespace_name,
                services=service_connect_services,
            )

        if self._ecs_service_config.auto_scaling:
            scalable_target = fargate_service.auto_scale_task_count(
                min_capacity=self._ecs_service_config.auto_scaling.min_capacity,
                max_capacity=self._ecs_service_config.auto_scaling.max_capacity,
            )
            if self._ecs_service_config.auto_scaling.cpu_target:
                scalable_target.scale_on_cpu_utilization(
                    "CpuScaling",
                    target_utilization_percent=self._ecs_service_config.auto_scaling.cpu_target,
                    scale_in_cooldown=Duration.seconds(
                        self._ecs_service_config.auto_scaling.cpu_scale_in_cooldown
                    ),
                    scale_out_cooldown=Duration.seconds(
                        self._ecs_service_config.auto_scaling.cpu_scale_out_cooldown
                    ),
                )

            if self._ecs_service_config.auto_scaling.memory_target:
                scalable_target.scale_on_memory_utilization(
                    "MemoryScaling",
                    target_utilization_percent=self._ecs_service_config.auto_scaling.memory_target,
                    scale_in_cooldown=Duration.seconds(
                        self._ecs_service_config.auto_scaling.memory_scale_in_cooldown
                    ),
                    scale_out_cooldown=Duration.seconds(
                        self._ecs_service_config.auto_scaling.memory_scale_out_cooldown
                    ),
                )

        return fargate_service

    def _create_task_definition(self):
        execution_role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:*",
                ],
                resources=["*"],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "kms:*",
                ],
                resources=["*"],
            )
        )

        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            # change this and add specific policies for each service, example s3 access for osd api
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
            ],
        )

        task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            cpu=self._ecs_service_config.cpu,
            execution_role=execution_role,
            task_role=task_role,
            memory_limit_mib=self._ecs_service_config.memory,
            # family=self._ecs_service_config.family, # TODO: uncomment this when we have a family
        )

        return task_definition

    def _create_container_definitions(self):
        container_definitions = []
        for container_definition in self._ecs_service_config.containers:
            container_definition = self._create_container_definition(container_definition)
            container_definitions.append(container_definition)
        return container_definitions

    def _create_container_definition(self, container_definition: ContainerDefinitionConfig):
        container_definition_port_mappings = [
            ecs.PortMapping(
                name=port_mapping.name,
                container_port=port_mapping.container_port,
                host_port=port_mapping.container_port,
                app_protocol=ecs.AppProtocol(port_mapping.app_protocol),
            )
            for port_mapping in container_definition.port_mappings
        ]

        container_definition_health_check = ecs.HealthCheck(
            command=container_definition.health_check.command,
            interval=Duration.seconds(container_definition.health_check.interval),
            timeout=Duration.seconds(container_definition.health_check.timeout),
            retries=container_definition.health_check.retries,
            start_period=Duration.seconds(container_definition.health_check.start_period),
        )

        if self._additional_environment:
            container_definition.environment.update(self._additional_environment)

        return ecs.ContainerDefinition(
            self,
            "ContainerDefinition",
            task_definition=self._task_definition,
            container_name=container_definition.container_name,
            image=ecs.ContainerImage.from_registry(
                self._ecr_image_uri or container_definition.image
            ),
            port_mappings=container_definition_port_mappings,
            environment=container_definition.environment,
            secrets=self._secrets,
            health_check=container_definition_health_check,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=f"{container_definition.container_name}",
                log_retention=logs.RetentionDays.ONE_MONTH,
            ),
        )
