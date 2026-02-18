import logging

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config.base_config import AngularBuildConfig
from config.loader import InfrastructureContext

logger = logging.getLogger(__name__)


class AngularPipeline(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        cloudfront_bucket_name: str,
        cloudfront_distribution_id: str,
        angular_build_config: AngularBuildConfig,
        infra_context: InfrastructureContext,
        **kwargs,
    ) -> None:
        """
        Create a CodePipeline for building Angular applications.

        Args:
            scope: Parent construct
            construct_id: Construct ID
            cloudfront_bucket_name: Name of the S3 bucket linked to CloudFront (where built files will be deployed)
            cloudfront_distribution_id: CloudFront distribution ID to invalidate after build
            angular_build_config: Configuration for the Angular build

        """
        super().__init__(scope, construct_id, **kwargs)

        self._cloudfront_bucket_name = cloudfront_bucket_name
        self._cloudfront_distribution_id = cloudfront_distribution_id
        self._angular_build_config = angular_build_config
        self._infra_context = infra_context

        logger.info(f"Angular build config: {angular_build_config}")

        self._source_bucket = self._get_source_bucket()
        if self._angular_build_config.source_bucket_key is None:
            self._source_bucket_key = f"{self._infra_context.context.tenant_name}-{self._infra_context.context.env_name}-front.zip"
        else:
            self._source_bucket_key = self._angular_build_config.source_bucket_key

        self._cloudfront_bucket = self._get_cloudfront_bucket()
        self._build_project = self._create_build_project()
        self._pipeline = self._create_pipeline()

        logger.info("Angular pipeline created successfully")

    @property
    def pipeline(self) -> codepipeline.Pipeline:
        return self._pipeline

    def _get_source_bucket(self) -> s3.IBucket:
        """Get or reference the source S3 bucket."""
        # Generate bucket name dynamically if not provided
        if self._angular_build_config.source_bucket_name is None:
            region = self._infra_context.config.aws.region_str
            bucket_name = f"appfront-{region}"
            logger.info(f"Source bucket name not provided, generating from region: {bucket_name}")
        else:
            bucket_name = self._angular_build_config.source_bucket_name
            logger.info(f"Retrieving source bucket: {bucket_name}")

        return s3.Bucket.from_bucket_name(
            self,
            "SourceBucket",
            bucket_name=bucket_name,
        )

    def _get_cloudfront_bucket(self) -> s3.IBucket:
        """Get or reference the CloudFront S3 bucket."""
        logger.info(f"Retrieving CloudFront bucket: {self._cloudfront_bucket_name}")
        return s3.Bucket.from_bucket_name(
            self,
            "CloudFrontBucket",
            self._cloudfront_bucket_name,
        )

    def _create_build_project(self) -> codebuild.PipelineProject:
        """Create a CodeBuild project for building Angular applications."""
        logger.info("Creating CodeBuild project...")

        # IAM role for CodeBuild
        build_role = iam.Role(
            self,
            "BuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess"),
            ],
        )

        # Grant permissions to read from source bucket
        self._source_bucket.grant_read(build_role)

        # Grant permissions to write to CloudFront bucket
        self._cloudfront_bucket.grant_read_write(build_role, objects_key_pattern="osd/*")

        # Grant permissions to create CloudFront invalidations
        build_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudfront:CreateInvalidation",
                    "cloudfront:GetInvalidation",
                ],
                resources=[
                    f"arn:aws:cloudfront::*:distribution/{self._cloudfront_distribution_id}"
                ],
            )
        )

        # Check if source is a pre-built zip (different from angular-generic.zip)
        is_pre_built = self._source_bucket_key != "angular-generic.zip"
        logger.info(f"Source bucket key: {self._source_bucket_key}, is_pre_built: {is_pre_built}")

        # Define environment variables for CodeBuild
        build_environment_variables = {
            "THEME": codebuild.BuildEnvironmentVariable(value=self._angular_build_config.theme),
            "API_URL": codebuild.BuildEnvironmentVariable(
                value=self._infra_context.config.domain.records["api_domain_name"]
            ),
            "LOGO": codebuild.BuildEnvironmentVariable(value=self._angular_build_config.logo),
            "ANGULAR_CONFIG": codebuild.BuildEnvironmentVariable(
                value=self._angular_build_config.config
            ),
            "CLOUDFRONT_BUCKET_NAME": codebuild.BuildEnvironmentVariable(
                value=self._cloudfront_bucket_name
            ),
            "CLOUDFRONT_DISTRIBUTION_ID": codebuild.BuildEnvironmentVariable(
                value=self._cloudfront_distribution_id
            ),
            "SOURCE_BUCKET_KEY": codebuild.BuildEnvironmentVariable(value=self._source_bucket_key),
        }

        if is_pre_built:
            # Pre-built zip: just extract and sync to S3
            logger.info("Using pre-built zip mode - skipping build steps")
            install_commands = [
                "echo 'Pre-built zip detected - skipping build steps'",
                "echo 'Installing unzip if needed...'",
                "which unzip || (apt-get update && apt-get install -y unzip)",
            ]

            pre_build_commands = [
                "echo 'Pre-built files already extracted by CodePipeline'",
                "echo 'Verifying dist/ directory exists...'",
                "ls -la dist/ || (echo 'Error: dist/ directory not found'; exit 1)",
            ]

            build_commands = [
                "echo 'Syncing pre-built files to CloudFront bucket...'",
                "aws s3 sync dist/ s3://$CLOUDFRONT_BUCKET_NAME/ --delete",
                "echo 'Creating CloudFront invalidation...'",
                "aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths '/*'",
            ]
        else:
            # Full build: install dependencies and build Angular app
            logger.info("Using full build mode - building Angular application")
            install_commands = [
                "echo 'Updating npm to latest version...'",
                "npm install -g npm@latest",
                "echo 'Verifying npm version...'",
                "npm --version",
                "echo 'Verifying Node.js version...'",
                "node --version",
            ]

            pre_build_commands = [
                "echo 'Cleaning npm cache...'",
                "npm cache clean --force",
                "echo 'Verifying package.json and package-lock.json exist...'",
                "ls -la package*.json || echo 'Warning: package files not found'",
                "echo 'Checking disk space...'",
                "df -h",
                "echo 'Environment variables:'",
                'echo "  THEME=$THEME"',
                'echo "  API_URL=$API_URL"',
                'echo "  LOGO=$LOGO"',
                'echo "  ANGULAR_CONFIG=$ANGULAR_CONFIG"',
                'echo "  CLOUDFRONT_BUCKET_NAME=$CLOUDFRONT_BUCKET_NAME"',
                'echo "  CLOUDFRONT_DISTRIBUTION_ID=$CLOUDFRONT_DISTRIBUTION_ID"',
            ]

            build_commands = [
                "echo 'Listing directory contents...'",
                "ls -la",
                "echo 'Installing dependencies with npm ci...'",
                "npm ci --verbose",
                "echo 'Running pre-build with theme...'",
                "npm run pre-build -- theme=$THEME api=https://$API_URL logo=$LOGO",
                "echo 'Building Angular application...'",
                "npm run ng -- build --configuration=$ANGULAR_CONFIG",
                "echo 'Uploading build artifacts to CloudFront bucket...'",
                "aws s3 sync dist/ s3://$CLOUDFRONT_BUCKET_NAME/ --delete",
                "echo 'Creating CloudFront invalidation...'",
                "aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths '/*'",
            ]

        # Build spec configuration - conditionally include Node.js runtime for full builds
        build_spec_dict = {
            "version": "0.2",
            "phases": {
                "install": {
                    "commands": install_commands,
                },
                "pre_build": {
                    "commands": pre_build_commands,
                },
                "build": {
                    "commands": build_commands,
                },
            },
        }

        # Only add Node.js runtime for full builds (not for pre-built zips)
        if not is_pre_built:
            build_spec_dict["phases"]["install"]["runtime-versions"] = {
                "nodejs": "20",
            }

        codebuild_parameters = {
            "role": build_role,
            "environment": codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
                environment_variables=build_environment_variables,
            ),
            "build_spec": codebuild.BuildSpec.from_object(build_spec_dict),
            "timeout": Duration.minutes(10),
            "logging": codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=logs.LogGroup(self, "AngularCodeBuildLogGroup")
                )
            ),
        }

        if not is_pre_built:
            # TODO: Temporary VPC configuration - to be removed later
            # Reference existing VPC ops, subnets, and security group
            logger.info("Using temporary VPC configuration")
            vpc = ec2.Vpc.from_lookup(
                self,
                "TempVpc",
                vpc_id="vpc-008921643605147cd",
            )
            subnet1 = ec2.Subnet.from_subnet_id(self, "TempSubnet1", "subnet-01f3a7f2bcd837542")
            subnet2 = ec2.Subnet.from_subnet_id(self, "TempSubnet2", "subnet-0ceb4118ba5283f9d")
            security_group = ec2.SecurityGroup.from_security_group_id(
                self, "TempSecurityGroup", "sg-0082d105190a22362"
            )
            codebuild_parameters["vpc"] = vpc
            codebuild_parameters["subnet_selection"] = ec2.SubnetSelection(
                subnets=[subnet1, subnet2]
            )
            codebuild_parameters["security_groups"] = [security_group]

        build_project = codebuild.PipelineProject(
            self,
            "BuildProject",
            **codebuild_parameters,
        )

        logger.info("CodeBuild project created successfully")
        return build_project

    def _create_pipeline(self) -> codepipeline.Pipeline:
        """Create the CodePipeline with S3 source and CodeBuild action."""
        logger.info("Creating CodePipeline...")

        # Create artifacts bucket with DESTROY removal policy
        artifacts_bucket = s3.Bucket(
            self,
            "ArtifactsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,  # Automatically delete objects when bucket is deleted
        )
        logger.info(f"Artifacts bucket created: {artifacts_bucket.bucket_name}")

        # Artifact for source
        source_artifact = codepipeline.Artifact("SourceArtifact")

        # Artifact for build output (optional, not used but required by CodeBuild action)
        build_artifact = codepipeline.Artifact("BuildArtifact")

        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            artifact_bucket=artifacts_bucket,
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        codepipeline_actions.S3SourceAction(
                            action_name="S3Source",
                            bucket=self._source_bucket,
                            bucket_key=self._source_bucket_key,
                            output=source_artifact,
                            trigger=codepipeline_actions.S3Trigger.POLL,
                        ),
                    ],
                ),
                codepipeline.StageProps(
                    stage_name="Build",
                    actions=[
                        codepipeline_actions.CodeBuildAction(
                            action_name="BuildAngular",
                            project=self._build_project,
                            input=source_artifact,
                            outputs=[build_artifact],
                        ),
                    ],
                ),
            ],
        )

        # Grant CodePipeline role permissions to start CodeBuild builds
        # This is needed when the pipeline tries to start a build immediately after creation
        pipeline.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "codebuild:StartBuild",
                    "codebuild:StopBuild",
                    "codebuild:BatchGetBuilds",
                ],
                resources=[self._build_project.project_arn],
            )
        )

        pipeline.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:GetBucketVersioning",
                    "s3:ListBucket",
                ],
                resources=[self._source_bucket.bucket_arn, f"{self._source_bucket.bucket_arn}/*"],
            )
        )

        logger.info("CodePipeline created successfully")
        return pipeline
