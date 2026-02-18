# Creating a New Tenant - Step by Step Guide

This guide walks you through the complete process of creating a new tenant in the OSD CDK infrastructure.

## Prerequisites

- Access to AWS Organization (to create new accounts)
- Access to the principal AWS account (777777777777)
- Access to GitLab CI/CD pipeline
- AWS CLI configured with appropriate credentials
- CDK CLI installed and configured

## Overview

The process involves:
1. Creating the AWS account in AWS Organization
2. Setting up IAM role for CDK bootstrap
3. Creating secrets in AWS Secrets Manager
4. Configuring the tenant using the template
5. Registering the tenant in code
6. Deploying via GitLab CI/CD

---

## Step 1: Create AWS Account in AWS Organization

Create a new AWS account in your AWS Organization. This will generate a new AWS Account ID.

**Actions:**
- Go to AWS Organizations console
- Create a new account
- Note the **Account ID** (12 digits) - you'll need it in the next steps

**Example:**
```
Account Name: OSD-Tenant-NewTenant
Account ID: 123456789012
```

---

## Step 2: Add GitLabCrossAccount in the New Account

The CDK bootstrap process requires a role that allows the principal account to assume it.

### 2.1 Create the Role

In the **new AWS account**, create an IAM role named `GitLabCrossAccount`:

**Custom Trust Policy Required:**
You need to create a custom trust policy (not the default one from AWS Console). The trust policy must be:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::111111111111:user/ops-cicd"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

**Note:** The AWS Console will create a trust policy with `arn:aws:iam::ACCOUNT_ID:root` by default, but we need a custom policy pointing to the specific user `ops-cicd`. You'll need to edit the trust policy after creating the role.

**Permissions:**
- Attach the `AdministratorAccess` policy to this role

**How to create (via AWS Console - Easy Way):**

1. **Log in to the new AWS account** (the one you created in Step 1)

2. **Go to IAM Console:**
   - Navigate to: **IAM** → **Roles** → **Create role**

3. **Select trusted entity type:**
   - Choose **Custom trust policy**
   - In the JSON editor, paste the following trust policy:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Principal": {
                   "AWS": "arn:aws:iam::111111111111:user/ops-cicd"
               },
               "Action": "sts:AssumeRole"
           }
       ]
   }
   ```
   - Click **Next**

4. **Add permissions:**
   - In the search box, type: `AdministratorAccess`
   - Check the box next to **AdministratorAccess**
   - Click **Next**

5. **Name the role:**
   - Role name: `GitLabCrossAccount`
   - Description: `Role for CDK bootstrap from principal account user ops-cicd`
   - Click **Create role**

6. **Verify the role:**
   - Go to **IAM** → **Roles** → **GitLabCrossAccount**
   - Click on the role name to open it
   - Check the **Trust relationships** tab:
     - Should show: `arn:aws:iam::111111111111:user/ops-cicd` as principal
   - Check the **Permissions** tab:
     - Should show: `AdministratorAccess` attached

**Important:**
- This role must exist **before** running the bootstrap job in GitLab CI/CD
- The trust policy **must** point to the specific user `arn:aws:iam::111111111111:user/ops-cicd`, not to the account root

**Alternative (via AWS CLI - Recommended):**
Using CLI is easier since you can specify the exact trust policy from the start without needing to edit it later:

```bash
# Option 1: Use the provided trust policy file
# Copy the trust policy file from docs/iam-policies-cdk-bootstrap.json
aws iam create-role \
  --role-name GitLabCrossAccount \
  --assume-role-policy-document file://docs/iam-policies-cdk-bootstrap.json

# Option 2: Create trust policy inline
cat > trust-policy.json <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::111111111111:user/ops-cicd"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

aws iam create-role \
  --role-name GitLabCrossAccount \
  --assume-role-policy-document file://trust-policy.json

# Attach AdministratorAccess
aws iam attach-role-policy \
  --role-name GitLabCrossAccount \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess

