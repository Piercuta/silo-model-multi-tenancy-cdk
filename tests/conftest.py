import aws_cdk as cdk
import pytest

from config.base_config import (
    AlbConfig,
    AuroraClusterConfig,
    AwsConfig,
    ContainerDefinitionConfig,
    DocDBConfig,
    DomainConfig,
    EcsClusterConfig,
    EcsServiceConfig,
    FrontEndConfig,
    InfrastructureConfig,
    PortMappingConfig,
    RedisConfig,
    SecretsConfig,
    StorageConfig,
    VpcConfig,
)
from config.loader import Context, InfrastructureContext
from stages.base_stage import BaseStage
from stages.tenant_c_stage import TenantCStage
from utils.naming import to_pascal


@pytest.fixture
def mock_infra_context():
    """Provides a standard configuration for testing."""
    # It s important to test the difference between a dev stg and prd stage.
    # For all statefull resources you have to test the retention policy is set to retain stg and destroy for prd and destroy for dev.
    return InfrastructureContext(
        config=InfrastructureConfig(
            aws=AwsConfig(account="123456789012", region="eu-west-1"),
            secrets=SecretsConfig(
                secret_ecs_complete_arn="arn:aws:secretsmanager:eu-west-1:123456789012:secret:tenant-test/prd/secret-123456",
            ),
            vpc=VpcConfig(cidr="10.0.0.0/16", reserved_azs=2, nat_gateways=1),
            storage=StorageConfig(),
            aurora_cluster=AuroraClusterConfig(),
            docdb=DocDBConfig(),
            redis=RedisConfig(),
            front_end=FrontEndConfig(),
            alb=AlbConfig(),
            ecs_cluster=EcsClusterConfig(),
            domain=DomainConfig(
                zone_name="app.prd.example.com",
                hosted_zone_id="Z0000000000000",
                records={
                    "front_domain_name": "app.prd.example.com",
                    "api_domain_name": "api.app.prd.example.com",
                    "sso_domain_name": "sso.app.prd.example.com",
                },
            ),
            ecs_services={
                "osd_api": EcsServiceConfig(
                    name="osd-api",
                    cpu=1024,
                    memory=2048,
                    containers=[
                        ContainerDefinitionConfig(
                            container_name="osd-api",
                            image="111111111111.dkr.ecr.eu-west-1.amazonaws.com/org/application/osd-api:abc12345",
                            port_mappings=[
                                PortMappingConfig(
                                    name="osd-api", container_port=8080, host_port=8080
                                ),
                            ],
                        ),
                    ],
                ),
                "review": EcsServiceConfig(
                    name="review",
                    cpu=1024,
                    memory=2048,
                    containers=[
                        ContainerDefinitionConfig(
                            container_name="review",
                            image="111111111111.dkr.ecr.eu-west-1.amazonaws.com/org/infrastructure/fonto/fonto-review:8.11.0",
                            port_mappings=[
                                PortMappingConfig(name="review", container_port=80, host_port=80),
                            ],
                        ),
                    ],
                ),
                "content_quality": EcsServiceConfig(
                    name="content-quality",
                    cpu=1024,
                    memory=2048,
                    containers=[
                        ContainerDefinitionConfig(
                            container_name="content-quality",
                            image="111111111111.dkr.ecr.eu-west-1.amazonaws.com/org/infrastructure/fonto/fonto-content-quality:8.11.0",
                            port_mappings=[
                                PortMappingConfig(
                                    name="content-quality", container_port=80, host_port=80
                                ),
                            ],
                        ),
                    ],
                ),
                "document_history": EcsServiceConfig(
                    name="document-history",
                    cpu=1024,
                    memory=2048,
                    containers=[
                        ContainerDefinitionConfig(
                            container_name="document-history",
                            image="111111111111.dkr.ecr.eu-west-1.amazonaws.com/org/infrastructure/fonto/fonto-document-history:8.11.0",
                            port_mappings=[
                                PortMappingConfig(
                                    name="document-history", container_port=80, host_port=80
                                ),
                            ],
                        ),
                    ],
                ),
                "keycloak": EcsServiceConfig(
                    name="keycloak",
                    cpu=1024,
                    memory=2048,
                    containers=[
                        ContainerDefinitionConfig(
                            container_name="keycloak",
                            image="public.ecr.aws/bitnami/keycloak:latest",
                            port_mappings=[
                                PortMappingConfig(
                                    name="keycloak", container_port=8080, host_port=8080
                                ),
                            ],
                        ),
                    ],
                ),
            },
        ),
        context=Context(env_name="prd", tenant_name="tenant-test"),
    )


@pytest.fixture
def app():
    """Provides a CDK App instance."""
    return cdk.App(context={"disable_lambda_bundling": True})


@pytest.fixture
def base_stage(app, mock_infra_context):
    """Provides an instantiated BaseStage."""
    return BaseStage(
        app,
        to_pascal(
            f"{mock_infra_context.context.tenant_name}-{mock_infra_context.context.env_name}-stage"
        ),
        infra_context=mock_infra_context,
    )


@pytest.fixture
def tenant_c_stage(app, mock_infra_context):
    """Provides an instantiated TenantCStage."""
    return TenantCStage(
        app,
        to_pascal(
            f"{mock_infra_context.context.tenant_name}-{mock_infra_context.context.env_name}-stage"
        ),
        infra_context=mock_infra_context,
    )
