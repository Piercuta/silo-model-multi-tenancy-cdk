import logging

from aws_cdk.assertions import Template

logger = logging.getLogger(__name__)


def test_tenant_c_stage_composition(tenant_c_stage):
    """Verify that TenantCStage contains all expected stacks."""

    # 1. Check Base Stacks
    assert tenant_c_stage.network_stack is not None
    assert tenant_c_stage.security_stack is not None

    # 2. Check Tenant C Specific Stack
    assert tenant_c_stage.extra_bucket_stack is not None

    # 3. Verify dependencies
    # The extra bucket stack should depend on network/security if they share resources
    # (In this case, it uses VPC and SGs, so implicit dependency exists)


def test_extra_bucket_stack_resources(tenant_c_stage):
    """Verify resources in the ExtraBucketStack."""
    stack = tenant_c_stage.extra_bucket_stack
    template = Template.from_stack(stack)
    # NOTE: This is for debugging purposes
    template_dict = template.to_json()
    logger.debug(template_dict)

    # Should have 2 S3 buckets
    template.resource_count_is("AWS::S3::Bucket", 2)

    # Verify naming convention application via config
    # We expect buckets to have names starting with "unit-test-test-"
    # But since S3 bucket names in CDK are physical names, we might verify the logical ID or tags

    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "Tags": [
                # NOTE: Order is important, it will be sorted by key
                {"Key": "EnvName", "Value": "prd"},
                {"Key": "ManagedBy", "Value": "CDK"},
                {"Key": "TenantName", "Value": "tenant-test"},
            ]
        },
    )
