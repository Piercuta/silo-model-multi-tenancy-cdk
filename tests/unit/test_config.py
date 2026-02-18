import pytest
from pydantic import ValidationError

from config.base_config import VpcConfig


def test_vpc_config_defaults():
    """Test that default values are correctly applied."""
    config = VpcConfig()
    assert config.cidr == "10.0.0.0/16"
    assert config.reserved_azs == 3
    assert config.nat_gateways == 3


def test_vpc_config_validation_nat_gateways():
    """Test validation logic for NAT gateways."""
    # Valid case
    VpcConfig(nat_gateways=1, reserved_azs=3)

    # Invalid: More NATs than reserved AZs
    with pytest.raises(ValidationError) as excinfo:
        VpcConfig(nat_gateways=3, reserved_azs=2)
    assert "must be less than or equal to reserved_azs" in str(excinfo.value)

    # Invalid: More than 3 NATs
    with pytest.raises(ValidationError) as excinfo:
        VpcConfig(nat_gateways=4)
    assert "Input should be less than or equal to 3" in str(excinfo.value)


def test_naming_prefix_logic(mock_infra_context):
    """Test that naming prefixes are generated correctly."""
    # mock_infra_context comes from conftest.py
    toto = mock_infra_context.context.kebab_prefix("bucket")
    print(toto)
    assert mock_infra_context.context.kebab_prefix("bucket") == "tenant-test-prd-bucket"
    assert mock_infra_context.context.pascal_prefix("Bucket") == "TenantTestPrdBucket"
