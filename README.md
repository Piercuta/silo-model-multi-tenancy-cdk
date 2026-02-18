# OSD CDK Infrastructure

> Multi-tenant AWS infrastructure as code using AWS CDK and GitLab CI/CD

## Overview

Multi-tenant AWS infrastructure with automated deployment through GitLab CI/CD. Supports multiple tenants across different AWS accounts with isolated network, security, and database configurations.

### Key Features

- 🎯 **Fully Dynamic Pipeline** - Add tenant in code → CI/CD jobs auto-generated from `cdk list --long`
- 🏢 **Multi-Tenant** - Separate infrastructure per tenant with customizable configurations
- 🔄 **Smart Deployments** - Automatic diff, destructive change detection, environment-based triggers
- 🔐 **Cross-Account** - Bootstrap and deploy across multiple AWS accounts with AssumeRole
- 🧩 **Modular Stacks** - Reusable network, security, database, domain, application, and frontend components
- 🎯 **Type-Safe** - Pydantic-based configuration with validation
- 🧪 **Quality Checks** - Pre-commit hooks, linting, formatting, and tests
- 🌐 **Complete Application Stack** - ECS Fargate, ALB, CloudFront, Route53, ACM certificates
- 🗄️ **Multi-Database Support** - Aurora MySQL, DocumentDB, Redis with automatic scaling
- 🔒 **DNS Management** - Flexible Route53 configuration (import, same-account, or cross-account delegation)

### Architecture

```
Principal AWS Account (111111111111)
├── Main Tenant (IT-Ops) - dev, stg
│
Target AWS Accounts
├── Tenant2 (444444444444) - prd (eu-central-1)
└── Tenant1 (333333333333) - prd (eu-central-1)
```

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **Node.js 22+** (for AWS CDK CLI)
- **AWS CLI** configured
- **Docker** (for CI/CD)

### Installation

```bash
# Clone and setup
git clone <repository-url>
cd osd-cdk

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
npm install -g aws-cdk@latest
```

### First Deployment

The CI/CD pipeline handles bootstrapping automatically. Just push to `main` or `develop`:

```bash
git push origin main
```

The pipeline will:
1. Discover stacks
2. Generate dynamic jobs
3. Trigger deployment for dev (automatic) or stg/prd (manual)

---

## Project Structure

```
fr-osd-cdk/
├── app.py                      # CDK app entry point
├── .gitlab-ci.yml             # Main CI config (39 lines)
├── Makefile                    # Development commands
├── Dockerfile                  # CI/CD runner image
│
├── config/                     # Tenant configurations
│   ├── loader.py              # Config loader with validation
│   ├── base_config.py         # Pydantic models
│   ├── template/              # Configuration templates
│   │   └── template_tenant_prd.yaml
│   ├── fr/                   # FR tenant configs
│   │   ├── dev.yaml
│   │   └── stg.yaml
│   ├── de/                   # DE tenant configs
│   ├── ch/                   # CH tenant configs
│   └── [tenant_name]/         # Other tenant configs
│
├── stacks/                     # CDK stack definitions
│   ├── base/                  # Reusable base stacks
│   │   ├── network_stack.py   # VPC, subnets, NAT
│   │   ├── security_stack.py  # Security groups
│   │   ├── database_stack.py  # Aurora, DocumentDB, Redis
│   │   ├── domain_stack.py    # Route53, DNS, ACM certificates
│   │   ├── storage_stack.py   # S3 buckets
│   │   ├── application_stack.py  # ECS, ALB, services
│   │   ├── front_end_stack.py    # CloudFront, S3
│   │   └── cloudfront_certificate_stack.py  # CloudFront certs
│   ├── shared/                # Shared infrastructure stacks
│   │   ├── ecr_repository_stack.py
│   │   ├── frontend_source_main_bucket_stack.py
│   │   └── frontend_source_bucket_replicas_stack.py
│   └── extensions/            # Custom tenant-specific stacks
│
├── stages/                     # CDK stage orchestration
│   ├── factory.py             # Stage factory
│   ├── base_stage.py          # Base stage
│   └── tenant_c_stage.py      # Custom stage
│
├── ci/
│   ├── gitlab/stages/         # GitLab CI stage definitions
│   │   ├── 01-validate.yml    # Code quality
│   │   ├── 02-discover.yml    # Stack discovery
│   │   ├── 03-bootstrap.yml   # Account bootstrap
│   │   ├── 04-deploy-shared.yml  # Deploy shared infrastructure (S3, ECR)
│   │   └── 05-triggers.yml    # Deployment triggers
│   └── scripts/
│       ├── discover_stages.py      # Dynamic job generation
│       └── bootstrap_accounts.py   # Cross-account bootstrap
│
└── tests/                      # Unit tests
```