# Verify the role
aws iam get-role --role-name GitLabCrossAccount
aws iam get-role-policy --role-name GitLabCrossAccount --policy-name AdministratorAccess
```

---

## Step 3: Configure SSO Federation in Entra (Microsoft)

Before creating the secret, you need to configure SSO federation in Microsoft Entra ID.

### 3.1 Access Entra Portal

1. Go to [https://entra.microsoft.com/](https://entra.microsoft.com/)
2. Navigate to **OSD SSO Master realms Federation**

### 3.2 Create SSO Authentication

1. Create a new authentication/application registration
2. Configure the SSO endpoint URL:
   - Format: `https://sso.{tenant_dns}/realms/master/broker/azuread/endpoint`
   - Example: `https://sso.app-tenant.example.com/realms/master/broker/azuread/endpoint`
   - Replace `{tenant_dns}` with your tenant's DNS zone name

### 3.3 Create Client Secret

1. Go to **Certificates and secrets** in the Entra application
2. Create a new client secret
3. **Note the secret value** - this will be used for `MASTER_REALM_IDP_CLIENT_SECRET` in AWS Secrets Manager

**Important:** Save this secret value securely - you'll need it in Step 4.

---

## Step 4: Create Secret in AWS Secrets Manager

Create a secret in AWS Secrets Manager in the **new AWS account** with the following naming convention:

**Format:** `{tenant}/{env_name}/secret`

**Example:**
- Tenant: `new_tenant`
- Environment: `prd`
- Secret name: `new_tenant/prd/secret`

### 4.1 Get Reference Secret Structure

To see the required secret structure and keys, check the existing reference secret:

**Account:** IT-Ops (111111111111)
**Region:** eu-west-1
**Secret name:** `fr/dev/secret`

**Using AWS Console:**
1. Switch to IT-Ops account (111111111111)
2. Go to AWS Secrets Manager in eu-west-1
3. Open the secret: `fr/dev/secret`
4. View the secret value to see all required keys

**Using AWS CLI:**
```bash
# Get the reference secret (from IT-Ops account)
aws secretsmanager get-secret-value \
  --secret-id "fr/dev/secret" \
  --region eu-west-1 \
  --profile it-ops-profile \
  --query SecretString \
  --output text | jq .
```

### 4.2 Secret Structure (Anonymized Example)

The secret must contain the following keys. Here's the structure with anonymized values:

```json
{
  "OSD_REALM_USERS_OSD_ADMIN_SECRET_DATA_SALT": "YOUR_SALT_VALUE_HERE",
  "OSD_REALM_USERS_OSD_ADMIN_SECRET_DATA_VAULT": "YOUR_VAULT_VALUE_HERE",
  "OSD_REALM_SMTP_SERVER_USER": "YOUR_SMTP_USER_HERE",
  "OSD_REALM_SMTP_SERVER_PASSWORD": "YOUR_SMTP_PASSWORD_HERE",
  "OSD_REALM_OSD_CLIENT_CLIENT_SECRET": "YOUR_CLIENT_SECRET_HERE",
  "MASTER_REALM_IDP_CLIENT_SECRET": "YOUR_ENTRA_CLIENT_SECRET_HERE",
  "MASTER_REALM_SMTP_SERVER_USER": "YOUR_MASTER_SMTP_USER_HERE",
  "MASTER_REALM_SMTP_SERVER_PASSWORD": "YOUR_MASTER_SMTP_PASSWORD_HERE",
  "KC_BOOTSTRAP_ADMIN_PASSWORD": "YOUR_KEYCLOAK_ADMIN_PASSWORD_HERE"
}
```

**Important notes:**
- `MASTER_REALM_IDP_CLIENT_SECRET`: Use the client secret value from Step 3.3 (Entra client secret)
- All other values should be obtained from the reference secret (`fr/dev/secret`) or generated as appropriate for your tenant
- Replace all `YOUR_*_HERE` placeholders with actual values

### 4.3 Create the Secret

**Using AWS Console:**
1. Switch to the **new AWS account**
2. Go to AWS Secrets Manager
3. Click "Store a new secret"
4. Choose "Other type of secret"
5. Create a JSON secret with the same structure as the reference secret (`fr/dev/secret`)
6. **Important:** Use the `MASTER_REALM_IDP_CLIENT_SECRET` value from Step 3.3 (Entra client secret)
7. Secret name: `{tenant}/{env_name}/secret` (e.g., `new_tenant/prd/secret`)
8. Click "Store"

