import logging

from aws_cdk import Tags
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk.aws_ec2 import GatewayVpcEndpointAwsService, InterfaceVpcEndpointAwsService
from constructs import Construct

from config.base_config import VpcConfig
from config.loader import Context

logger = logging.getLogger(__name__)

SUBNET_CONFIGURATION = [
    ec2.SubnetConfiguration(
        name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24, map_public_ip_on_launch=True
    ),
    ec2.SubnetConfiguration(
        name="isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
    ),
    ec2.SubnetConfiguration(
        name="private",
        subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
        cidr_mask=24,
    ),
]


class ClassicVpc(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc_config: VpcConfig,
        context: Context = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id)
        self._vpc_config = vpc_config
        self._context = context
        logger.info("Creating VPC...")
        logger.info(f"VPC parameters: {self._vpc_config}")

        self._vpc = self._create_vpc()
        self._add_vpc_endpoints()
        self._tag_subnets()
        self.activate_flow_logs()
        # self._tag_other_vpc_resources()

        logger.info("VPC created successfully")

    @property
    def vpc(self) -> ec2.Vpc:
        return self._vpc

    def _create_vpc(self) -> ec2.Vpc:
        vpc = ec2.Vpc(
            self,
            "Vpc",
            # vpc_name=self.config.prefix("vpc"),
            ip_addresses=ec2.IpAddresses.cidr(self._vpc_config.cidr),
            max_azs=self._vpc_config.reserved_azs,
            reserved_azs=self._vpc_config.reserved_azs,
            nat_gateways=self._vpc_config.nat_gateways,
            subnet_configuration=SUBNET_CONFIGURATION,
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )
        return vpc

    def _add_vpc_endpoints(self):
        self.vpc.add_gateway_endpoint("S3Endpoint", service=GatewayVpcEndpointAwsService.S3)

        self.vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=InterfaceVpcEndpointAwsService.ECR_DOCKER,
        )

        self.vpc.add_interface_endpoint(
            "EcrApiEndpoint",
            service=InterfaceVpcEndpointAwsService.ECR,
        )

    def activate_flow_logs(self):
        flow_log_group = logs.LogGroup(
            self,
            "FlowLogLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        flow_log_role = iam.Role(
            self,
            "FlowLogRole",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
        )
        flow_log_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                ],
                resources=["*"],
            )
        )
        flow_log_group.grant_write(flow_log_role)
        self.vpc.add_flow_log(
            "FlowLog",
            traffic_type=ec2.FlowLogTrafficType.ALL,
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                log_group=flow_log_group,
                iam_role=flow_log_role,
            ),
        )

    def _tag_subnets(self):
        for subnet in self.vpc.public_subnets:
            # Tags.of(subnet).add(
            #     "Name",
            #      self._config.kebab_prefix( f"public-subnet-{subnet.availability_zone}")
            # )
            Tags.of(subnet).add("Az", subnet.availability_zone)

        for subnet in self.vpc.private_subnets:
            # Tags.of(subnet).add(
            #     "Name",
            #     self._config.kebab_prefix( f"private-subnet-{subnet.availability_zone}")
            # )
            Tags.of(subnet).add("Az", subnet.availability_zone)

        for subnet in self.vpc.isolated_subnets:
            # Tags.of(subnet).add(
            #     "Name",
            #     self._config.kebab_prefix( f"isolated-subnet-{subnet.availability_zone}")
            # )
            Tags.of(subnet).add("Az", subnet.availability_zone)

    def _tag_other_vpc_resources(self):
        """
        Add tags to the resources of the VPC.

        Args:
            common_tags: Dictionary containing common tags for all resources
        """
        nat_gateways = []
        internet_gateways = []
        eips = []

        all_resources = self.vpc.node.find_all()
        for child in all_resources:
            # NAT Gateways
            if isinstance(child, ec2.CfnNatGateway):
                nat_gateways.append(child)
            # Internet Gateway
            if isinstance(child, ec2.CfnInternetGateway):
                internet_gateways.append(child)

            if isinstance(child, ec2.CfnEIP):
                eips.append(child)

        for index, nat_gateway in enumerate(nat_gateways):
            Tags.of(nat_gateway).add("Name", self._context.kebab_prefix(f"nat-gateway-{index+1}"))

        for index, internet_gateway in enumerate(internet_gateways):
            Tags.of(internet_gateway).add("Name", self._context.kebab_prefix(f"igw-{index+1}"))

        for index, eip in enumerate(eips):
            Tags.of(eip).add("Name", self._context.kebab_prefix(f"eip-{index+1}"))
