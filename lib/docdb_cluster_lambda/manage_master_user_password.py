import json
import logging
import time

import boto3
import cfnresponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    # NOTE:
    # This Lambda is invoked by CloudFormation as part of a Custom Resource lifecycle.
    # The value of event["RequestType"] reflects the state of the Custom Resource itself,
    # not the Lambda nor the CloudFormation stack as a whole.
    #
    # Possible values:
    # - "Create": CloudFormation is creating the Custom Resource
    # - "Update": CloudFormation is updating the Custom Resource (when its properties change)
    # - "Delete": CloudFormation is deleting the Custom Resource
    #
    # The handler must be idempotent and handle these states explicitly.
    # In this case, the master user password is only managed during Create.
    # No action is required during Delete.
    if event["RequestType"] in ["Create"]:
        try:
            docdb_client = boto3.client("docdb")

            # Get parameters
            cluster_id = event["ResourceProperties"]["ClusterId"]
            logger.info(f"Cluster ID: {cluster_id}")
            instance_id = event["ResourceProperties"]["InstanceId"]
            logger.info(f"Instance ID: {instance_id}")
            kms_key_id = event["ResourceProperties"]["KmsKeyId"]
            logger.info(f"KMS Key ID: {kms_key_id}")

            # Enable manage_master_user_password
            docdb_client.modify_db_cluster(
                DBClusterIdentifier=cluster_id,
                ManageMasterUserPassword=True,
                RotateMasterUserPassword=False,
                MasterUserSecretKmsKeyId=kms_key_id,
                ApplyImmediately=True,
            )

            # Wait for the modification to be applied
            logger.info(f"Waiting for cluster {cluster_id} to be modified...")
            time.sleep(60)

            logger.info(
                f"Successfully enabled manage_master_user_password for cluster {cluster_id}"
            )
            response = docdb_client.describe_db_clusters(DBClusterIdentifier=cluster_id)
            secret_arn = response["DBClusters"][0].get("MasterUserSecret", {}).get("SecretArn")

            logger.info(f"Cancelling rotation for secret {secret_arn}")
            secretsmanager = boto3.client("secretsmanager")
            secretsmanager.cancel_rotate_secret(SecretId=secret_arn)
            logger.info(f"Rotation cancelled for secret {secret_arn}")

            cfnresponse.send(event, context, cfnresponse.SUCCESS, {"SecretArn": secret_arn})
        except Exception as e:
            logger.info(f"Error cancelling rotation for secret {secret_arn}: {str(e)}")
            cfnresponse.send(event, context, cfnresponse.FAILED, {"SecretArn": "Unknown"})
    else:
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {"SecretArn": "Unknown"})