**Using AWS CLI:**
```bash
# Switch to the new account
aws configure set profile.new-tenant ...

# Create the secret (use the reference secret structure)
aws secretsmanager create-secret \
  --name "new_tenant/prd/secret" \
  --description "ECS secrets for new_tenant prd environment" \
  --secret-string file://secret-values.json \
  --region eu-west-1
```

**Note:** The secret must contain all the same keys as shown in section 4.2, with values appropriate for your tenant. The `MASTER_REALM_IDP_CLIENT_SECRET` should be the value from the Entra client secret created in Step 3.3.

### 4.4 Get the Secret ARN

After creating the secret, note the **complete ARN**. It will look like:

```
arn:aws:secretsmanager:eu-west-1:123456789012:secret:new_tenant/prd/secret-XXXXX
```

The ARN format is: `arn:aws:secretsmanager:{region}:{account}:secret:{tenant}/{env_name}/secret-{suffix}`

**You'll need this ARN in the next step.**

---

## Step 5: Configure the Tenant Using Template

### 5.1 Copy the Template

```bash
# Create the tenant directory
mkdir -p config/new_tenant

# Copy the template
cp config/template/template_tenant_prd.yaml config/new_tenant/prd.yaml
```

### 5.2 Replace Placeholders

Edit `config/new_tenant/prd.yaml` and replace all placeholders:

| Placeholder | Replace With | Example |
|------------|--------------|---------|
| `{tenant_dns}` | DNS zone name | `app-newtenant.example.com` |
| `{account}` | AWS Account ID (from Step 1) | `123456789012` |
| `{region}` | AWS region | `eu-west-1` or `eu-central-1` |
| `{tenant}` | Tenant name (snake_case) | `new_tenant` |
| `{env_name}` | Environment name | `prd` |

### 5.3 Update Secret ARN

In the `secrets` section, replace the placeholder ARN with the actual ARN from Step 4.3:

```yaml
secrets:
  secret_ecs_complete_arn: "arn:aws:secretsmanager:eu-west-1:123456789012:secret:new_tenant/prd/secret-XXXXX"
```

### 5.4 Configure Domain

Choose the appropriate domain configuration based on your DNS setup (see main README for details):

**Option A: Cross-account delegation (for parent domain)**
```yaml
domain:
  zone_name: "${dns_zone_name}"
  parent_hosted_zone_id: "Z0000000000000"
  delegation_role_arn: "arn:aws:iam::777777777777:role/Route53ZoneDelegationRole-OrgRoot"
  records:
    front_domain_name: "${dns_zone_name}"
    api_domain_name: "api.${dns_zone_name}"
    sso_domain_name: "sso.${dns_zone_name}"
```

**Option B: Existing hosted zone**
```yaml
domain:
  zone_name: "${dns_zone_name}"
  hosted_zone_id: "Z1234567890ABC"
  records:
    front_domain_name: "${dns_zone_name}"
    api_domain_name: "api.${dns_zone_name}"
    sso_domain_name: "sso.${dns_zone_name}"
```

**Important for cross-account delegation:** If you chose Option A (cross-account delegation), you must add the new account ID to the trust policy of the `Route53ZoneDelegationRole-OrgRoot` role in the parent account (777777777777). See Step 5.5 below.

### 5.5 Update Route53 Delegation Role Trust Policy (for cross-account delegation only)

**Important:** This step is **only required** if you're using cross-account delegation (Option A in Step 5.4).

Before deploying the infrastructure, you need to add the new AWS account ID to the trust policy of the `Route53ZoneDelegationRole-OrgRoot` role in the parent AWS account (777777777777). This allows the new account to assume this role for Route53 zone delegation.

**How to do it via AWS Console:**

1. **Log in to parent AWS account 777777777777**

2. **Go to IAM Console:**
   - Navigate to: **IAM** → **Roles**
   - Search for: `Route53ZoneDelegationRole-OrgRoot`
   - Click on the role name

