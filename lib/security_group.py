from aws_cdk import Tags
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class SecurityGroup(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        security_group_name: str = "",
        description: str = "Security group",
        allow_all_outbound: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id)

        self.sg = ec2.SecurityGroup(
            self,
            construct_id,
            vpc=vpc,
            description=description,
            allow_all_outbound=allow_all_outbound,
        )
        if security_group_name:
            Tags.of(self.sg).add("Name", security_group_name)
