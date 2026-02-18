import logging

from aws_cdk.assertions import Template

from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


def test_application_stack_creates_expected_ecs_services(base_stage: BaseStage) -> None:
    """Ensure ApplicationStack creates one ECS service per configured ECS service."""
    stack = base_stage.application_stack
    template = Template.from_stack(stack)

    template_dict = template.to_json()
    logger.debug(template_dict)

    # Count ECS::Service resources in the synthesized template
    resources = template_dict.get("Resources", {})
    ecs_services_in_template = [
        r for r in resources.values() if r.get("Type") == "AWS::ECS::Service"
    ]

    # In the mock_infra_context we define 5 ECS services (osd_api, review,
    # content_quality, document_history, keycloak).
    # ApplicationStack may create additional internal services in the future, so we
    # assert at least those 5 exist.
    assert len(ecs_services_in_template) >= 5


def test_application_stack_dns_records(base_stage: BaseStage) -> None:
    """Ensure ApplicationStack creates Route53 CNAME records for API and SSO."""
    stack = base_stage.application_stack
    template = Template.from_stack(stack)

    template_dict = template.to_json()
    logger.debug(template_dict)

    # Expect exactly two CNAME records (API + Keycloak/SSO)
    template.resource_count_is("AWS::Route53::RecordSet", 2)