3. **Edit Trust Policy:**
   - Click on the **Trust relationships** tab
   - Click **Edit trust policy**
   - In the JSON editor, add the new account ID to the `Principal` section
   - The trust policy should include both the existing account IDs and the new one:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Principal": {
                   "AWS": [
                       "arn:aws:iam::EXISTING_ACCOUNT_1:root",
                       "arn:aws:iam::EXISTING_ACCOUNT_2:root",
                       "arn:aws:iam::NEW_ACCOUNT_ID:root"
                   ]
               },
               "Action": "sts:AssumeRole",
               "Condition": {}
           }
       ]
   }
   ```
   - Replace `NEW_ACCOUNT_ID` with the account ID from Step 1 (e.g., `123456789012`)
   - Keep all existing account IDs in the list (do not remove them)
   - Click **Update policy**

4. **Verify:**
   - The trust policy should now include your new account ID
   - The role can now be assumed by the new account for Route53 zone delegation

**Alternative (via AWS CLI):**

```bash
# Get the current trust policy
aws iam get-role \
  --role-name Route53ZoneDelegationRole-OrgRoot \
  --profile principal-account \
  --query 'Role.AssumeRolePolicyDocument' \
  --output json > current-trust-policy.json

# Edit the JSON file to add the new account ID to the Principal.AWS array
# Then update the trust policy
aws iam update-assume-role-policy \
  --role-name Route53ZoneDelegationRole-OrgRoot \
  --policy-document file://updated-trust-policy.json \
  --profile principal-account
```

**Important notes:**
- This must be done **before** deploying the infrastructure (Step 9), otherwise the cross-account zone delegation will fail during deployment
- Only add the account ID if the tenant uses cross-account delegation
- Do not remove existing account IDs from the trust policy

### 5.6 Review Other Settings

Review and adjust other configuration sections as needed:
- VPC CIDR (ensure no conflicts)
- Database settings (Aurora, DocumentDB, Redis)
- ECS service configurations
- Frontend settings

---

## Step 6: Register Tenant in app.py

Add the new tenant to the `stages_config` list in `app.py`:

```python
stages = StageFactory.create_stages(
    app,
    stages_config=[
        ("fr", "dev"),
        ("fr", "stg"),
        ("dke", "prd"),
        ("che", "prd"),
        ("new_tenant", "prd"),  # ← Add your new tenant here
    ],
)
```

**File location:** `app.py` (root directory)

---

## Step 7: Verify Configuration

Verify that the new tenant is discovered correctly:

```bash
cdk list
```

You should see stacks for your new tenant, for example:
```
NewTenantPrdStage/NetworkStack
NewTenantPrdStage/SecurityStack
NewTenantPrdStage/DatabaseStack
NewTenantPrdStage/DomainStack
NewTenantPrdStage/StorageStack
NewTenantPrdStage/ApplicationStack
NewTenantPrdStage/FrontEndStack
NewTenantPrdStage/CloudFrontCertificateStack
```

---

## Step 8: Commit and Push

```bash
# Stage your changes
git add config/new_tenant/prd.yaml app.py

# Commit
git commit -m "feat: add new_tenant prd environment"

