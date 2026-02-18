import logging

from aws_cdk.assertions import Template

from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


def test_storage_stack_bucket_retention_prd(base_stage: BaseStage) -> None:
    """Ensure StorageStack S3 bucket is retained (not destroyed) in prd."""
    stack = base_stage.storage_stack
    template = Template.from_stack(stack)

    template_dict = template.to_json()
    logger.debug(template_dict)

    resources = template_dict.get("Resources", {})
    buckets = [res for res in resources.values() if res.get("Type") == "AWS::S3::Bucket"]

    # We expect exactly one storage bucket in this stack
    assert len(buckets) == 1
    bucket = buckets[0]

    # In prd, RemovalPolicy.RETAIN should be used:
    # DeletionPolicy and UpdateReplacePolicy must both be Retain.
    assert bucket.get("DeletionPolicy") == "Retain"
    assert bucket.get("UpdateReplacePolicy") == "Retain"
