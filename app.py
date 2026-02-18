#!/usr/bin/env python3
import logging

import aws_cdk as cdk

from stages.factory import StageFactory
from stages.shared_stage import SharedStage


def setup_logging():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )


setup_logging()
logger = logging.getLogger(__name__)

MAIN_ACCOUNT_ID = "111111111111"
MAIN_ACCOUNT_REGION = "eu-west-1"

app = cdk.App()

ctx = app.node.try_get_context

tenant = ctx("tenant")
env_name = ctx("env")


# If both tenant and env are specified, synthesize only that specific stage
if tenant and env_name:
    logger.info(f"CDK mode: FOCUS tenant={tenant} env={env_name}")
    stage = StageFactory.create(app, env_name, tenant)
    stages = [stage]
else:
    # Default behavior: synthesize all stages when no specific context is provided
    logger.info("CDK mode: FULL (no specific tenant/env context provided)")
    stages = StageFactory.create_stages(
        app,
        stages_config=[
            # ("fr", "dev"),
            ("fr", "stg"),
            ("de", "prd"),
            ("ch", "prd"),
            ("us", "prd"),
            ("nl", "prd"),
        ],
    )

    # NOTE: DISABLED for now, we don't need to create shared stage for frontend source buckets
    # get target region list
    # target_region_list = [stage.infra_context.config.aws.region_str for stage in stages]
    # if MAIN_ACCOUNT_REGION in target_region_list:
    #     target_region_list.remove(MAIN_ACCOUNT_REGION)
    # target_region_list = list(dict.fromkeys(target_region_list))

    tenant_list = [stage.infra_context.context.tenant_name for stage in stages]
    tenant_list = list(dict.fromkeys(tenant_list))

    account_list = [stage.infra_context.config.aws.account for stage in stages]
    account_list = list(dict.fromkeys(account_list))
    # Always create shared stage for frontend source buckets
    shared_stage = SharedStage(
        app,
        "SharedOsd",
        main_account_id=MAIN_ACCOUNT_ID,
        main_account_region=MAIN_ACCOUNT_REGION,
        # replication_regions=target_region_list,
        tenants=tenant_list,
        accounts=account_list,
    )


logger.info(f"Synthesis complete - Created {len(stages)} tenant stages")

app.synth()