# Push to trigger CI/CD pipeline
git push origin main
```

**Important:** The CI/CD pipeline will automatically:
1. Validate the code
2. Discover the new stacks
3. Generate deployment jobs

---

## Step 9: Deploy via GitLab CI/CD

After pushing, go to GitLab CI/CD pipeline and execute the following jobs **in order**:

### 9.1 Bootstrap Account (Manual)

**Job:** `bootstrap-discovered-accounts` (stage: `bootstrap`)

**What it does:**
- Bootstraps the principal account directly
- Assumes `GitLabCrossAccount` in the new account
- Bootstraps the new account with CDK bootstrap

**How to run:**
1. Go to GitLab CI/CD → Pipelines
2. Find the pipeline for your commit
3. Click on the `bootstrap` stage
4. Click the play button (▶️) on `bootstrap-discovered-accounts`
5. Wait for completion

**Prerequisites:**
- `GitLabCrossAccount` must exist in the new account (Step 2)

### 9.2 Deploy Shared Infrastructure (Manual)

**Job:** `deploy-shared-stage` (stage: `deploy-shared`)

**What it does:**
- Deploys shared infrastructure (S3 buckets, ECR repositories) across regions
- Creates ECR repositories in all target regions
- Creates frontend source buckets with replication

**How to run:**
1. In the same pipeline, go to the `deploy-shared` stage
2. Click the play button (▶️) on `deploy-shared-stage`
3. Wait for completion

**Note:** This is typically a one-time operation, but run it if it's the first tenant in a new region.

### 9.3 Trigger Production Deployment (Manual)

**Job:** `trigger-prd` (stage: `trigger`)

**What it does:**
- Launches the production child pipeline
- Generates diff and deploy jobs for all prd stages

**How to run:**
1. In the same pipeline, go to the `trigger` stage
2. Click the play button (▶️) on `trigger-prd`
3. This will create a new child pipeline for production

### 9.4 Review Diff (Automatic)

**Job:** `diff:prd:NewTenantPrdStage` (in the child pipeline)

**What it does:**
- Runs `cdk diff` for your new tenant
- Shows all infrastructure changes that will be created
- Detects destructive changes (if any)

**Review the output:**
- Check that all resources are being created (not destroyed)
- Verify account IDs and regions are correct
- Note any warnings about destructive changes

### 9.5 Deploy Infrastructure (Manual)

**Job:** `deploy:prd:NewTenantPrdStage` (in the child pipeline)

**What it does:**
- Deploys all stacks for your new tenant
- Creates VPC, security groups, databases, ECS, ALB, CloudFront, etc.

**How to run:**
1. In the child pipeline (triggered by `trigger-prd`)
2. Go to the `deploy` stage
3. Click the play button (▶️) on `deploy:prd:NewTenantPrdStage`
4. Monitor the deployment progress

**Expected duration:** ~30 minutes (depending on database creation time)

**What gets created:**
- Network Stack (VPC, subnets, NAT gateways)
- Security Stack (security groups)
- Database Stack (Aurora MySQL, DocumentDB, Redis)
- Storage Stack (S3 buckets)
- Domain Stack (Route53 hosted zone, DNS records, ACM certificates)
- CloudFront Certificate Stack (certificate in us-east-1)
- Application Stack (ECS cluster, services, ALB)
- Frontend Stack (CloudFront distribution, S3)

---

## Step 10: Create DNS Delegation (if cross-account domain)

**Important:** This step is **only required** if you're using cross-account delegation.

After the deployment completes, the Domain Stack will have created a Route53 cross delegation in the parent hosted zone for the parent AWS account (777777777777). You now need to retrieve the name servers (NS records) from AWS and create the corresponding delegation on your internal DNS server.

### 10.1 Get Name Servers from AWS Route53

After the deployment is complete, retrieve the name servers from the Route53 hosted zone that was created:

**Using AWS Console:**
1. Go to **Route53** → **Hosted zones** in the new AWS account
2. Find the hosted zone for your tenant domain (e.g., `app-newtenant.example.com`)
3. Note the **4 name server values** listed in the NS record

**Using AWS CLI:**
```bash
# Get the hosted zone ID first
aws route53 list-hosted-zones-by-name \
  --dns-name app-newtenant.example.com \
  --region eu-west-1 \
  --profile new-tenant-profile

# Get the name servers
aws route53 get-hosted-zone \
  --id <HOSTED_ZONE_ID> \
  --region eu-west-1 \
  --profile new-tenant-profile \
  --query 'DelegationSet.NameServers' \
  --output text
```

**Example output:**
```
ns-123.awsdns-12.com
ns-456.awsdns-45.net
ns-789.awsdns-78.org
ns-012.awsdns-01.co.uk
```

### 10.2 Create DNS Delegation on Internal Machine

1. Connect to your internal DNS management server
2. Create a DNS delegation for your tenant domain using the name servers retrieved from AWS Route53

**Example:**
- For tenant DNS: `app-newtenant.example.com`
- Create delegation on your internal DNS management server
- Use the 4 name servers from AWS Route53 (from Step 10.1)

**Note:** The exact procedure for creating the delegation depends on your DNS management system on the internal machine. Contact your DNS administrator if you need assistance with the specific commands or interface.

---

## Step 11: Verify Deployment

After deployment completes, verify the infrastructure:

### 11.1 Check Stacks

```bash
# List all stacks in the new account
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --region eu-west-1 \
  --profile new-tenant-profile
