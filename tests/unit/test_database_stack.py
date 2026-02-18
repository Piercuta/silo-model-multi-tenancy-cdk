import logging

from aws_cdk.assertions import Template

from stages.base_stage import BaseStage

logger = logging.getLogger(__name__)


def test_database_stack_creates_docdb_cluster(base_stage: BaseStage) -> None:
    """Ensure DatabaseStack creates a DocumentDB cluster with expected basics."""
    stack = base_stage.database_stack
    template = Template.from_stack(stack)

    # For debugging / snapshotting if needed
    template_dict = template.to_json()
    logger.debug(template_dict)

    # We expect exactly one DocDB cluster
    template.resource_count_is("AWS::DocDB::DBCluster", 1)


def test_database_stack_creates_redis_cluster(base_stage: BaseStage) -> None:
    """Ensure DatabaseStack creates a Redis/ElastiCache cluster."""
    stack = base_stage.database_stack
    template = Template.from_stack(stack)

    template_dict = template.to_json()
    logger.debug(template_dict)

    # Depending on the construct implementation this may be ReplicationGroup or CacheCluster.
    # Here we just assert at least one Redis-related resource exists.
    redis_resource_types = [
        "AWS::ElastiCache::ReplicationGroup",
        "AWS::ElastiCache::CacheCluster",
    ]

    has_redis = any(
        template.to_json().get("Resources", {}).get(logical_id, {}).get("Type")
        in redis_resource_types
        for logical_id in template.to_json().get("Resources", {})
    )

    assert has_redis, "Expected at least one Redis-related resource in DatabaseStack"


def test_database_stack_creates_aurora_cluster(base_stage: BaseStage) -> None:
    """Ensure DatabaseStack creates an Aurora cluster."""
    stack = base_stage.database_stack
    template = Template.from_stack(stack)

    template_dict = template.to_json()
    logger.debug(template_dict)

    # We expect at least one RDS::DBCluster (Aurora) in the stack
    template.resource_count_is("AWS::RDS::DBCluster", 1)


def test_database_stack_retention_policies_prd(base_stage: BaseStage) -> None:
    """Ensure Aurora and DocDB clusters use snapshot retention policy in prd."""
    stack = base_stage.database_stack
    template = Template.from_stack(stack)

    resources = template.to_json().get("Resources", {})

    # Find Aurora DBCluster and DocDB DBCluster logical IDs
    aurora_clusters = [
        res for res in resources.values() if res.get("Type") == "AWS::RDS::DBCluster"
    ]
    docdb_clusters = [
        res for res in resources.values() if res.get("Type") == "AWS::DocDB::DBCluster"
    ]

    assert len(aurora_clusters) == 1
    assert len(docdb_clusters) == 1

    aurora = aurora_clusters[0]
    docdb = docdb_clusters[0]

    # CDK RemovalPolicy.SNAPSHOT should translate to CloudFormation Snapshot policies
    assert aurora.get("DeletionPolicy") == "Snapshot"
    assert aurora.get("UpdateReplacePolicy") == "Snapshot"
    assert docdb.get("DeletionPolicy") == "Snapshot"
    assert docdb.get("UpdateReplacePolicy") == "Snapshot"
