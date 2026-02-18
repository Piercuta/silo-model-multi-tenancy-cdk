"""
Lambda function to clean up ACM DNS validation records from Route53 hosted zone.

This Lambda is triggered by a CloudFormation custom resource during stack deletion
to remove DNS validation records created by ACM before the hosted zone is deleted.
"""

import json
import logging
from typing import Any, Dict

import boto3
import urllib3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

route53 = boto3.client("route53")

http = urllib3.PoolManager()


def send_response(event, context, status, data=None, reason=None):
    response_body = {
        "Status": status,
        "Reason": reason or f"See CloudWatch Log Stream: {context.log_stream_name}",
        "PhysicalResourceId": context.log_stream_name,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": data or {},
    }

    encoded = json.dumps(response_body).encode("utf-8")

    logger.info("=== Sending CloudFormation response ===")
    logger.info(f"ResponseURL: {event['ResponseURL']}")
    logger.info(f"Payload: {json.dumps(response_body, indent=2)}")

    response = http.request(
        "PUT",
        event["ResponseURL"],
        body=encoded,
        headers={"content-type": "", "content-length": str(len(encoded))},
    )

    # http responses logs
    logger.info("=== CloudFormation response result ===")
    logger.info(f"Status code: {response.status}")
    logger.info(f"Headers: {response.headers}")
    logger.info(f"Raw response data: {response.data}")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle CloudFormation custom resource events.

    Args:
        event: CloudFormation custom resource event
        context: Lambda context

    Returns:
        Response dictionary for CloudFormation
    """
    logger.info(f"Received event: {json.dumps(event)}")

    request_type = event.get("RequestType")
    hosted_zone_id = event.get("ResourceProperties", {}).get("HostedZoneId")

    if not hosted_zone_id:
        raise ValueError("HostedZoneId is required")

    response_data: Dict[str, Any] = {}

    try:
        if request_type in ["Create", "Update"]:
            # No action needed on create/update
            logger.info(f"No action needed for {request_type}")
            response_data["Message"] = f"Custom resource {request_type} completed"

        elif request_type == "Delete":
            # Clean up DNS validation records before hosted zone deletion
            logger.info(f"Deleting DNS validation records from hosted zone: {hosted_zone_id}")
            deleted_count = delete_acm_validation_records(hosted_zone_id)
            response_data["Message"] = f"Deleted {deleted_count} DNS validation records"
            logger.info(f"Successfully deleted {deleted_count} DNS validation records")

        else:
            raise ValueError(f"Unknown request type: {request_type}")

        send_response(event, context, "SUCCESS")

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        send_response(event, context, "SUCCESS")


def delete_acm_validation_records(hosted_zone_id: str) -> int:
    """
    Delete ACM DNS validation records from the hosted zone.

    ACM validation records are typically CNAME records with names like:
    - _acme-challenge.<domain>
    - <random-string>._acme-challenge.<domain>

    Args:
        hosted_zone_id: Route53 hosted zone ID

    Returns:
        Number of records deleted
    """
    deleted_count = 0

    try:
        # List all resource record sets in the hosted zone
        paginator = route53.get_paginator("list_resource_record_sets")
        pages = paginator.paginate(HostedZoneId=hosted_zone_id)

        changes = []

        for page in pages:
            for record_set in page.get("ResourceRecordSets", []):
                record_name = record_set.get("Name", "").rstrip(".")
                record_type = record_set.get("Type")

                # Skip system records (NS and SOA records are required and cannot be deleted)
                if record_type in ["NS", "SOA"]:
                    continue

                # Check if this is an ACM validation record
                # Only delete records that are definitively ACM validation records
                if record_type == "CNAME" and is_acm_validation_record(record_set):
                    logger.info(f"Found ACM validation record: {record_name} (Type: {record_type})")
                    changes.append(
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": record_set,
                        }
                    )

        # Delete records in batches (Route53 allows up to 1000 changes per request)
        if changes:
            # Route53 allows up to 1000 changes per ChangeBatch
            batch_size = 1000
            for i in range(0, len(changes), batch_size):
                batch = changes[i : i + batch_size]
                logger.info(f"Deleting batch of {len(batch)} records")

                route53.change_resource_record_sets(
                    HostedZoneId=hosted_zone_id,
                    ChangeBatch={
                        "Comment": "Delete ACM DNS validation records before hosted zone deletion",
                        "Changes": batch,
                    },
                )
                deleted_count += len(batch)

            logger.info(f"Total records deleted: {deleted_count}")
        else:
            logger.info("No ACM validation records found to delete")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "NoSuchHostedZone":
            logger.warning(f"Hosted zone {hosted_zone_id} not found, may have been already deleted")
            return deleted_count
        else:
            logger.error(f"Error deleting records: {str(e)}")
            raise

    return deleted_count


def is_acm_validation_record(record_set: Dict[str, Any]) -> bool:
    """
    Check if a record set is likely an ACM validation record.

    ACM validation records have specific patterns:
    - CNAME records with values pointing to *.acm-validations.aws.
    - Names often start with underscore followed by random hash
    - Example: _fa25f9273eb453c881d83cef57080322.app.dev.example.com
    - Value: _c5d831f4b485c2849190d07123084b2c.jkddzztszm.acm-validations.aws.

    Args:
        record_set: Route53 resource record set

    Returns:
        True if likely an ACM validation record
    """
    record_name = record_set.get("Name", "").lower()
    record_type = record_set.get("Type")

    # ACM validation records are CNAME records
    if record_type != "CNAME":
        return False

    # Check for ACM validation patterns in the name
    # ACM sometimes uses _acme-challenge subdomain
    if "_acme-challenge" in record_name:
        return True

    # Check if the record value points to ACM validation endpoints
    # ACM validation records always point to *.acm-validations.aws.
    resource_records = record_set.get("ResourceRecords", [])
    for record in resource_records:
        value = record.get("Value", "").lower().rstrip(".")
        # The definitive pattern: ends with .acm-validations.aws
        if value.endswith(".acm-validations.aws"):
            logger.info(f"Found ACM validation record by value pattern: {record_name} -> {value}")
            return True
        # Also check for variations
        if ".acm-validations.aws" in value:
            logger.info(
                f"Found ACM validation record by value pattern (variation): {record_name} -> {value}"
            )
            return True

    # Check if name pattern matches ACM validation (starts with underscore + hash)
    # Pattern: _<hash>.<domain>
    if record_name.startswith("_"):
        name_parts = record_name.split(".")
        # If first part after underscore looks like a hash (32+ hex chars), likely ACM validation
        if len(name_parts) > 0 and len(name_parts[0]) > 30:
            logger.info(f"Found potential ACM validation record by name pattern: {record_name}")
            return True

    return False