---

## Development

### Adding a New Tenant

> **📖 Quick guide:** [docs/CREATING_NEW_TENANT_SIMPLE.md](docs/CREATING_NEW_TENANT_SIMPLE.md)
> **📖 Complete guide:** [docs/CREATING_NEW_TENANT.md](docs/CREATING_NEW_TENANT.md)

**Quick summary:**

1. **Create AWS account** in AWS Organization
2. **Add `GitLabCrossAccount`** in the new account
3. **Create secret** in Secrets Manager: `{tenant}/{env_name}/secret`
4. **Copy and configure** the template:
   ```bash
   mkdir -p config/new_tenant
   cp config/template/template_tenant_prd.yaml config/new_tenant/prd.yaml
   # Edit and replace all placeholders
   ```
5. **Register in `app.py`**:
   ```python
   stages = StageFactory.create_stages(
       app,
       stages_config=[
           # ... existing tenants ...
           ("new_tenant", "prd"),
       ],
   )
   ```
6. **Verify and commit**:
   ```bash
   cdk list  # Verify stacks are discovered
   git commit -m "feat: add new_tenant prd environment"
   git push
   ```
7. **Deploy via GitLab CI/CD**:
   - Run `bootstrap-discovered-accounts` (manual)
   - Run `deploy-shared-stage` (manual)
   - Run `trigger-prd` (manual)
   - Review `diff:prd:NewTenantPrdStage`
   - Run `deploy:prd:NewTenantPrdStage` (manual)

**See [docs/CREATING_NEW_TENANT.md](docs/CREATING_NEW_TENANT.md) for detailed instructions, troubleshooting, and verification steps.**

### Configuration System

- **Directory name** = tenant name (snake_case)
- **File name** = environment name (kebab-case)
- **Overrides** available via `env_name_override` and `tenant_name_override`
- **Validation** with Pydantic models
- **Flexible** infrastructure parameters (AZs, NAT gateways, CIDR, etc.)
- **Template** available at `config/template/template_tenant_prd.yaml` for quick start

### Configuration Template

A comprehensive configuration template is available at `config/template/template_tenant_prd.yaml`.

**What's included:**
- Complete domain configuration examples (all 3 DNS scenarios)
- ECS services configuration (osd-api, keycloak, xslt, Fonto services)
- Database configuration (Aurora MySQL, DocumentDB, Redis)
- Network, security, and storage settings
- ALB and target groups configuration
- Detailed comments explaining each section

**Usage:**
```bash
# Copy template for new tenant
cp config/template/template_tenant_prd.yaml config/new_tenant/prd.yaml

# Edit and customize as needed
# Replace all {placeholders} with actual values
```

The template serves as a complete starting point with all required and optional configuration sections documented.

### Domain Configuration

The infrastructure supports three DNS configuration scenarios for Route53 hosted zones:

#### Scenario 1: Use Existing Hosted Zone

When you have already created a Route53 hosted zone manually:

```yaml
domain:
  zone_name: "example.com"
  hosted_zone_id: "Z1234567890ABC"  # Your existing hosted zone ID
  records:
    front_domain_name: "example.com"
    api_domain_name: "api.example.com"
    sso_domain_name: "sso.example.com"
```

**Use case:** You've manually created the hosted zone in Route53 and want to import it.

#### Scenario 2: Same-Account Delegation

Create a new hosted zone and delegate it under a parent zone in the same AWS account:

```yaml
domain:
  zone_name: "subdomain.example.com"
  parent_hosted_zone_id: "Z2222222222222"  # Parent zone in same account
  # delegation_role_arn: NOT REQUIRED (same account)
  records:
    front_domain_name: "subdomain.example.com"
    api_domain_name: "api.subdomain.example.com"
    sso_domain_name: "sso.subdomain.example.com"
```

**Use case:** Creating a subdomain under a parent domain managed in the same AWS account.

**Example:** `fr/dev.yaml` uses this scenario.

#### Scenario 3: Cross-Account Delegation

Create a new hosted zone and delegate it under a parent zone in a different AWS account (e.g., .example.com):

```yaml
domain:
  zone_name: "app-tenant.example.com"
  parent_hosted_zone_id: "Z0000000000000"  # Parent zone in different account
  delegation_role_arn: "arn:aws:iam::777777777777:role/Route53ZoneDelegationRole-OrgRoot"
  records:
    front_domain_name: "app-tenant.example.com"
    api_domain_name: "api.app-tenant.example.com"
    sso_domain_name: "sso.app-tenant.example.com"
```

**Use case:** Creating a subdomain under a parent domain (like .example.com) managed in a different AWS account.

**Requirements:**
- `delegation_role_arn` must point to a role in the parent account
- The role must allow the current account to assume it and modify the parent hosted zone

**Examples:** `de/prd.yaml` and `ch/prd.yaml` use this scenario.

**Important Notes:**
- `hosted_zone_id` and `parent_hosted_zone_id` are **mutually exclusive**
- Exactly one must be provided
- For cross-account delegation, `delegation_role_arn` is required
- The CDK automatically creates DNS delegation records and ACM certificates

### Creating Custom Stacks

For tenant-specific infrastructure:

```python
# stages/custom_tenant_stage.py
from stages.base_stage import BaseStage
from stacks.custom_stack import CustomStack

class CustomTenantStage(BaseStage):
    def __init__(self, scope, id, config, **kwargs):
        super().__init__(scope, id, config, **kwargs)

        # Add custom stack after base stacks
        CustomStack(
            self, "CustomStack",
            vpc=self.network_stack.vpc,
            env=self.env_kwargs
        )
```

### Local Development

```bash
# Run tests
make test

# Format code
make format

# Run linter
make lint

# Synthesize stacks
make synth

# List stacks
make list

# Show differences
make diff

# Run all pre-commit hooks
make pre-commit
```

---

## CI/CD Pipeline

### Pipeline Flow

```
Validate → Discover → Bootstrap (manual) → Deploy-Shared (manual) → Trigger → Diff + Deploy
                                                                    ├─ Dev (auto)
                                                                    ├─ Stg (manual)
                                                                    └─ Prd (manual)
```

### How It Works

**The pipeline automatically discovers your infrastructure from `app.py`:**

```
app.py (defines tenants)
    ↓
cdk list --long (discovers all stages/stacks/accounts)
    ↓
discover_stages.py (generates dynamic jobs)
    ↓
gitlab-ci-dynamic-jobs-{env}.yml (one file per environment)
    ↓
diff + deploy jobs (automatically created for each stage)
```

**Pipeline stages:**

1. **Validate** - Code quality checks (lint, format, test)
2. **Discover** - Run `cdk list --long`, parse output, generate dynamic jobs
3. **Bootstrap** - (Manual, one-time) Bootstrap discovered AWS accounts
4. **Deploy-Shared** - (Manual, one-time) Deploy shared infrastructure (S3 buckets, ECR repositories) across regions
5. **Trigger** - Launch child pipelines per environment (dev/stg/prd)
6. **Diff + Deploy** - For each discovered stage, run diff then deploy

