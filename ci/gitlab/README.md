# GitLab CI Pipeline Structure

This directory contains the refactored GitLab CI pipeline configuration for CDK deployments.

## Directory Structure

```
ci/
├── gitlab/
│   ├── README.md                   # This file
│   ├── stages/
│   │   ├── 01-validate.yml        # Code quality checks (lint, format, test)
│   │   ├── 02-discover.yml        # CDK stack discovery and job generation
│   │   ├── 03-bootstrap.yml       # AWS account bootstrap (manual, one-time)
│   │   ├── 04-deploy-shared.yml   # Deploy shared infrastructure (S3, ECR) (manual)
│   │   └── 05-triggers.yml        # Environment-specific child pipeline triggers
│   └── templates/                  # (Future) Reusable job templates
└── scripts/
    ├── discover_stages.py         # CDK stack discovery logic
    └── bootstrap_accounts.py      # AWS account bootstrap with AssumeRole
```

## Stage Files

### 01-validate.yml
- **Purpose**: Code quality checks
- **Jobs**: `lint`, `format-check`, `test`
- **When**: On merge requests, main, and develop branches

### 02-discover.yml
- **Purpose**: Discover CDK stacks dynamically
- **Jobs**: `discover-stages`
- **Outputs**:
  - `stages_config.json` - Stage configurations
  - `bootstrap_config.json` - Bootstrap configuration for discovered accounts
  - `gitlab-ci-dynamic-jobs-{env}.yml` - Dynamic job files per environment

### 03-bootstrap.yml
- **Purpose**: Bootstrap AWS accounts for CDK deployments
- **Jobs**: `bootstrap-discovered-accounts` (manual)
- **Script**: Calls `ci/scripts/bootstrap_accounts.py`
- **When**: Manual, one-time per new account

### 04-deploy-shared.yml
- **Purpose**: Deploy shared infrastructure (S3 buckets, ECR repositories) across regions
- **Jobs**: `deploy-shared-stage` (manual)
- **What**: Deploys `SharedOsd/*` stacks
- **When**: Manual, after bootstrap and before environment-specific deployments

### 05-triggers.yml
- **Purpose**: Trigger child pipelines per environment
- **Jobs**:
  - `1-dev-trigger-diff-deploy` (automatic)
  - `2-stg-trigger-diff-deploy` (manual)
  - `3-prd-trigger-diff-deploy` (manual)

## Main Pipeline File

The main `.gitlab-ci.yml` at the root uses conditional includes based on `PIPELINE_TYPE`:

- **Default pipeline** (`.gitlab-ci-default.yml`): Full pipeline with all stages
  - Includes: `01-validate.yml`, `02-discover.yml`, `03-bootstrap.yml`, `04-deploy-shared.yml`, `05-triggers.yml`
  - Stages: `validate`, `discover`, `bootstrap`, `deploy-shared`, `trigger`, `deploy`
  - Used when `PIPELINE_TYPE` is null or not set

- **Single-tenant pipeline** (`.gitlab-ci-deploy-single-tenant.yml`): Tenant-specific deployment
  - Stages: `diff`, `deploy`
  - Used when `PIPELINE_TYPE == "single-tenant"`
  - Requires: `TENANT` and `ENV` variables
  - Optional: `STACK_NAME` (default: "ApplicationStack"), `ECR_IMAGE_URI`

The default pipeline configuration includes:

```yaml
include:
  - local: ci/gitlab/stages/01-validate.yml
  - local: ci/gitlab/stages/02-discover.yml
  - local: ci/gitlab/stages/03-bootstrap.yml
  - local: ci/gitlab/stages/04-deploy-shared.yml
  - local: ci/gitlab/stages/05-triggers.yml
```

## Helper Scripts

### ci/scripts/discover_stages.py
- Discovers CDK stacks from `cdk list --long`
- Extracts AWS account IDs
- Generates dynamic job files per environment
- Generates `bootstrap_config.json`

### ci/scripts/bootstrap_accounts.py
- Bootstraps AWS accounts for CDK deployments
- Uses AssumeRole for cross-account access
- Handles principal and target accounts differently

## Benefits of This Structure

✅ **Modularity**: Each stage in a separate file
✅ **Readability**: Main .gitlab-ci.yml is ~40 lines instead of 288
✅ **Maintainability**: Easy to modify individual stages
✅ **Testability**: Scripts can be tested locally
✅ **Organization**: Clear separation of concerns

## Modifying the Pipeline

To modify a specific stage:
1. Edit the corresponding file in `ci/gitlab/stages/`
2. Commit and push
3. GitLab CI will use the updated configuration

To add a new stage:
1. Create a new file `ci/gitlab/stages/06-your-stage.yml` (or appropriate number)
2. Add it to the `include` section in `.gitlab-ci-default.yml`
3. Add the stage name to the `stages` list in `.gitlab-ci-default.yml`
