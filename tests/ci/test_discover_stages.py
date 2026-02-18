"""Tests for CI stage discovery script."""

from pathlib import Path

from ci.scripts.discover_stages import (
    create_stage_configs,
    detect_environment_type,
    group_by_stage,
    parse_cdk_stacks_from_yaml,
)


def test_parse_cdk_stacks_from_yaml(tmp_path: Path):
    """Test parsing CDK stacks from cdk list --long YAML output."""
    yaml_path = tmp_path / "cdk_stacks_long.yml"
    yaml_content = """
- id: FrdevStage/NetworkStack (FrdevStage-NetworkStack)
  name: FrdevStage-NetworkStack
  environment:
    account: "111111111111"
    region: eu-west-1
    name: aws://111111111111/eu-west-1
- id: FrdevStage/SecurityStack (FrdevStage-SecurityStack)
  name: FrdevStage-SecurityStack
  environment:
    account: "111111111111"
    region: eu-west-1
    name: aws://111111111111/eu-west-1
- id: TenantcprdStage/NetworkStack (TenantcprdStage-NetworkStack)
  name: TenantcprdStage-NetworkStack
  environment:
    account: "222222222222"
    region: eu-west-1
    name: aws://222222222222/eu-west-1
- id: TenantcprdStage/SecurityStack (TenantcprdStage-SecurityStack)
  name: TenantcprdStage-SecurityStack
  environment:
    account: "222222222222"
    region: eu-west-1
    name: aws://222222222222/eu-west-1
"""
    yaml_path.write_text(yaml_content)

    stacks = parse_cdk_stacks_from_yaml(str(yaml_path))
    assert len(stacks) == 4
    assert "FrdevStage/NetworkStack" in stacks
    assert "FrdevStage/SecurityStack" in stacks
    assert "TenantcprdStage/NetworkStack" in stacks
    assert "TenantcprdStage/SecurityStack" in stacks


def test_group_by_stage():
    """Test grouping stacks by stage name."""
    stacks = [
        "FrdevStage/NetworkStack",
        "FrdevStage/SecurityStack",
        "TenantcprdStage/NetworkStack",
        "TenantcprdStage/ExtraBucketStack",
    ]

    grouped = group_by_stage(stacks)

    assert len(grouped) == 2
    assert "FrdevStage" in grouped
    assert "TenantcprdStage" in grouped
    assert len(grouped["FrdevStage"]) == 2
    assert len(grouped["TenantcprdStage"]) == 2


def test_detect_environment_type():
    """Test environment type detection from stage name."""
    assert detect_environment_type("FrdevStage") == "dev"
    assert detect_environment_type("FrstgStage") == "stg"
    assert detect_environment_type("FrprdStage") == "prd"
    assert detect_environment_type("TenantbprodStage") == "prd"
    assert detect_environment_type("TenantcStagingStage") == "stg"
    assert detect_environment_type("UnknownStage") == "other"


def test_create_stage_configs():
    """Test creation of stage configurations."""
    grouped = {
        "FrdevStage": ["FrdevStage/NetworkStack", "FrdevStage/SecurityStack"],
        "TenantcprdStage": ["TenantcprdStage/NetworkStack"],
    }

    configs = create_stage_configs(grouped)

    assert len(configs) == 2

    # Check FrdevStage config
    dev_config = next(c for c in configs if c["stage_name"] == "FrdevStage")
    assert dev_config["env_type"] == "dev"
    assert dev_config["stack_count"] == 2
    assert dev_config["deploy_pattern"] == "FrdevStage/*"
    assert len(dev_config["stacks"]) == 2

    # Check TenantcprdStage config
    prd_config = next(c for c in configs if c["stage_name"] == "TenantcprdStage")
    assert prd_config["env_type"] == "prd"
    assert prd_config["stack_count"] == 1
    assert prd_config["deploy_pattern"] == "TenantcprdStage/*"
