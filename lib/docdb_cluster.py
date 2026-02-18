import logging
from pathlib import Path

from aws_cdk import BundlingFileAccess, BundlingOptions, CustomResource, Duration, RemovalPolicy
from aws_cdk import aws_docdb as docdb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from config.base_config import DocDBConfig

logger = logging.getLogger(__name__)


class DocDBCluster(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        security_group: ec2.SecurityGroup,
        docdb_lambda_security_group: ec2.SecurityGroup,
        docdb_config: DocDBConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id)

        self._vpc = vpc
        self._security_group = security_group
        self._docdb_lambda_security_group = docdb_lambda_security_group
        self._docdb_config = docdb_config

        logger.info("Creating DocumentDB cluster...")
        logger.info(f"DocumentDB cluster parameters: {self._docdb_config}")

        self._cluster = self._create_cluster()

        logger.info("DocumentDB cluster created successfully")

    @property
    def cluster(self) -> docdb.DatabaseCluster:
        return self._cluster

    @property
    def secret_arn(self) -> str:
        return self._secret_arn_output

    def _create_manage_master_user_password_lambda(self) -> lambda_.Function:
        # Create Lambda role
        lambda_role = iam.Role(
            self,
            "ManageMasterUserPasswordLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Add necessary permissions for DocDB
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    # NOTE: docdb need rds right
                    "rds:ModifyDBCluster",
                    "rds:DescribeDBClusters",
                    "rds:ModifyDBInstance",
                    "rds:DescribeDBInstances",
                    "docdb:*",
                    "secretsmanager:*",
                    "kms:*",
                ],
                resources=["*"],
            )
        )

        # Create log group for Lambda
        lambda_log_group = logs.LogGroup(
            self,
            "ManageMasterUserPasswordLambdaLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        LAMBDA_DIR = Path(__file__).resolve().parent / "docdb_cluster_lambda"

        # Create Lambda function
        return lambda_.Function(
            self,
            "ManageMasterUserPasswordLambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="manage_master_user_password.handler",
            code=lambda_.Code.from_asset(
                str(LAMBDA_DIR),
                bundling=BundlingOptions(
                    bundling_file_access=BundlingFileAccess.VOLUME_COPY,
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                ),
            ),
            role=lambda_role,
            vpc=self._vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=self._vpc.private_subnets),
            security_groups=[self._docdb_lambda_security_group],
            timeout=Duration.minutes(5),
            log_group=lambda_log_group,
        )

    def _create_cluster(self) -> docdb.DatabaseCluster:
        cluster_config = {
            "master_user": docdb.Login(
                username=self._docdb_config.master_username,  # NOTE: 'admin' is reserved by DocumentDB
                exclude_characters='"@/:',  # optional, defaults to the set "\"@/" and is also used for eventually created rotations
            ),
            "backup": docdb.BackupProps(
                retention=Duration.days(self._docdb_config.backup_retention),
            ),
            "instance_type": ec2.InstanceType(self._docdb_config.db_instance_type),
            "storage_type": docdb.StorageType.IOPT1,
            "storage_encrypted": self._docdb_config.storage_encrypted,
            "vpc": self._vpc,
            "vpc_subnets": ec2.SubnetSelection(subnets=self._vpc.isolated_subnets),
            "security_group": self._security_group,
            "copy_tags_to_snapshot": True,
            "removal_policy": RemovalPolicy.SNAPSHOT,
            "export_audit_logs_to_cloud_watch": True,
            "export_profiler_logs_to_cloud_watch": True,
        }

        if self._docdb_config.snapshot_identifier:
            cluster = docdb.DatabaseCluster(self, "DocDBCluster", **cluster_config)
            cfn_cluster = cluster.node.default_child
            cfn_cluster.snapshot_identifier = self._docdb_config.snapshot_identifier
        else:
            cluster = docdb.DatabaseCluster(self, "DocDBCluster", **cluster_config)

        manage_master_user_password_lambda = self._create_manage_master_user_password_lambda()

        # Create KMS key for DocDB secrets
        docdb_kms_key = kms.Key(
            self,
            "DocDBSecretKmsKey",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Grant KMS permissions to Lambda
        docdb_kms_key.grant_encrypt_decrypt(manage_master_user_password_lambda.role)

        # Create custom resource
        custom_resource = CustomResource(
            self,
            "ManageMasterUserPassword",
            service_token=manage_master_user_password_lambda.function_arn,
            properties={
                "ClusterId": cluster.cluster_identifier,
                "InstanceId": cluster.instance_identifiers[0],
                "KmsKeyId": docdb_kms_key.key_id,
            },
            service_timeout=Duration.minutes(10),
        )

        # Add dependency on writer instance
        # logger.info(f"Cluster nodes: {cluster.node.find_all()}")
        # instance_node = cluster.node.find_child("CfnDBInstance")
        # custom_resource.node.add_dependency(instance_node)
        self._secret_arn_output = custom_resource.get_att("SecretArn").to_string()

        return cluster