### 🎯 Dynamic Job Generation - The Core Concept

**Everything starts with `cdk list --long`** - This is the foundation of our dynamic pipeline!

#### Step 1: CDK discovers all stages and stacks

```bash
$ cdk list --long
```

**Output example:**
```yaml
- id: FrDevStage/NetworkStack
  name: FrDevStage-NetworkStack
  environment:
    account: "111111111111"
    region: eu-west-1

- id: FrDevStage/SecurityStack
  name: FrDevStage-SecurityStack
  environment:
    account: "111111111111"
    region: eu-west-1

- id: FrDevStage/DatabaseStack
  name: FrDevStage-DatabaseStack
  environment:
    account: "111111111111"
    region: eu-west-1

- id: FrDevStage/DomainStack
  name: FrDevStage-DomainStack
  environment:
    account: "111111111111"
    region: eu-west-1

- id: FrDevStage/ApplicationStack
  name: FrDevStage-ApplicationStack
  environment:
    account: "111111111111"
    region: eu-west-1

# ... and more stacks (StorageStack, FrontEndStack, CloudFrontCertificateStack)
```

#### Step 2: Discovery script analyzes the output

The `ci/scripts/discover_stages.py` script:
1. Parses `cdk list --long` YAML output
2. **Groups stacks by Stage** (FrDevStage, TenantBPrdStage, etc.)
   - Example: `FrDevStage/NetworkStack` + `FrDevStage/SecurityStack` → grouped as `FrDevStage`
3. Extracts AWS account IDs from each stack's environment
4. Identifies environment types (dev, stg, prd) from stage names

#### Step 3: Generates dynamic CI/CD jobs

**For each Stage → Create 2 jobs (diff + deploy)**

A **Stage** contains multiple **Stacks**. We generate 2 jobs per Stage (not per Stack):

```
FrDevStage                     →  diff:dev:FrDevStage  (diffs ALL stacks)
  ├─ NetworkStack               →  deploy:dev:FrDevStage (deploys ALL stacks)
  ├─ SecurityStack
  ├─ DatabaseStack
  ├─ StorageStack
  ├─ DomainStack
  ├─ CloudFrontCertificateStack
  ├─ ApplicationStack
  └─ FrontEndStack

DePrdStage                     →  diff:prd:DePrdStage  (diffs ALL stacks)
  ├─ NetworkStack               →  deploy:prd:DePrdStage (deploys ALL stacks)
  ├─ SecurityStack
  ├─ DatabaseStack
  ├─ StorageStack
  ├─ DomainStack
  ├─ CloudFrontCertificateStack
  ├─ ApplicationStack
  └─ FrontEndStack

ChPrdStage                     →  diff:prd:ChPrdStage  (diffs ALL stacks)
  ├─ NetworkStack               →  deploy:prd:ChPrdStage (deploys ALL stacks)
  ├─ SecurityStack
  ├─ DatabaseStack
  ├─ StorageStack
  ├─ DomainStack
  ├─ CloudFrontCertificateStack
  ├─ ApplicationStack
  └─ FrontEndStack
```

**Key point**: Each Stage = 1 diff job + 1 deploy job (that handles all stacks in that stage).

**Example of generated jobs:**
```yaml
# diff:dev:FrDevStage job runs:
cdk diff FrDevStage/*   # Diffs all 8 stacks together

# deploy:dev:FrDevStage job runs:
cdk deploy FrDevStage/* # Deploys all 8 stacks together
```

**Result: 3 separate job files per environment**
- `gitlab-ci-dynamic-jobs-dev.yml` - All dev stages
- `gitlab-ci-dynamic-jobs-stg.yml` - All stg stages
- `gitlab-ci-dynamic-jobs-prd.yml` - All prd stages

