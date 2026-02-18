import logging

from aws_cdk.assertions import Match, Template

from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


def test_security_stack_rules(base_stage: BaseStage):
    """Test security group rules in the security stack."""
    stack = base_stage.security_stack
    template = Template.from_stack(stack)

    # NOTE: This is for debugging purposes
    template_dict = template.to_json()
    logger.debug(template_dict)

    # Verify Security Group creation
    template.resource_count_is("AWS::EC2::SecurityGroup", 9)
    # ALB + RDS SGs + OSD API + ECS Shared

    # Verify ALB Security Group allows HTTP ingress
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "SecurityGroupIngress": Match.array_with(
                [
                    {
                        "CidrIp": "0.0.0.0/0",
                        "Description": "Allow HTTP traffic from any IP address",
                        "FromPort": 80,
                        "IpProtocol": "tcp",
                        "ToPort": 80,
                    },
                    {
                        "CidrIp": "0.0.0.0/0",
                        "Description": "Allow HTTPS traffic from any IP address",
                        "FromPort": 443,
                        "IpProtocol": "tcp",
                        "ToPort": 443,
                    },
                ]
            )
        },
    )


def test_security_stack_internal_ingress_relations(base_stage: BaseStage):
    """Test key internal ingress rules between security groups.

    Note: CDK creates separate AWS::EC2::SecurityGroupIngress resources
    when using add_ingress_rule(), not inline SecurityGroupIngress properties.
    """
    stack = base_stage.security_stack
    template = Template.from_stack(stack)

    template_dict = template.to_json()
    logger.debug(template_dict)

    resources = template_dict.get("Resources", {})

    # Helper to find SecurityGroup logical ID by tag name pattern
    def find_sg_logical_id(name_pattern):
        for logical_id, res in resources.items():
            if res.get("Type") != "AWS::EC2::SecurityGroup":
                continue
            props = res.get("Properties", {})
            tags = props.get("Tags", [])
            if any(name_pattern in tag.get("Value", "") for tag in tags):
                return logical_id
        return None

    # Helper to find SecurityGroupIngress resources targeting a specific SG
    def find_ingress_rules(target_sg_logical_id):
        ingress_rules = []
        for logical_id, res in resources.items():
            if res.get("Type") != "AWS::EC2::SecurityGroupIngress":
                continue
            props = res.get("Properties", {})
            # GroupId is a Fn::GetAtt reference, extract the referenced logical ID
            group_id = props.get("GroupId", {})
            if isinstance(group_id, dict) and "Fn::GetAtt" in group_id:
                referenced_id = group_id["Fn::GetAtt"][0]
                if referenced_id == target_sg_logical_id:
                    ingress_rules.append(props)
        return ingress_rules

    # 1. OSD API SG: ingress from ALB SG on ports 8080 and 2112
    osd_api_sg_id = find_sg_logical_id("osd-api-sg")
    assert osd_api_sg_id is not None, "OSD API SecurityGroup not found"
    osd_api_ingress = find_ingress_rules(osd_api_sg_id)
    osd_api_ports = sorted({r.get("FromPort") for r in osd_api_ingress if r.get("FromPort")})
    assert (
        8080 in osd_api_ports
    ), f"OSD API SG missing ingress on port 8080. Found ports: {osd_api_ports}"
    assert (
        2112 in osd_api_ports
    ), f"OSD API SG missing ingress on port 2112. Found ports: {osd_api_ports}"

    # 2. Keycloak SG: ingress from ALB SG on ports 8080 and 9000
    keycloak_sg_id = find_sg_logical_id("keycloak-sg")
    assert keycloak_sg_id is not None, "Keycloak SecurityGroup not found"
    keycloak_ingress = find_ingress_rules(keycloak_sg_id)
    keycloak_ports = sorted({r.get("FromPort") for r in keycloak_ingress if r.get("FromPort")})
    assert (
        8080 in keycloak_ports
    ), f"Keycloak SG missing ingress on port 8080. Found ports: {keycloak_ports}"
    assert (
        9000 in keycloak_ports
    ), f"Keycloak SG missing ingress on port 9000. Found ports: {keycloak_ports}"

    # 3. DocDB SG: ingress from OSD API SG on port 27017
    docdb_sg_id = find_sg_logical_id("docdb-sg")
    assert docdb_sg_id is not None, "DocDB SecurityGroup not found"
    docdb_ingress = find_ingress_rules(docdb_sg_id)
    docdb_ports = {r.get("FromPort") for r in docdb_ingress if r.get("FromPort")}
    assert (
        27017 in docdb_ports
    ), f"DocDB SG missing ingress on port 27017. Found ports: {docdb_ports}"

    # 4. Redis SG: ingress from OSD API SG on port 6379
    redis_sg_id = find_sg_logical_id("redis-sg")
    assert redis_sg_id is not None, "Redis SecurityGroup not found"
    redis_ingress = find_ingress_rules(redis_sg_id)
    redis_ports = {r.get("FromPort") for r in redis_ingress if r.get("FromPort")}
    assert 6379 in redis_ports, f"Redis SG missing ingress on port 6379. Found ports: {redis_ports}"

    # 5. RDS SG: ingress from Keycloak SG and Aurora Lambda SG on port 3306
    rds_sg_id = find_sg_logical_id("rds-sg")
    assert rds_sg_id is not None, "RDS SecurityGroup not found"
    rds_ingress = find_ingress_rules(rds_sg_id)
    rds_ports = {r.get("FromPort") for r in rds_ingress if r.get("FromPort")}
    assert 3306 in rds_ports, f"RDS SG missing ingress on port 3306. Found ports: {rds_ports}"
    # Verify at least 2 ingress rules for RDS (Keycloak + Lambda)
    assert (
        len([r for r in rds_ingress if r.get("FromPort") == 3306]) >= 2
    ), "RDS SG should have at least 2 ingress rules on port 3306"

    # 6. ECS Shared SG: self-referencing ingress (all traffic)
    ecs_shared_sg_id = find_sg_logical_id("ecs-shared-sg")
    assert ecs_shared_sg_id is not None, "ECS Shared SecurityGroup not found"
    ecs_shared_ingress = find_ingress_rules(ecs_shared_sg_id)
    # Should have at least one rule with IpProtocol "-1" (all traffic)
    assert any(
        r.get("IpProtocol") == "-1" for r in ecs_shared_ingress
    ), "ECS Shared SG should allow all traffic within the same security group"
