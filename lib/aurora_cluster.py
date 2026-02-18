import logging
from pathlib import Path

from aws_cdk import BundlingFileAccess, BundlingOptions, CustomResource, Duration, RemovalPolicy
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

from config.base_config import AuroraClusterConfig

logger = logging.getLogger(__name__)


class AuroraCluster(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        security_group: ec2.SecurityGroup,
        rds_lambda_security_group: ec2.SecurityGroup,
        aurora_cluster_config: AuroraClusterConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._vpc = vpc
        self._security_group = security_group
        self._rds_lambda_security_group = rds_lambda_security_group
        self._aurora_cluster_config = aurora_cluster_config
        self._cluster = self._create_cluster()

    @property
    def secret(self) -> sm.Secret:
        return sm.Secret.from_secret_complete_arn(self, "AuroraSecret", self._secret_arn_output)

    @property
    def jdbc_url(self) -> str:
        return f"jdbc:mysql://{self._cluster.cluster_endpoint.hostname}:{self._cluster.cluster_endpoint.port}/{self._aurora_cluster_config.default_database_name}"

    def _create_manage_master_user_password_lambda(self) -> lambda_.Function:
        """
        Create Lambda function to manage master user password.

        """
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

        # Add necessary permissions for RDS
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "rds:ModifyDBCluster",
                    "rds:DescribeDBClusters",
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

        LAMBDA_DIR = Path(__file__).resolve().parent / "aurora_cluster_lambda"

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
            security_groups=[self._rds_lambda_security_group],
            timeout=Duration.minutes(5),
            log_group=lambda_log_group,
        )

    def _create_cluster(self):
        subnet_group = rds.SubnetGroup(
            self,
            "RdsSubnetGroup",
            description="Subnet group for RDS in private subnets",
            vpc=self._vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=self._vpc.isolated_subnets),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Monitoring role for activating enhanced monitoring
        monitoring_role = iam.Role(
            self,
            "MonitoringRole",
            assumed_by=iam.ServicePrincipal("monitoring.rds.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonRDSEnhancedMonitoringRole"
                ),
            ],
        )

        # Basic cluster configuration
        cluster_config = {
            "writer": rds.ClusterInstance.serverless_v2("Writer"),
            "serverless_v2_min_capacity": self._aurora_cluster_config.serverless_v2_min_capacity,
            "serverless_v2_max_capacity": self._aurora_cluster_config.serverless_v2_max_capacity,
            "backup": rds.BackupProps(
                retention=Duration.days(self._aurora_cluster_config.backup_retention)
            ),
            "enable_performance_insights": True,
            "enable_cluster_level_enhanced_monitoring": True,
            "monitoring_role": monitoring_role,
            "monitoring_interval": Duration.seconds(30),
            "cloudwatch_logs_exports": ["audit", "error", "slowquery", "iam-db-auth-error"],
            "storage_encrypted": True,
            "vpc": self._vpc,
            "security_groups": [self._security_group],
            "subnet_group": subnet_group,
            "default_database_name": self._aurora_cluster_config.default_database_name,
            "removal_policy": RemovalPolicy.SNAPSHOT,
        }

        if self._aurora_cluster_config.engine == "mysql":
            cluster_config["engine"] = rds.DatabaseClusterEngine.aurora_mysql(
                version=rds.AuroraMysqlEngineVersion.VER_3_11_0
            )
            cluster_config["parameter_group"] = rds.ParameterGroup.from_parameter_group_name(
                self, "ParameterGroup", parameter_group_name="default.aurora-mysql8.0"
            )
        else:
            cluster_config["engine"] = rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_6
            )
            cluster_config["parameter_group"] = rds.ParameterGroup.from_parameter_group_name(
                self, "ParameterGroup", parameter_group_name="default.aurora-postgresql16"
            )

        if self._aurora_cluster_config.instance_reader_count > 0:
            readers = []
            for i in range(self._aurora_cluster_config.instance_reader_count):
                readers.append(
                    rds.ClusterInstance.serverless_v2(
                        f"Reader{i + 1}",
                        scale_with_writer=True,
                    )
                )
            cluster_config["readers"] = readers
        # If a snapshot is specified, use it for creation
        if self._aurora_cluster_config.snapshot_identifier:
            cluster_config["snapshot_identifier"] = self._aurora_cluster_config.snapshot_identifier
            cluster = rds.DatabaseClusterFromSnapshot(self, "Database", **cluster_config)
        else:
            cluster = rds.DatabaseCluster(self, "Database", **cluster_config)

        manage_master_user_password_lambda = self._create_manage_master_user_password_lambda()

        # Create KMS key for Aurora secrets
        aurora_kms_key = kms.Key(
            self,
            "AuroraSecretKmsKey",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Grant KMS permissions to Lambda
        aurora_kms_key.grant_encrypt_decrypt(manage_master_user_password_lambda.role)

        # Create custom resource
        custom_resource = CustomResource(
            self,
            "ManageMasterUserPassword",
            service_token=manage_master_user_password_lambda.function_arn,
            properties={"ClusterId": cluster.cluster_identifier, "KmsKeyId": aurora_kms_key.key_id},
            service_timeout=Duration.minutes(10),
        )

        # Add dependency on writer instance
        writer_instance = cluster.node.find_child("Writer")
        custom_resource.node.add_dependency(writer_instance)
        logger.info(f"add dependency on Writer instance: {writer_instance.node.id}")

        reader_instances = [
            cluster.node.find_child(f"Reader{i + 1}")
            for i in range(self._aurora_cluster_config.instance_reader_count)
        ]
        for reader_instance in reader_instances:
            custom_resource.node.add_dependency(reader_instance)
            logger.info(f"add dependency on Reader{i + 1} instance: {reader_instance.node.id}")

        self._secret_arn_output = custom_resource.get_att("SecretArn").to_string()

        return cluster