#### Step 4: Also generates bootstrap configuration

Extracts unique AWS accounts:
```json
{
  "principal_account": "111111111111",
  "region": "eu-west-1",
  "accounts": [
    {"account_id": "111111111111", "is_principal": true},
    {"account_id": "888888888888", "is_principal": false},
    {"account_id": "333333333333", "is_principal": false}
  ]
}
```

**🔑 Key Benefit:** Add a new tenant in `app.py` → All jobs are auto-generated! No manual CI/CD configuration needed.

### Bootstrap Process

**One-time setup for cross-account deployments:**

1. **Create `GitLabCrossAccount` in target accounts**

Trust policy allowing principal account's GitLab runner user:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::111111111111:user/ops-cicd"
    },
    "Action": "sts:AssumeRole"
  }]
}
```

Attach `AdministratorAccess` policy to `GitLabCrossAccount`.

2. **Run bootstrap job in GitLab**

Manually trigger `bootstrap-discovered-accounts` job. The script will:
- Bootstrap principal account directly
- AssumeRole into target accounts via `GitLabCrossAccount`
- Bootstrap with trust relationships

### Deployment Workflow

**Dev** (automatic on `main`/`develop`):
```
git push → validate → discover → trigger-dev → diff → deploy
```

**Stg/Prd** (manual):
```
git push → validate → discover → [manual trigger] → diff → deploy
```

### Diff Features

- Runs `cdk diff` for each tenant
- Detects destructive changes (replacement, destroy, delete, terminate)
- Shows warning icon if destructive operations detected
- Allows deployment to continue (`allow_failure: true`)

---

## Configuration

### Tenant Configuration Structure

```yaml
# config/tenant_name/environment.yaml

# Variables section (optional, for reuse)
variables:
  dns_zone_name: "app-tenant.example.com"

# Domain configuration (see Domain Configuration section)
domain:
  zone_name: "${dns_zone_name}"
  parent_hosted_zone_id: "Z0000000000000"
  delegation_role_arn: "arn:aws:iam::777777777777:role/Route53ZoneDelegationRole-OrgRoot"
  records:
    front_domain_name: "${dns_zone_name}"
    api_domain_name: "api.${dns_zone_name}"
    sso_domain_name: "sso.${dns_zone_name}"

# AWS account and region
aws:
  account: "123456789012"
  region: eu-west-1

# Secrets (must be created before deployment)
secrets:
  secret_ecs_complete_arn: "arn:aws:secretsmanager:eu-west-1:123456789012:secret:tenant/env/secret-*****"

# Network configuration
vpc:
  cidr: "10.10.0.0/16"
  reserved_azs: 3        # 1-3 availability zones
  nat_gateways: 1        # 0-3 NAT gateways

# Database configuration
redis:
  cache_engine_version: "7.1"

aurora_cluster:
  engine: "mysql"
  backup_retention: 7
  serverless_v2_min_capacity: 0.5
  serverless_v2_max_capacity: 2.0

docdb:
  storage_encrypted: true

# Application Load Balancer
alb:
  internet_facing: true
  target_group_osd_api:
    port: 8080
    protocol: HTTP
    health_check:
      path: "/actuator/health"
      port: "2112"
      success_codes: "200-399"

# ECS Cluster
ecs_cluster:
  container_insights: true

# ECS Services (osd-api, keycloak, xslt, review, content_quality, document_history)
ecs_services:
  osd_api:
    name: "osd-api"
    cpu: 1024
    memory: 2048
    desired_count: 2
    # ... container definitions, auto-scaling, etc.

# Frontend configuration
front_end:
  angular_build:
    source_bucket_key: "tenant-env-front.zip"
