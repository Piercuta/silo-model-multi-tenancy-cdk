"""
Configuration Management Module

This module defines the configuration structure for AWS CDK infrastructure.
It uses Pydantic for data validation and dependency management.

Structure:
- BaseConfig: Base class with common functionality
- AWS Configuration: AwsConfig, VpcConfig
- Database Configuration: DatabaseConfig
- DNS Configuration: DnsConfig

Configurations can be overridden via YAML files per environment.
Example file structure:
```
config/
  └── environments/
      ├── dev.yaml
      ├── staging.yaml
      └── prod.yaml

```
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .enums import AwsRegion


class AwsConfig(BaseModel):
    """
    Base AWS configuration.

    Defines fundamental parameters for AWS access.

    Attributes:
        account: AWS account ID
        region: AWS deployment region
    """

    account: str
    region: AwsRegion

    @property
    def region_str(self) -> str:
        """Returns the region as a string."""
        return self.region.value


class SecretsConfig(BaseModel):
    """
    Secrets configuration.
    """

    secret_ecs_complete_arn: Optional[str] = None


class VpcConfig(BaseModel):
    """
    VPC network configuration.

    Defines parameters for the private virtual network.

    Attributes:
        cidr: IP address range (default: "10.0.0.0/16")
        max_azs: Maximum number of availability zones (default: 3)
        reserved_azs: Number of reserved zones (default: 3)
        nat_gateways: Number of NAT Gateways (default: 1)
        automatic_subnet_creation: Enable automatic subnet creation (default: True)
    """

    cidr: str = Field(
        default="10.0.0.0/16",
        pattern=r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$",
        description="CIDR block for VPC (e.g., 10.0.0.0/16)",
    )
    reserved_azs: int = 3
    nat_gateways: int = Field(default=3, ge=0, le=3, description="Number of NAT Gateways (0-3)")

    @model_validator(mode="after")
    def validate_nat_gateways(self) -> "VpcConfig":
        """Validates NAT Gateway configuration constraints."""
        if self.nat_gateways > self.reserved_azs:
            raise ValueError(
                f"nat_gateways ({self.nat_gateways}) must be less than or equal to "
                f"reserved_azs ({self.reserved_azs})"
            )

        return self


class DocDBConfig(BaseModel):
    """
    DocumentDB configuration.

    Attributes:
        snapshot_identifier: Snapshot identifier for restoration (optional)
        db_instance_type: Instance type for DocumentDB
        storage_encrypted: Storage encrypted for DocumentDB
    """

    master_username: str = Field(
        default="docdbadmin",
        pattern=r"^[a-zA-Z][a-zA-Z0-9]{0,62}$",
        description="Master username for DocumentDB. Must start with a letter, 1-63 alphanumeric characters. Cannot be 'admin' or 'serviceadmin'.",
    )
    snapshot_identifier: Optional[str] = None
    backup_retention: int = 15
    db_instance_type: str = Field(default="t4g.medium", description="Instance type for DocumentDB")
    storage_encrypted: bool = Field(default=True, description="Storage encrypted for DocumentDB")

    @model_validator(mode="after")
    def validate_master_username(self) -> "DocDBConfig":
        """Validate that master_username is not a reserved word."""
        reserved_words = {"admin", "serviceadmin"}
        for reserved_word in reserved_words:
            if self.master_username.lower() == reserved_word.lower():
                raise ValueError(
                    f"master_username cannot be '{self.master_username}'. Reserved words: {', '.join(reserved_words)}"
                )
        return self


class RedisConfig(BaseModel):
    """
    Redis configuration.
    """

    # Note: if serverless_cache_name is not provided, a deterministic name will be generated
    serverless_cache_enabled: bool = False
    # Serverless cluster parameters (if serverless_cache_enabled is True)
    serverless_cache_name: Optional[str] = Field(
        default=None,
        max_length=40,
        pattern=r"^[a-zA-Z][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z]$",
        description="Optional Serverless cache name. Must start with a letter, contain only ASCII letters, digits, and hyphens, not end with a hyphen, and not contain consecutive hyphens. Max 40 characters.",
    )
    backup_retention: int = 7
    backup_arns_to_restore: Optional[str] = None
    # Redis cluster parameters (if serverless_cache_enabled is False)
    num_cache_nodes: int = 1
    cache_node_type: str = "cache.t4g.medium"
    cache_engine_version: str = "7.1"
    cache_parameter_group_name: str = "default.redis7"

    @model_validator(mode="after")
    def validate_serverless_cache_name(self) -> "RedisConfig":
        """
        Validate serverless cache name according to ElastiCache rules:
        - Must not contain two consecutive hyphens
        """
        if self.serverless_cache_name is None:
            return self

        # Check no consecutive hyphens
        if "--" in self.serverless_cache_name:
            raise ValueError(
                f"serverless_cache_name '{self.serverless_cache_name}' must not contain two consecutive hyphens"
            )

        return self


class HealthCheckTargetGroupConfig(BaseModel):
    """
    Health check configuration.
    """

    path: str = "/"
    port: str = "8080"
    protocol: str = "HTTP"
    interval: int = 30
    timeout: int = 10
    retries: int = 3
    success_codes: str = "200-399"


class TargetGroupConfig(BaseModel):
    """
    Target group configuration.
    """

    port: int = 8080
    protocol: str = "HTTP"
    deregistration_delay: int = 300
    health_check: HealthCheckTargetGroupConfig = HealthCheckTargetGroupConfig()


class AlbConfig(BaseModel):
    """
    ALB configuration.
    """

    internet_facing: bool = True
    target_group_osd_api: TargetGroupConfig = TargetGroupConfig()
    target_group_keycloak: TargetGroupConfig = TargetGroupConfig()
    enable_log_replication: bool = Field(default=True)


class EcsClusterConfig(BaseModel):
    container_insights: bool = True
    namespace: Optional[str] = None


class PortMappingConfig(BaseModel):
    name: str = ""
    container_port: int = 8080
    host_port: int = container_port
    app_protocol: str = "http"


class HealthCheckConfig(BaseModel):
    command: List[str] = ["CMD-SHELL", "echo ok || exit 1"]
    interval: int = 30
    timeout: int = 10
    retries: int = 3
    start_period: int = 0


class ServiceConnectServiceConfig(BaseModel):
    port_mapping_name: str = ""
    dns_name: str = ""
    port: int = 8080


class ContainerDefinitionConfig(BaseModel):
    container_name: str = ""
    image: str = ""
    port_mappings: List[PortMappingConfig] = []
    environment: Dict[str, str] = Field(default_factory=dict)
    health_check: HealthCheckConfig = HealthCheckConfig()


class AutoScalingConfig(BaseModel):
    min_capacity: int = 1
    max_capacity: int = 10
    cpu_target: int = 60
    cpu_scale_in_cooldown: int = 300
    cpu_scale_out_cooldown: int = 300
    memory_target: int = 70
    memory_scale_in_cooldown: int = 300
    memory_scale_out_cooldown: int = 300


class CapacityProviderStrategyConfig(BaseModel):
    capacity_provider: str = "FARGATE"
    base: int = 1
    weight: int = 1


class EcsServiceConfig(BaseModel):
    name: str = ""
    cpu: int = 1024
    memory: int = 2048
    desired_count: int = 1
    service_connect_services: List[ServiceConnectServiceConfig] = []
    auto_scaling: Optional[AutoScalingConfig] = None
    containers: List[ContainerDefinitionConfig] = []
    capacity_provider_strategies: Optional[List[CapacityProviderStrategyConfig]] = None


class AngularBuildConfig(BaseModel):
    theme: str = "sandbox"
    config: str = "aws-tenant"
    logo: str = "assets/logo-fr.png"
    source_bucket_key: Optional[str] = None
    source_bucket_name: Optional[str] = None
    # If None, will be generated as "appfront-{region}"


class FrontEndConfig(BaseModel):
    bucket_name: Optional[str] = None
    comment: str = "osd frontend"
    domain_names: List[str] = []
    angular_build: AngularBuildConfig = AngularBuildConfig()
    delivery_destination_arn: str = Field(
        default="arn:aws:logs:us-east-1:000000000000:delivery-destination:cloudfront-logs-delivery-destination"
    )


class AuroraClusterConfig(BaseModel):
    """
    RDS database configuration.

    Defines parameters for PostgreSQL / MySQL / Aurora database.

    Attributes:
        snapshot_identifier: Snapshot identifier for restoration (optional)
        backup_retention: Backup retention period in days (default: 2)
        instance_reader_count: Number of read-only instances (default: 0)
        serverless_v2_min_capacity: Minimum capacity in ACU (default: 0.5)
        serverless_v2_max_capacity: Maximum capacity in ACU (default: 2.0)
        master_username: Administrator username (default: "auroradba")
        engine: Database engine type (default: MYSQL)
    """

    engine: str = "mysql"
    snapshot_identifier: Optional[str] = None
    backup_retention: int = 14
    instance_reader_count: int = 1
    default_database_name: str = "keycloak"
    serverless_v2_min_capacity: float = Field(
        default=0.5, ge=0, description="Minimum capacity in ACU (minimum 0.5)"
    )
    serverless_v2_max_capacity: float = Field(default=4.0, description="Maximum capacity in ACU")

    @model_validator(mode="after")
    def validate_capacity(self) -> "AuroraClusterConfig":
        """Validates that minimum capacity is less than maximum capacity."""
        if self.serverless_v2_min_capacity >= self.serverless_v2_max_capacity:
            raise ValueError(
                f"serverless_v2_min_capacity ({self.serverless_v2_min_capacity}) "
                f"must be less than serverless_v2_max_capacity ({self.serverless_v2_max_capacity})"
            )
        return self


class StorageConfig(BaseModel):
    """
    Storage configuration.

    Defines parameters for storage management with S3.

    Attributes:
        osd_bucket_name: OSD bucket name
    """

    osd_bucket_name: Optional[str] = None


class DomainConfig(BaseModel):
    """
    DNS configuration.

    Defines parameters for DNS management with Route53.

    Attributes:
        hosted_zone_id: Route53 hosted zone ID
        zone_name: DNS zone name
        frontend_domain_name: Frontend domain name
        backend_domain_name: Backend domain name
    """

    zone_name: str = "app.dev.example.com"
    hosted_zone_id: Optional[str] = None
    parent_hosted_zone_id: Optional[str] = None
    delegation_role_arn: Optional[
        Literal[
            "arn:aws:iam::111111111111:role/Route53ZoneDelegationRole-OrgSubdomains",
            "arn:aws:iam::777777777777:role/Route53ZoneDelegationRole-OrgRoot",
        ]
    ] = None

    cloudfront_certificate_arn: Optional[str] = Field(
        default=None, description="ARN of existing ACM certificate for CloudFront in us-east-1"
    )
    alb_certificate_arn: Optional[str] = Field(
        default=None, description="ARN of existing ACM certificate for ALB in eu-west-1"
    )
    records: Dict[str, str] = Field(
        ...,
        description="DNS records configuration. Must contain 'front_domain_name', 'api_domain_name', and 'sso_domain_name'.",
    )

    @model_validator(mode="after")
    def validate_hosted_zone_config(self) -> "DomainConfig":
        """
        Validate hosted zone configuration.

        Rules:
        - Exactly one of hosted_zone_id or parent_hosted_zone_id must be provided (mutually exclusive)
        - If hosted_zone_id is provided: use existing hosted zone (no delegation)
        - If parent_hosted_zone_id is provided: create new hosted zone with delegation
        - For cross-account delegation, delegation_role_arn is required (validated at stack level)
        - records must contain the three required keys: front_domain_name, api_domain_name, sso_domain_name
        """
        # Check that at least one is provided
        if not self.hosted_zone_id and not self.parent_hosted_zone_id:
            raise ValueError(
                "Either 'hosted_zone_id' or 'parent_hosted_zone_id' must be provided. "
                "Use 'hosted_zone_id' to import an existing zone, or 'parent_hosted_zone_id' "
                "to create a new zone with delegation."
            )

        # Check that both are not provided (mutually exclusive)
        if self.hosted_zone_id and self.parent_hosted_zone_id:
            raise ValueError(
                "'hosted_zone_id' and 'parent_hosted_zone_id' are mutually exclusive. "
                "Provide 'hosted_zone_id' to use an existing zone (no delegation), "
                "or 'parent_hosted_zone_id' to create a new zone with delegation, but not both."
            )

        # Validate that records contains the three required keys
        required_keys = {"front_domain_name", "api_domain_name", "sso_domain_name"}
        if not required_keys.issubset(self.records.keys()):
            missing_keys = required_keys - set(self.records.keys())
            raise ValueError(
                f"records must contain all three required keys: 'front_domain_name', 'api_domain_name', and 'sso_domain_name'. "
                f"Missing keys: {', '.join(missing_keys)}"
            )

        return self


class InfrastructureConfig(BaseModel):
    """
    Complete infrastructure configuration.

    This class groups all configurations needed to deploy
    the complete infrastructure.

    Attributes:
        aws: Base AWS configuration
        vpc: VPC network configuration
        database: Database configuration
        backend: ECS backend configuration
        frontend: CloudFront frontend configuration
        cicd_fronend: CI/CD pipeline configuration
        cicd_backend: CI/CD pipeline configuration
        dns: DNS configuration

    Example:
        ```yaml
        # config/environments/dev.yaml
        env_name: dev
        tenant_name: my-tenant

        aws:
          account: "123456789012"
          region: eu-west-1

        vpc:
          cidr: "10.0.0.0/16"
          max_azs: 3
          nat_gateways: 1

        database:
          backup_retention: 7
          serverless_v2_min_capacity: 0.5
          serverless_v2_max_capacity: 2.0

        dns:
          hosted_zone_id: "Z1234567890"
          zone_name: "example.com"
        ```
    """

    aws: AwsConfig
    secrets: SecretsConfig
    vpc: VpcConfig
    storage: StorageConfig
    aurora_cluster: AuroraClusterConfig
    docdb: DocDBConfig
    redis: RedisConfig
    front_end: FrontEndConfig
    alb: AlbConfig
    ecs_cluster: EcsClusterConfig
    ecs_services: Optional[Dict[str, EcsServiceConfig]] = None  # Utiliser directement Dict
    domain: DomainConfig
