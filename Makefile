.PHONY: format lint test synth deploy clean help

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install-hooks:  ## Install pre-commit hooks
	pre-commit install

pre-commit:  ## Run all pre-commit hooks on all files
	pre-commit run --all-files

format:  ## Format code with black and isort
	isort .
	black .

format-check:  ## Check formatting without modifying files
	isort --check-only .
	black --check --diff .

clean-imports:  ## Remove unused imports with autoflake
	autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive .

lint:  ## Run flake8 linter
	flake8 .

lint-fix:  ## Clean imports, format, and lint
	$(MAKE) clean-imports
	$(MAKE) format
	$(MAKE) lint

test:  ## Run pytest tests
	pytest tests/ -v

synth:  ## Synthesize CDK stacks
	cdk synth

list:  ## List all CDK stacks
	cdk list

diff:  ## Show differences for all stacks
	cdk diff

clean:  ## Clean generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf cdk.out htmlcov .coverage cdk_stacks.txt stages_config.json

# CI/CD helpers
ci-discover:  ## Test CI stage discovery locally
	@bash -c "source .venv/bin/activate && cdk list > cdk_stacks.txt && python3 ci/scripts/discover_stages.py"

ci-deploy-dev:  ## Test CI deployment (dev) locally with dry-run
	@bash -c "source .venv/bin/activate && python3 ci/deploy_stages.py dev --dry-run"

ci-deploy-prd:  ## Test CI deployment (prd) locally with dry-run
	@bash -c "source .venv/bin/activate && python3 ci/deploy_stages.py prd --dry-run"

all: lint-fix test  ## Run format, lint, and tests

# Docker/ECR variables
AWS_REGION = eu-west-1
ECR_REGISTRY = 111111111111.dkr.ecr.eu-west-1.amazonaws.com
IMAGE_NAME = infra/osd-cdk-ci-runner
IMAGE_TAG ?= latest
FULL_IMAGE = $(ECR_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

docker-login:  ## Login to AWS ECR
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(ECR_REGISTRY)

docker-build:  ## Build Docker image
	docker build --no-cache -t $(IMAGE_NAME):$(IMAGE_TAG) .

docker-tag:  ## Tag image for ECR
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(FULL_IMAGE)

docker-push: docker-login docker-tag  ## Push image to ECR
	docker push $(FULL_IMAGE)

docker-all: docker-build docker-push  ## Build and push image
	@echo "✅ Image pushed to $(FULL_IMAGE)"