```

**See the template file** (`config/template/template_tenant_prd.yaml`) for a complete example with all available options.

### AWS Accounts

| Account | ID | Tenants | Regions |
|---------|----|---------|---------|
| Principal (IT-Ops) | 111111111111 | Main (dev, stg) | eu-west-1 |
| Tenant2 | 444444444444 | Tenant2 (prd) | eu-central-1 |
| Tenant1 | 333333333333 | Tenant1 (prd) | eu-central-1 |

**Note:** The actual account IDs and tenant names may vary. Check `app.py` for current configuration.

**CI/CD runners use:** `arn:aws:iam::111111111111:user/ops-cicd`

---

## Commands Reference

### Makefile

```bash
make help          # Show all commands
make install-hooks # Install pre-commit hooks
make format        # Format code
make lint          # Run linter
make lint-fix      # Fix imports and format
make test          # Run tests
make synth         # Synthesize stacks
make list          # List all stacks
make diff          # Show differences
make clean         # Clean generated files
make discover      # Generate CI jobs locally
make docker-build  # Build CI/CD runner image
make docker-push   # Push image to ECR
```

### CDK Commands

```bash
cdk list                 # List all stacks
cdk synth                # Synthesize CloudFormation
cdk diff [STACK]         # Show differences
cdk deploy [STACK]       # Deploy stack
cdk destroy [STACK]      # Destroy stack
cdk bootstrap            # Bootstrap account
```

---

## Architecture

### Infrastructure Components

Each tenant stage (`BaseStage`) creates the following stacks:

#### Network Stack
- VPC with configurable CIDR
- Public subnets (configurable AZs) with NAT gateways
- Private subnets (configurable AZs) for workloads
- Isolated subnets (configurable AZs) for databases
- NAT gateway count configurable (0-3)

#### Security Stack
- Security groups for all components:
  - ALB Security Group (HTTPS/HTTP)
  - ECS shared Security Group
  - ECS service-specific Security Groups (osd-api, keycloak)
  - Database Security Groups (Aurora, DocumentDB, Redis)
  - Lambda Security Groups (for database management)

#### Database Stack
- **Aurora MySQL** (Serverless v2) for Keycloak SSO
  - Configurable min/max capacity (ACU)
  - Automatic scaling
  - Backup retention configurable
  - Read replicas support
- **DocumentDB** (MongoDB-compatible) for application data
  - Configurable instance type
  - Encryption at rest
  - Snapshot support
- **Redis** (ElastiCache) for caching
  - Serverless or provisioned mode
  - Configurable engine version
- All databases deployed in isolated subnets (no internet access)

#### Domain Stack
- Route53 hosted zone management
  - Import existing hosted zone, or
  - Create new hosted zone with delegation
- DNS record creation:
  - Frontend domain (e.g., `app-tenant.example.com`)
  - API domain (e.g., `api.app-tenant.example.com`)
  - SSO domain (e.g., `sso.app-tenant.example.com`)
- ACM certificate management:
  - ALB certificate (in deployment region)
  - Automatic DNS validation
- Cross-account delegation support (for parent domain delegation)

#### Storage Stack
- S3 buckets for application storage
- Configurable bucket names per tenant/environment

#### Application Stack
- **Application Load Balancer (ALB)**
  - Internet-facing or internal
  - Target groups for osd-api and keycloak
  - Health check configuration
  - SSL/TLS termination
- **ECS Fargate Cluster**
  - CloudWatch Container Insights
  - Service Connect for service discovery
- **ECS Services:**
  - **osd-api**: Main application service
    - Auto-scaling (CPU/memory based)
    - Service Connect integration
    - Health checks
  - **keycloak**: SSO/authentication service
    - MySQL database connection (Aurora)
    - Admin interface
  - **xslt**: XSLT processor service
    - Fargate Spot support
  - **review**: Fonto review service
    - Fargate Spot support
  - **content-quality**: Fonto content quality service
    - Fargate Spot support
  - **document-history**: Fonto document history service
    - Fargate Spot support

#### Frontend Stack
- **CloudFront Distribution**
  - S3 origin for static assets
  - Custom domain with SSL certificate
  - Route53 DNS records
- **S3 Bucket** for static assets
  - CloudFront origin access

#### CloudFront Certificate Stack
- ACM certificate in `us-east-1` (required for CloudFront)
- DNS validation via Route53
- Cross-region references support

### Shared Stage (Cross-Region Infrastructure)

The `SharedStage` creates shared resources across multiple regions:

- **ECR Repositories** (in all target regions)
  - `osd/osd-api`
  - `osd/xslt-processor`
  - `osd/keycloak`
  - `osd/fonto/review`
  - `osd/fonto/content-quality`
  - `osd/fonto/document-history`
- **Frontend Source Buckets**
  - Primary bucket in `eu-west-1`
  - Replica buckets in replication regions (eu-west-3, eu-central-1)
  - Cross-region replication configured

### Network Topology

```
VPC (configurable CIDR)
├── Public Subnets (configurable AZs)
│   └── NAT Gateways (configurable count)
├── Private Subnets (configurable AZs)
│   └── ECS Services (osd-api, keycloak, xslt, Fonto services)
│       └── Application Load Balancer
└── Isolated Subnets (configurable AZs)
    └── Databases (no internet)
        ├── Aurora MySQL (Keycloak)
        ├── DocumentDB (Application data)
        └── Redis (Cache)
