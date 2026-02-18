# utils/aspects.py
import aws_cdk.aws_s3 as s3
import jsii
from aws_cdk import IAspect, Stack


@jsii.implements(IAspect)
class BucketNamingAspect:
    def visit(self, node):
        # we look only for CfnBucket (S3) resources
        if isinstance(node, s3.CfnBucket):
            # we get the parent stack for context
            stack = Stack.of(node)
            # we check if a name is already defined
            if not node.bucket_name:
                # we apply our automatic naming logic
                # NOTE: This is a simplified example, the actual logic may be more complex
                node.bucket_name = f"{stack.stack_name}-{node.logical_id}".lower()
