import logging

from aws_cdk.assertions import Match, Template

from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


def test_network_stack_vpc_properties(base_stage: BaseStage):
    """Test that VPC is created with correct properties."""
    # Access the stack from the stage
    stack = base_stage.network_stack

    # Create an assertion template
    template = Template.from_stack(stack)

    template = Template.from_stack(stack)

    # NOTE: This is for debugging purposes
    template_dict = template.to_json()
    logger.debug(template_dict)

    # Verify VPC Resource
    template.has_resource_properties(
        "AWS::EC2::VPC",
        {
            "CidrBlock": "10.0.0.0/16",
            "EnableDnsHostnames": True,
            "EnableDnsSupport": True,
            "Tags": Match.array_with(
                [
                    # NOTE: Order is important, it will be sorted by key
                    {"Key": "EnvName", "Value": "prd"},
                    {"Key": "ManagedBy", "Value": "CDK"},
                    {"Key": "Name", "Value": "TenantTestPrdStage/NetworkStack/ClassicVpc/Vpc"},
                    {"Key": "TenantName", "Value": "tenant-test"},
                ]
            ),
        },
    )


def test_network_stack_subnet_counts(base_stage: BaseStage):
    """Test that the correct number of subnets are created."""
    stack = base_stage.network_stack
    template = Template.from_stack(stack)

    # NOTE: This is for debugging purposes
    template_dict = template.to_json()
    logger.debug(template_dict)

    # Config has max_azs=2, so we expect:
    # 2 Public Subnets
    # 2 Private Subnets
    # 2 Isolated Subnets

    template.resource_count_is("AWS::EC2::Subnet", 6)

    # Verify we have exactly 1 NAT Gateway (as per config)
    template.resource_count_is("AWS::EC2::NatGateway", 1)
