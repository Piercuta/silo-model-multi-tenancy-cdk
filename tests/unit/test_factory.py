import pytest

from stages.base_stage import BaseStage
from stages.factory import StageFactory


def test_create_stages_explicit(app):
    """Test explicit stage creation with create_stages."""
    stages = StageFactory.create_stages(
        app,
        stages_config=[
            ("fr", "dev"),
            # ("fr", "prd"),
            # ("tenant_c", "prd", TenantCStage),
        ],
    )

    # Should create exactly 3 stages
    assert len(stages) == 1

    # Check types
    assert isinstance(stages[0], BaseStage)
    # assert isinstance(stages[1], BaseStage)
    # assert isinstance(stages[2], TenantCStage)

    # # Verify tenant_c has extra_bucket_stack
    # assert hasattr(stages[2], "extra_bucket_stack")


def test_create_stages_invalid_config(app):
    """Test that invalid config raises an error."""
    with pytest.raises(ValueError, match="Invalid stage config"):
        StageFactory.create_stages(
            app,
            stages_config=[
                ("fr",),  # Missing environment
            ],
        )
