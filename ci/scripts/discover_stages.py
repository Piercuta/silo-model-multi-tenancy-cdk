#!/usr/bin/env python3
"""
Discover CDK stages dynamically from cdk list output.

This script parses the output of 'cdk list' and groups stacks by stage,
generating a JSON configuration file for deployment.
"""

import json
import sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import yaml


def parse_cdk_stacks_from_yaml(yaml_file: str = "cdk_stacks_long.yml") -> List[str]:
    """
    Read and parse CDK stacks from cdk list --long YAML output.

    Args:
        yaml_file: Path to YAML file containing cdk list --long output

    Returns:
        List of stack names in the format StageName/StackName
    """
    print(f"   Reading YAML file for stacks: {yaml_file}")
    with open(yaml_file, "r") as f:
        stacks_data = yaml.safe_load(f)

    stacks: List[str] = []

    if stacks_data and isinstance(stacks_data, list):
        for stack in stacks_data:
            stack_id = stack.get("id")
            if not stack_id:
                continue
            # Example: "PcoDevStage/DomainStack (PcoDevStage-DomainStack)"
            # Keep only the "PcoDevStage/DomainStack" part before the first space
            stacks.append(stack_id.split(" ")[0])

    return stacks


def group_by_stage(stacks: List[str]) -> Dict[str, List[str]]:
    """
    Group stacks by their stage name.

    Args:
        stacks: List of stack names (format: StageName/StackName)

    Returns:
        Dictionary mapping stage names to lists of stacks
    """
    stages = defaultdict(list)
    for stack in stacks:
        if "/" in stack:
            stage_name = stack.split("/")[0]
            stages[stage_name].append(stack)
    return dict(stages)


def detect_environment_type(stage_name: str) -> str:
    """
    Detect environment type from stage name.

    Args:
        stage_name: Name of the CDK stage

    Returns:
        Environment type: 'dev', 'stg', 'prd', or 'other'
    """
    stage_lower = stage_name.lower()

    if "dev" in stage_lower:
        return "dev"
    elif "stg" in stage_lower or "staging" in stage_lower:
        return "stg"
    elif "prd" in stage_lower or "prod" in stage_lower:
        return "prd"
    else:
        return "other"


def create_stage_configs(grouped_stages: Dict[str, List[str]]) -> List[Dict]:
    """
    Create deployment configuration for each stage.

    Args:
        grouped_stages: Dictionary of stage names to stack lists

    Returns:
        List of stage configurations
    """
    stage_configs = []

    for stage_name, stack_list in grouped_stages.items():
        env_type = detect_environment_type(stage_name)

        config = {
            "stage_name": stage_name,
            "stacks": stack_list,
            "stack_count": len(stack_list),
            "env_type": env_type,
            "deploy_pattern": f"{stage_name}/*",
        }
        stage_configs.append(config)

    return stage_configs


def extract_accounts_from_yaml(yaml_file: str = "cdk_stacks_long.yml") -> Set[Tuple[str, str]]:
    """
    Extract unique (account_id, region) pairs from cdk list --long output (YAML format).

    Args:
        yaml_file: Path to YAML file containing cdk list --long output

    Returns:
        Set of unique (account_id, region) pairs
    """
    accounts: Set[Tuple[str, str]] = set()

    try:
        print(f"   Reading YAML file: {yaml_file}")
        with open(yaml_file, "r") as f:
            stacks_data = yaml.safe_load(f)

        print("   YAML parsed successfully")
        print(f"   Data type: {type(stacks_data)}")

        if stacks_data and isinstance(stacks_data, list):
            print(f"   Processing {len(stacks_data)} stack entries")
            for stack in stacks_data:
                environment = stack.get("environment", {})
                account_id = environment.get("account")
                region = environment.get("region")

                if account_id and region:
                    account_id_str = str(account_id)
                    accounts.add((account_id_str, region))
                    print(f"   Found account: {account_id_str} in region: {region}")
        else:
            print("   ⚠️  Data is not a list or is empty")
            if stacks_data:
                print(f"   First few chars: {str(stacks_data)[:200]}")
    except FileNotFoundError:
        print(f"⚠️  Error: File {yaml_file} not found")
        return set()
    except Exception as e:
        print(f"⚠️  Error parsing YAML file: {e}")
        import traceback

        traceback.print_exc()
        return set()

    return accounts


def generate_bootstrap_config(accounts: Set[Tuple[str, str]], principal_account: str) -> Dict:
    """
    Generate bootstrap configuration for discovered accounts.

    Args:
        accounts: Set of discovered (account_id, region) pairs
        principal_account: Principal account ID (the one running deployments)

    Returns:
        Bootstrap configuration dictionary
    """
    config = {
        "principal_account": principal_account,
        "accounts": [],
    }

    for account_id, region in sorted(accounts):
        account_config = {
            "account_id": account_id,
            "region": region,
        }

        # Principal account doesn't need trust relationship
        if account_id == principal_account:
            account_config["is_principal"] = True
            account_config["needs_trust"] = False
        else:
            account_config["is_principal"] = False
            account_config["needs_trust"] = True

        config["accounts"].append(account_config)

    return config


