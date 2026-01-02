# Fraud Analytics Pipeline

This repository contains a modular pipeline for fraud analytics, including infrastructure, data ingestion, real-time scoring, and analytics modeling.

## Structure
- `infra/` — Infrastructure as code (Terraform)
- `producer/` — CSV to Kinesis producer
- `lambda/` — Kinesis consumer and scoring (AWS Lambda)
- `dbt/` — DBT models and tests
- `docs/` — Diagrams, screenshots, and documentation


## Quick Start

### 1. Infrastructure Setup
- Provision AWS resources using Terraform in `infra/` (see infra/README.md for details)
- Run `make tf-plan` and `make tf-apply` to deploy core infrastructure (Kinesis, S3, IAM, etc.)

### 2. Producer Implementation
- Python producer in `producer/` replays PaySim CSV as JSON events to Kinesis
- Supports configurable event rate, robust error handling, and metrics logging
- Usage:
	- Install dependencies: `pip install -r producer/requirements.txt`
	- Configure `.env` or use CLI args for stream name, region, rate, and CSV path
	- Run: `python producer/main.py`

### 3. Next Steps
- Implement Lambda consumer for real-time fraud scoring and enrichment
- Set up S3 data lake zones (raw/enriched)
- Build dbt models for Redshift analytics
- Add CI/CD and data quality tests

## Contributing
See REQUIREMENTS.md for project conventions and intended content for each directory. PRs and issues welcome!
