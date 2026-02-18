# config/loader.py
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict

import yaml
from aws_cdk import Stack, Stage, Tags

from utils.naming import to_kebab, to_pascal

from .base_config import (
    AlbConfig,
    AuroraClusterConfig,
    AwsConfig,
    DocDBConfig,
    DomainConfig,
    EcsClusterConfig,
    EcsServiceConfig,
    FrontEndConfig,
    InfrastructureConfig,
    RedisConfig,
    SecretsConfig,
    StorageConfig,
    VpcConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class Context:
    env_name: str
    tenant_name: str

    def kebab_prefix(self, base: str) -> str:
        return to_kebab(f"{self.tenant_name}-{self.env_name}") + "-" + base

    def pascal_prefix(self, base: str) -> str:
        return to_pascal(self.tenant_name) + to_pascal(f"{self.env_name}") + base

    def prefix(self, base: str) -> str:
        """Generates a standardized kebab prefix for resources."""
        return self.kebab_prefix(base)

    def add_stack_global_tags(self, stack: Stack):
        """Adds global tags to the configuration."""
        for key, value in self.tags.items():
            Tags.of(stack).add(key, value)

    def add_stage_global_tags(self, stage: Stage):
        """Adds global tags to the stage."""
        for key, value in self.tags.items():
            Tags.of(stage).add(key, value)

    @property
    def tags(self):
        """Standardized tags to apply to all resources."""
        return {
            "EnvName": self.env_name,
            "TenantName": self.tenant_name,
            "ManagedBy": "CDK",
        }


@dataclass
class InfrastructureContext:
    config: InfrastructureConfig
    context: Context


def substitute_variables(data: Any, variables: Dict[str, str]) -> Any:
    """
    Recursively substitute ${variable_name} placeholders in configuration data.

    Args:
        data: The data structure to process (dict, list, str, or other)
        variables: Dictionary of variable names to their values

    Returns:
        Data structure with all ${variable_name} placeholders replaced

    Raises:
        ValueError: If a variable placeholder is found but not defined
    """
    if isinstance(data, str):
        # Find all ${variable_name} patterns
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, data)

        # Check if all variables are defined
        for var_name in matches:
            if var_name not in variables:
                raise ValueError(
                    f"Variable '${var_name}' is used but not defined in 'variables' section. "
                    f"Available variables: {list(variables.keys())}"
                )

        # Replace all ${variable_name} with their values
        result = data
        for var_name, var_value in variables.items():
            result = result.replace(f"${{{var_name}}}", str(var_value))

        return result
    elif isinstance(data, dict):
        return {k: substitute_variables(v, variables) for k, v in data.items()}
    elif isinstance(data, list):
        return [substitute_variables(item, variables) for item in data]
    else:
        return data


class ConfigLoader:
    """
    Loader for the configuration files.

    This class loads the configuration files for the infrastructure.
    It also creates the complete configuration for the infrastructure.
    """

    def __init__(self, env_name: str, tenant_name: str = "fr"):
        """
        Initialize the configuration loader.

        Args:
            env_name: The name of the environment.
            tenant_name: The name of the tenant.
        """
        self._env_name = env_name
        self._tenant_name = tenant_name

        self.base_path = os.path.dirname(os.path.abspath(__file__))

    def generate_stage_name(self) -> str:
        return f"{to_pascal(self._tenant_name)}-{to_pascal(self._env_name)}"

    def load_environment_config(self) -> Dict[str, Any]:
        """
        Load the configuration from the YAML file and substitute variables.

        Variables are defined in a 'variables' section at the top of the YAML file.
        They can be referenced anywhere in the config using ${variable_name} syntax.
        """
        # NOTE: base_path peut être overridé depuis app.py pour supporter multi-tenant
        config_path = os.path.join(self.base_path, self._tenant_name, f"{self._env_name}.yaml")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_path, "r") as f:
            raw_config = yaml.safe_load(f)

        # Extract variables section if present
        variables = raw_config.pop("variables", {})
        if not isinstance(variables, dict):
            raise ValueError("'variables' section must be a dictionary")

        # Substitute variables within the variables themselves (for variable references)
        # This allows variables to reference other variables, e.g.:
        #   zone_name: "example.com"
        #   front_domain: "front.${zone_name}"
        if variables:
            # Convert values to strings and substitute recursively
            # Multiple passes may be needed for nested references
            max_passes = 10  # Prevent infinite loops
            for _ in range(max_passes):
                changed = False
                for key, value in variables.items():
                    if isinstance(value, str):
                        new_value = substitute_variables(value, variables)
                        if new_value != value:
                            variables[key] = new_value
                            changed = True
                if not changed:
                    break
            else:
                logger.warning("Variable substitution may not have converged after max passes")

        # Substitute variables in the rest of the configuration
        if variables:
            logger.info(f"Substituting variables: {list(variables.keys())}")
            raw_config = substitute_variables(raw_config, variables)

        return raw_config

    def create_infra_context(self) -> InfrastructureContext:
        """Create the complete configuration."""
        env_config = self.load_environment_config()
        # Merge configuration and secrets
        config = {
            "aws": AwsConfig(**env_config["aws"]),
            "secrets": SecretsConfig(**env_config.get("secrets", {})),
            "vpc": VpcConfig(**env_config.get("vpc", {})),
            "storage": StorageConfig(**env_config.get("storage", {})),
            "aurora_cluster": AuroraClusterConfig(**env_config.get("aurora_cluster", {})),
            "docdb": DocDBConfig(**env_config.get("docdb", {})),
            "redis": RedisConfig(**env_config.get("redis", {})),
            "front_end": FrontEndConfig(**env_config.get("front_end", {})),
            "alb": AlbConfig(**env_config.get("alb", {})),
            "ecs_cluster": EcsClusterConfig(**env_config.get("ecs_cluster", {})),
            "ecs_services": (
                {
                    name: EcsServiceConfig(**service_config)
                    for name, service_config in env_config.get("ecs_services", {}).items()
                }
                if env_config.get("ecs_services")
                else None
            ),
            "domain": DomainConfig(**env_config.get("domain", {})),
        }

        logger.info(f"Config: {config}")

        infra_config = InfrastructureConfig(**config)

        self._env_name = env_config.get("env_name_override") or self._env_name
        self._tenant_name = env_config.get("tenant_name_override") or self._tenant_name

        context = Context(
            env_name=self._env_name,
            tenant_name=self._tenant_name,
        )

        return InfrastructureContext(config=infra_config, context=context)