def extract_tenant_and_env(stage_name: str) -> tuple[str, str]:
    """
    Extract tenant and environment from stage name.

    Args:
        stage_name: Stage name in format "Tenant-Env" (e.g., "Pco-Dev", "Che-Prd")

    Returns:
        Tuple of (tenant, env) in lowercase
    """
    if "-" in stage_name:
        parts = stage_name.split("-", 1)
        tenant = parts[0].lower()
        env = parts[1].lower()
        return (tenant, env)
    else:
        # Fallback: try to detect env from stage name
        env = detect_environment_type(stage_name)
        # Extract tenant by removing env suffix
        tenant = stage_name.lower().replace(env, "").replace("-", "").strip()
        return (tenant if tenant else "unknown", env)


def generate_gitlab_dynamic_jobs(configs: List[Dict], ecr_image: str) -> str:
    """
    Generate GitLab CI YAML for dynamic deployment jobs.

    Args:
        configs: List of stage configurations
        ecr_image: ECR image to use for jobs

    Returns:
        YAML string with job definitions (diff + deploy for each stage, destroy for non-prd stages)
    """
    # Check if any non-prd stages exist to include the destroy stage
    has_destroy_stages = any(cfg["env_type"] != "prd" for cfg in configs)

    # Start with stages definition for child pipeline
    destroy_stage = "\n  - destroy" if has_destroy_stages else ""
    header = f"""# Dynamically generated GitLab CI jobs
# Generated by discover_stages.py

stages:
  - diff
  - deploy{destroy_stage}

"""
    jobs = []

    for config in configs:
        stage_name = config["stage_name"]
        env_type = config["env_type"]
        deploy_pattern = config["deploy_pattern"]
        stack_count = config["stack_count"]

        # Extract tenant and env from stage name (format: Tenant-Env)
        tenant, env = extract_tenant_and_env(stage_name)

        # Format d'environnement sûr pour GitLab (sans slash)
        env_name = f"{env_type}-{stage_name}" if env_type else stage_name

        # Job names avec prefix env pour grouping visuel
        diff_job_name = f"diff:{env_type}:{stage_name}"
        deploy_job_name = f"deploy:{env_type}:{stage_name}"
        destroy_job_name = f"destroy:{env_type}:{stage_name}"

        # Déterminer si auto ou manuel pour le deploy
        deploy_when = "manual"  # "on_success" if env_type == "dev" else "manual"

        # CDK context flags
        cdk_context = f"-c tenant={tenant} -c env={env}"

        # Job 1: Diff (always automatic to show changes)
        diff_job_yaml = f"""{diff_job_name}:
  stage: diff
  image: "{ecr_image}"
  variables:
    CDK_DISABLE_TYPEGUARD: "1"
  allow_failure: true
  script:
    - echo "📊 Showing diff for {stage_name} ({env_type})"
    - echo "Tenant {tenant}, Env {env}"
    - echo "Stacks - {stack_count}"
    - echo "Pattern - {deploy_pattern}"
    - echo ""
    - echo "📊 Running - cdk diff {deploy_pattern} {cdk_context}"
    - |
      # Run cdk diff with context and capture output
      cdk diff {deploy_pattern} {cdk_context} | tee diff_output.txt
      DIFF_EXIT_CODE=${{PIPESTATUS[0]}}

      # Check for dangerous operations in the diff output
      DANGEROUS_WORDS="requires replacement|dangerous word"
      if grep -iE "$DANGEROUS_WORDS" diff_output.txt > /dev/null; then
        echo ""
        echo "⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️"
        echo "⚠️  WARNING: DESTRUCTIVE CHANGES DETECTED!"
        echo "⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️"
        echo ""
        echo "🔥 The following dangerous operations were found:"
        grep -iE "$DANGEROUS_WORDS" diff_output.txt | head -20
        echo ""
        echo "⚠️  Please review carefully before deploying!"
        echo "⚠️  Resources may be REPLACED or DESTROYED!"
        echo ""
        # Clean up temp file
        rm -f diff_output.txt
        # Exit with code 1 to show warning icon in GitLab
        exit 1
      else
        echo ""
        echo "✅ No destructive changes detected"
        echo ""
        # Clean up temp file
        rm -f diff_output.txt
        # Exit with the original cdk diff exit code
        exit $DIFF_EXIT_CODE
      fi
  when: on_success
  only:
    - main
    - develop"""

        # Job 2: Deploy (depends on diff)
        deploy_job_yaml = f"""{deploy_job_name}:
  stage: deploy
  image: "{ecr_image}"
  variables:
    CDK_DISABLE_TYPEGUARD: "1"
  needs:
    - {diff_job_name}
  script:
    - echo "🚀 Deploying {stage_name} ({env_type})"
    - echo "Tenant {tenant}, Env {env}"
    - echo "Stacks - {stack_count}"
    - echo "Pattern - {deploy_pattern}"
    - echo "🚀 Running - cdk deploy {deploy_pattern} {cdk_context} --require-approval never --concurrency 4 --progress events"
    - cdk deploy {deploy_pattern} {cdk_context} --require-approval never --concurrency 4 --progress events
  environment:
    name: "{env_name}"
  when: {deploy_when}
  only:
    - main
    - develop"""

        jobs.append(diff_job_yaml)
        jobs.append(deploy_job_yaml)

        # Job 3: Destroy (manual, in separate destroy stage, depends on deploy)
        # Skip destroy job for production environments to prevent accidental destruction
        if env_type != "prd":
            destroy_job_yaml = f"""{destroy_job_name}:
  stage: destroy
  image: "{ecr_image}"
  variables:
    CDK_DISABLE_TYPEGUARD: "1"
  needs:
    - {deploy_job_name}
  script:
    - echo "💣 Destroying {stage_name} ({env_type})"
    - echo "Tenant {tenant}, Env {env}"
    - echo "Stacks - {stack_count}"
    - echo "Pattern - {deploy_pattern}"
    - echo "💣 Running - cdk destroy {deploy_pattern} {cdk_context} --require-approval never --force --concurrency 4 --progress events"
    - cdk destroy {deploy_pattern} {cdk_context} --require-approval never --force --concurrency 4 --progress events
  environment:
    name: "{env_name}"
    action: stop
  when: manual
  only:
    - main
    - develop"""

            jobs.append(destroy_job_yaml)

    return header + "\n\n".join(jobs)