```

### Application Architecture

```
Internet
  ↓
CloudFront Distribution (Frontend)
  ↓
Route53 DNS
  ├── Frontend → CloudFront → S3
  ├── API → ALB → ECS (osd-api)
  └── SSO → ALB → ECS (keycloak)
        ↓
    ECS Services (Service Connect)
        ├── osd-api → DocumentDB, Redis
        ├── keycloak → Aurora MySQL
        └── xslt, review, content-quality, document-history
```

---

## Troubleshooting

### Bootstrap Fails

```bash
# Verify GitLabCrossAccount exists in target account
aws iam get-role --role-name GitLabCrossAccount --profile target-account

# Check trust policy allows ops-cicd user
aws iam get-role --role-name GitLabCrossAccount --query 'Role.AssumeRolePolicyDocument'
```

### Pipeline Fails

**discover-stages fails:**
- Check `cdk list --long` output
- Verify YAML parsing in logs
- Ensure `bootstrap_config.json` is generated

**bootstrap-discovered-accounts fails:**
- Verify `GitLabCrossAccount` exists with correct trust policy
- Ensure `AdministratorAccess` attached

**diff/deploy fails:**
- Verify stack names match discovered stacks
- Check for resource conflicts

### Destructive Changes

```bash
# Review changes
cdk diff STACK_NAME

# Common causes:
# - Changing VPC CIDR
# - Modifying database config
# - Security group rule changes
```

---

## Contributing

### Workflow

```bash
# Create branch
git checkout -b feature/new-tenant

# Make changes
# ... edit files ...

# Test locally
make lint
make test
cdk synth

# Commit (pre-commit hooks run automatically)
git commit -m "feat: add new tenant"

# Push
git push origin feature/new-tenant
```

### Code Standards

- **Python**: PEP 8, black formatter, type hints
- **Commits**: Conventional commit messages
- **Tests**: Add tests for new features
- **Pre-commit**: Hooks run automatically

---

## Documentation

- **Creating a New Tenant**:
  - Quick guide: [docs/CREATING_NEW_TENANT_SIMPLE.md](docs/CREATING_NEW_TENANT_SIMPLE.md) - Ultra-simplified version
  - Complete guide: [docs/CREATING_NEW_TENANT.md](docs/CREATING_NEW_TENANT.md) - Detailed step-by-step
- **Pipeline Details**: See `ci/gitlab/README.md`
- **Scripts Documentation**: See `ci/scripts/README.md`

---

**Built with ❤️ using AWS CDK and GitLab CI/CD**
