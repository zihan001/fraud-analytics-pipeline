# Makefile for common project tasks

.PHONY: fmt lint test tf-plan tf-apply tf-plan-bootstrap tf-apply-bootstrap tf-plan-dev tf-apply-dev tf-init-dev tf-destroy-dev

fmt:
	black producer lambda
	terraform -chdir=infra/bootstrap fmt
	terraform -chdir=infra/envs/dev fmt

lint:
	flake8 producer lambda
	terraform -chdir=infra/bootstrap validate
	terraform -chdir=infra/envs/dev validate

# Add your test commands here
test:
	pytest producer lambda

# Bootstrap infrastructure (run once)
tf-plan-bootstrap:
	terraform -chdir=infra/bootstrap plan

tf-apply-bootstrap:
	terraform -chdir=infra/bootstrap apply

# Dev environment infrastructure
tf-init-dev:
	terraform -chdir=infra/envs/dev init

tf-plan-dev:
	terraform -chdir=infra/envs/dev plan

tf-apply-dev:
	terraform -chdir=infra/envs/dev apply

tf-destroy-dev:
	terraform -chdir=infra/envs/dev destroy

# Legacy targets (deprecated - use env-specific targets)
tf-plan:
	@echo "⚠️  Deprecated: Use 'make tf-plan-dev' or 'make tf-plan-bootstrap' instead"
	terraform -chdir=infra/envs/dev plan

tf-apply:
	@echo "⚠️  Deprecated: Use 'make tf-apply-dev' or 'make tf-apply-bootstrap' instead"
	terraform -chdir=infra/envs/dev apply