def main():
    """Main function to discover and save stage configurations."""
    import os

    print("🔍 Discovering CDK stages...")
    yaml_file = "cdk_stacks_long.yml"

    # Parse stacks from cdk list --long YAML output
    stacks = parse_cdk_stacks_from_yaml(yaml_file)
    print(f"   Found {len(stacks)} total stacks from {yaml_file}")

    # Group by stage
    grouped = group_by_stage(stacks)
    print(f"   Grouped into {len(grouped)} stages")

    # Create configs
    configs = create_stage_configs(grouped)

    # Save to JSON
    output_file = "stages_config.json"
    with open(output_file, "w") as f:
        json.dump(configs, f, indent=2)

    # Generate dynamic GitLab jobs per environment
    ecr_image = os.getenv(
        "ECR_IMAGE",
        "$LATEST_CDK_DEPLOY_ECR_IMAGE",
    )

    # Generate separate YAML files for each environment
    env_types = ["dev", "stg", "prd"]
    generated_files = []

    for env_type in env_types:
        # Filter configs by environment
        env_configs = [cfg for cfg in configs if cfg["env_type"] == env_type]

        if env_configs:
            gitlab_jobs_yaml = generate_gitlab_dynamic_jobs(env_configs, ecr_image)
            gitlab_jobs_file = f"gitlab-ci-dynamic-jobs-{env_type}.yml"
            with open(gitlab_jobs_file, "w") as f:
                f.write(gitlab_jobs_yaml)
            generated_files.append((env_type, gitlab_jobs_file, len(env_configs)))

    # Extract AWS accounts from cdk list --long output (if available)
    print("\n🔍 Extracting AWS account information...")
    accounts = extract_accounts_from_yaml(yaml_file)

    if accounts:
        print(f"   Found {len(accounts)} unique AWS account(s)/region pair(s):")
        for account_id, account_region in sorted(accounts):
            print(f"   - {account_id} ({account_region})")

        # Generate bootstrap configuration
        principal_account = os.getenv(
            "AWS_PRINCIPAL_ACCOUNT_ID",
            os.getenv("AWS_ACCOUNT_ID", "111111111111"),
        )

        bootstrap_config = generate_bootstrap_config(accounts, principal_account)

        # Save bootstrap config
        bootstrap_file = "bootstrap_config.json"
        with open(bootstrap_file, "w") as f:
            json.dump(bootstrap_config, f, indent=2)

        print(f"\n📝 Bootstrap configuration saved to {bootstrap_file}")
        print(f"   Principal account: {principal_account}")
        print(
            f"   Accounts needing trust: "
            f"{len([a for a in bootstrap_config['accounts'] if a['needs_trust']])}"
        )
    else:
        print("   ⚠️  No YAML file found - skipping bootstrap config generation")
        print(f"   (Expected file: {yaml_file})")

    # Display summary
    print(f"\n✅ Discovered {len(configs)} stages:")
    for config in configs:
        print(
            f"  - {config['stage_name']:<30} ({config['env_type']:>3}) : "
            f"{config['stack_count']} stacks"
        )

    print(f"\n📝 Configuration saved to {output_file}")
    print("📝 GitLab dynamic jobs saved:")
    for env_type, filename, count in generated_files:
        print(f"   - {filename} ({count} stages for {env_type})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
