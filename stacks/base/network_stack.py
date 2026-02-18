import logging

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from config.loader import InfrastructureContext
from lib.vpc.classic_vpc import ClassicVpc
from utils.naming import kebab_to_pascal

logger = logging.getLogger(__name__)


class NetworkStack(Stack):
    """
    Stack containing the network resources for the infrastructure.

    This stack creates a classic VPC with public, private and isolated subnets.
    It also creates the necessary outputs for the infrastructure.
    """

    def __init__(
        self, scope: Construct, construct_id: str, *, infra_context: InfrastructureContext, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        logger.info(
            f"Creating network stack (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

        self._infra_context = infra_context

        self._classic_vpc = self._create_vpc()
        # self._create_stacks_outputs()

        logger.info(
            f"Network stack created successfully (environment: {infra_context.context.env_name}, tenant: {infra_context.context.tenant_name})"
        )

    @property
    def vpc(self) -> ec2.Vpc:
        return self._classic_vpc.vpc

    def _create_vpc(self) -> None:
        return ClassicVpc(
            self,
            "ClassicVpc",
            vpc_config=self._infra_context.config.vpc,
            context=self._infra_context.context,
        )

    def _create_stacks_outputs(self) -> None:
        CfnOutput(
            self,
            "VpcId",
            value=self._classic_vpc.vpc.vpc_id,
            description="Vpc Id",
        )

        for subnet in self.vpc.public_subnets:
            logger.info(f"Subnet Id: {subnet.subnet_id}")
            logger.info(f"Subnet Availability Zone: {subnet.availability_zone}")
            CfnOutput(
                self,
                f"PublicSubnet{kebab_to_pascal(subnet.availability_zone)}",
                value=subnet.subnet_id,
                description=f"Public Subnet for {subnet.availability_zone}",
            )

        for i, eip in enumerate(self.vpc.public_subnets):
            if eip.node.try_find_child("EIP") is not None:
                CfnOutput(
                    self,
                    f"NatEip{i+1}",
                    value=eip.node.try_find_child("EIP").ref,
                    description=f"NAT EIP for {eip.availability_zone}",
                )

        for subnet in self.vpc.private_subnets:
            logger.info(f"Subnet Id: {subnet.subnet_id}")
            logger.info(f"Private Subnet Availability Zone: {subnet.availability_zone}")
            CfnOutput(
                self,
                f"PrivateSubnet{kebab_to_pascal(subnet.availability_zone)}",
                value=subnet.subnet_id,
                description=f"Private Subnet for {subnet.availability_zone}",
            )

        for subnet in self.vpc.isolated_subnets:
            logger.info(f"Isolated Subnet Id: {subnet.subnet_id}")
            logger.info(f"Isolated Subnet Availability Zone: {subnet.availability_zone}")
            CfnOutput(
                self,
                f"IsolatedSubnet{kebab_to_pascal(subnet.availability_zone)}",
                value=subnet.subnet_id,
                description=f"Isolated Subnet for {subnet.availability_zone}",
            )
