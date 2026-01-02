# Makefile for common project tasks

.PHONY: fmt lint test lambda-test lambda-deploy lambda-package tf-plan tf-apply tf-plan-bootstrap tf-apply-bootstrap tf-plan-dev tf-apply-dev tf-init-dev tf-destroy-dev

fmt:
	black producer lambda
	terraform -chdir=infra/bootstrap fmt
	terraform -chdir=infra/envs/dev fmt

lint:
	flake8 producer lambda
	terraform -chdir=infra/bootstrap validate
	terraform -chdir=infra/envs/dev validate

# Test commands
test:
	pytest producer lambda

lambda-test:
	pytest lambda/test_handler.py -v

# Lambda deployment
lambda-package:
	cd lambda && \
	rm -f lambda.zip && \
	pip install -r requirements.txt -t package/ && \
	cd package && zip -r ../lambda.zip . && cd .. && \
	zip -g lambda.zip handler.py

lambda-deploy: lambda-package
	@echo "Deploying Lambda function..."
	aws lambda update-function-code \
		--function-name fraud-analytics-dev-fraud-scorer \
		--zip-file fileb://lambda/lambda.zip
	@echo "✅ Lambda deployed successfully"

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
