# Creating a New Tenant - Quick Guide

Ultra-simplified step-by-step guide to create a new tenant.

## Prerequisites

- AWS Organization access
- GitLab CI/CD access
- AWS CLI configured

---

## Step 1: Create AWS Account

Create new account in AWS Organization → Note the **Account ID** (12 digits)

---

## Step 2: Create GitLabCrossAccount

In the **new AWS account**, create IAM role:

1. **IAM** → **Roles** → **Create role**
2. Select **Custom trust policy**
3. Paste this JSON:
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
4. Attach **AdministratorAccess** policy
5. Name: `GitLabCrossAccount`
6. Create role

---

## Step 3: Configure SSO in Entra (Microsoft)

1. Go to [https://entra.microsoft.com/](https://entra.microsoft.com/)
2. Navigate to **OSD SSO Master realms Federation**
3. Create authentication with SSO endpoint:
   - URL: `https://sso.{tenant_dns}/realms/master/broker/azuread/endpoint`
   - Example: `https://sso.app-tenant.example.com/realms/master/broker/azuread/endpoint`
4. Go to **Certificates and secrets**
5. Create a new client secret
6. **Note the secret value** → This is `MASTER_REALM_IDP_CLIENT_SECRET`

---

## Step 4: Create Secret

**First, get reference secret structure:**
- Account: IT-Ops (111111111111)
- Region: eu-west-1
- Secret: `fr/dev/secret`
- View this secret to see all required keys

**Secret structure (all required keys):**
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

**Note:** `MASTER_REALM_IDP_CLIENT_SECRET` = value from Step 3 (Entra client secret)

**Then create secret in new account:**

1. **AWS Secrets Manager** → **Store a new secret**
2. Choose **Other type of secret**
3. Use the JSON structure above (replace all `YOUR_*_HERE` with actual values)
4. Use `MASTER_REALM_IDP_CLIENT_SECRET` from Step 3
5. Secret name: `{tenant}/{env_name}/secret` (e.g., `new_tenant/prd/secret`)
6. **Store**
7. **Note the ARN** (you'll need it in Step 5)

---

## Step 5: Configure Tenant

```bash
# Copy template
mkdir -p config/new_tenant
cp config/template/template_tenant_prd.yaml config/new_tenant/prd.yaml
```

Edit `config/new_tenant/prd.yaml`:

1. Replace placeholders:
   - `{tenant_dns}` → DNS zone (e.g., `app-newtenant.example.com`)
   - `{account}` → Account ID from Step 1
   - `{region}` → Region (e.g., `eu-west-1`)
   - `{tenant}` → Tenant name (e.g., `new_tenant`)
   - `{env_name}` → Environment (e.g., `prd`)

2. Update secret ARN (from Step 4):
```yaml
secrets:
  secret_ecs_complete_arn: "arn:aws:secretsmanager:eu-west-1:123456789012:secret:new_tenant/prd/secret-XXXXX"
```

3. Configure domain (choose one):

**Option A: Cross-account delegation (.example.com)**
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

**Important for cross-account delegation domains:** If you chose Option A (cross-account delegation), you must add the new account ID to the trust policy of the `Route53ZoneDelegationRole-OrgRoot` role in the parent account (777777777777). See Step 5.5 below.

---

## Step 5.5: Update Route53 Delegation Role Trust Policy (for cross-account delegation only)

**Important:** This step is **only required** if you're using cross-account delegation (Option A in Step 5).

You need to add the new AWS account ID to the trust policy of the `Route53ZoneDelegationRole-OrgRoot` role in the parent AWS account (777777777777).

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
   - Replace `NEW_ACCOUNT_ID` with the account ID from Step 1
   - Keep all existing account IDs in the list
   - Click **Update policy**

4. **Verify:**
   - The trust policy should now include your new account ID
   - The role can now be assumed by the new account for Route53 zone delegation

**Note:** This must be done **before** deploying the infrastructure, otherwise the cross-account zone delegation will fail.

---

## Step 6: Register in app.py

Add to `app.py`:
```python
stages = StageFactory.create_stages(
    app,
    stages_config=[
        # ... existing tenants ...
        ("new_tenant", "prd"),  # ← Add here
    ],
)
```

---

## Step 7: Verify & Commit

```bash
# Verify stacks are discovered
cdk list

# Commit and push
git add config/new_tenant/prd.yaml app.py
git commit -m "feat: add new_tenant prd environment"
git push
```

---

## Step 8: Deploy via GitLab CI/CD

In GitLab pipeline, run jobs **in order**:

1. **bootstrap-discovered-accounts** (manual) → Bootstrap account
2. **deploy-shared-stage** (manual) → Deploy shared infrastructure
3. **trigger-prd** (manual) → Launch production pipeline
4. **diff:prd:NewTenantPrdStage** (auto) → Review changes
5. **deploy:prd:NewTenantPrdStage** (manual) → Deploy infrastructure

**Wait ~30 minutes** for deployment to complete.

---

## Step 9: Create DNS Delegation (if cross-account domain)

**Important:** This step is **only required** if using cross-account delegation.

After deployment, the Route53 hosted zone is created in AWS. You need to:

1. **Get name servers from AWS Route53:**
   - Go to **Route53** → **Hosted zones** in the parent AWS account (777777777777).
   - Find your record name for your tenant domain (e.g., `app-newtenant.example.com`)
   - Note the **4 name server values** from the NS record

2. **Create delegation on internal DNS:**
   - Connect to your DNS management server
   - Create DNS delegation for `app-newtenant.example.com` using the AWS name servers

---

## Step 10: Verify

- Check CloudFormation stacks in AWS Console
- Test DNS: `dig app-newtenant.example.com`
- Access: `https://app-newtenant.example.com`

---

## Checklist

- [ ] AWS account created
- [ ] GitLabCrossAccount created with custom trust policy
- [ ] SSO configured in Entra with client secret created
- [ ] Secret created: `{tenant}/{env_name}/secret` (using reference from `fr/dev/secret`)
- [ ] Template configured with all placeholders replaced
- [ ] Route53 delegation role trust policy updated with new account ID (if cross-account delegation)
- [ ] Tenant added to `app.py`
- [ ] `cdk list` shows new stacks
- [ ] Committed and pushed
- [ ] Bootstrap job completed
- [ ] Deploy-shared job completed
- [ ] Trigger-prd job completed
- [ ] Diff reviewed
- [ ] Deploy job completed
- [ ] Name servers retrieved from AWS Route53 (if cross-account delegation)
- [ ] DNS delegation created on internal DNS (if cross-account delegation)
- [ ] Infrastructure verified

---

**Need more details?** See [CREATING_NEW_TENANT.md](CREATING_NEW_TENANT.md) for the complete guide.