```

### 11.2 Verify Resources

- **VPC:** Check that VPC is created with correct CIDR
- **Databases:** Verify Aurora, DocumentDB, and Redis clusters are running
- **ECS:** Check that ECS cluster and services are running
- **ALB:** Verify Application Load Balancer is created
- **Route53:** Check DNS records are created
- **CloudFront:** Verify distribution is created

### 11.3 Test DNS

```bash
# Test DNS resolution
dig app-newtenant.example.com
dig api.app-newtenant.example.com
dig sso.app-newtenant.example.com
```

### 11.4 Test Application

Once DNS propagates (can take a few minutes):
- Access frontend: `https://app-newtenant.example.com`
- Access API: `https://api.app-newtenant.example.com`
- Access SSO: `https://sso.app-newtenant.example.com`

---

## Troubleshooting

### Bootstrap Fails

**Error:** `GitLabCrossAccount` not found

**Solution:**
- Verify the role exists in the new account
- Check the trust policy allows `arn:aws:iam::111111111111:user/ops-cicd`
- Ensure `AdministratorAccess` is attached

### Secret Not Found

**Error:** Secret ARN not found during deployment

**Solution:**
- Verify the secret exists in the correct region
- Check the ARN format matches: `arn:aws:secretsmanager:{region}:{account}:secret:{tenant}/{env_name}/secret-{suffix}`
- Ensure the secret name is exactly `{tenant}/{env_name}/secret`

### Domain Configuration Error

**Error:** Domain validation fails or cross-account delegation fails

**Solution:**
- Verify `hosted_zone_id` OR `parent_hosted_zone_id` is provided (not both)
- For cross-account delegation, ensure `delegation_role_arn` is correct
- Check that the parent hosted zone exists and is accessible
- **For cross-account delegation:** Verify that the new account ID has been added to the trust policy of `Route53ZoneDelegationRole-OrgRoot` in the parent account (777777777777) (Step 5.5)

### Deployment Fails

**Error:** Stack deployment fails

**Solution:**
- Check CloudFormation events in AWS Console
- Review CloudWatch logs for ECS services
- Verify all prerequisites are met (secrets, roles, etc.)
- Check for resource limits (VPCs, subnets, etc.)

---

## Next Steps

After successful deployment:

1. **Configure Keycloak:**
   - Access Keycloak admin console
   - Configure realms and clients
   - Set up user authentication

2. **Deploy Application Code:**
   - Build and push Docker images to ECR
   - Update ECS service task definitions with new images

3. **Configure Frontend:**
   - Upload frontend build to S3 bucket
   - Configure CloudFront distribution

4. **Documentation:**
   - Document tenant-specific configurations
   - Update runbooks

---

## Summary Checklist

- [ ] AWS account created in AWS Organization
- [ ] `GitLabCrossAccount` created in new account with correct trust policy
- [ ] Secret created in Secrets Manager with format `{tenant}/{env_name}/secret`
- [ ] Secret ARN noted
- [ ] Template copied and all placeholders replaced
- [ ] Domain configuration chosen and configured
- [ ] Route53 delegation role trust policy updated with new account ID (if cross-account delegation)
- [ ] Tenant added to `app.py`
- [ ] `cdk list` shows new tenant stacks
- [ ] Changes committed and pushed
- [ ] Bootstrap job executed successfully
- [ ] Deploy-shared job executed successfully
- [ ] Trigger-prd job executed
- [ ] Diff reviewed and approved
- [ ] Deploy job executed successfully
- [ ] Name servers retrieved from AWS Route53 (if cross-account delegation)
- [ ] DNS delegation created on internal DNS (if cross-account delegation)
- [ ] Infrastructure verified
- [ ] DNS tested
- [ ] Application tested

---

**Need help?** Check the main [README.md](../README.md) for more details on configuration options and architecture.
