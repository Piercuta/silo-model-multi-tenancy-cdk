# stages/factory.py

import logging
from typing import List, Type

from aws_cdk import App

from config.loader import ConfigLoader
from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


class StageFactory:
    """Factory for creating CDK stages with proper configuration."""

    @staticmethod
    def create(
        app: App, env: str, tenant: str, stage_class: Type[BaseStage] = BaseStage
    ) -> BaseStage:
        """
        Create a stage with the appropriate configuration.

        Args:
            app: CDK App instance
            env: Environment name (dev, stg, prd)
            tenant: Tenant name (fr, tenant_b, tenant_c)
            stage_class: Stage class to instantiate

        Returns:
            Instantiated stage
        """
        config_loader = ConfigLoader(env, tenant)
        infra_context = config_loader.create_infra_context()
        stage_name = config_loader.generate_stage_name()
        logger.info(f"Creating {stage_class.__name__}: {stage_name}")
        return stage_class(app, stage_name, infra_context=infra_context)

    @staticmethod
    def create_stages(app: App, stages_config: List[tuple]) -> List[BaseStage]:
        """
        Create multiple stages from an explicit configuration list.

        This is the recommended approach for clarity - you explicitly list
        which stages to create in your app.py file.

        Args:
            app: CDK App instance
            stages_config: List of tuples defining stages to create.
                          Each tuple can be:
                          - (tenant, env) for BaseStage
                          - (tenant, env, StageClass) for custom stage

        Returns:
            List of created stages

        Example:
            ```python
            stages = StageFactory.create_stages(app, [
                # FR tenant (uses BaseStage by default)
                ("fr", "dev"),
                ("fr", "stg"),
                ("fr", "prd"),

                # Tenant B (uses BaseStage)
                ("tenant_b", "prd"),

                # Tenant C (uses custom TenantCStage)
                ("tenant_c", "prd", TenantCStage),
            ])
            ```
        """
        stages = []

        for config in stages_config:
            if len(config) == 2:
                # (tenant, env) - use BaseStage
                tenant, env = config
                stage_class = BaseStage
            elif len(config) == 3:
                # (tenant, env, StageClass) - use custom stage
                tenant, env, stage_class = config
            else:
                raise ValueError(
                    f"Invalid stage config: {config}. "
                    "Expected (tenant, env) or (tenant, env, StageClass)"
                )

            try:
                stage = StageFactory.create(
                    app=app, env=env, tenant=tenant, stage_class=stage_class
                )
                stages.append(stage)
            except Exception as e:
                logger.error(f"Failed to create stage for {tenant}/{env}: {e}")
                raise

        logger.info(f"Successfully created {len(stages)} stages")
        return stages
