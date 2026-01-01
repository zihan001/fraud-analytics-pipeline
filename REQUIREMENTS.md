# Real-Time Fraud Analytics Data Engineering Pipeline (AWS)

## 1. Purpose

This document defines the functional and non-functional requirements for a production-inspired, first data engineering project that demonstrates a **real-time + batch hybrid analytics pipeline on AWS** using a fraud detection use case.

The document is intended to be used as **context for development tools (e.g., Copilot)** and as a reference for design decisions, scope boundaries, and tradeoffs.

---

## 2. Goals & Success Criteria

### 2.1 Primary Goals

* Demonstrate an **end-to-end data engineering pipeline** on AWS
* Combine **streaming ingestion** with **batch analytics**
* Use **industry-standard DE tools and patterns**
* Remain simple enough for a first DE project, while being credible and realistic

### 2.2 Success Criteria

* Streaming transactions are ingested, scored, stored, transformed, and visualized
* Pipeline runs end-to-end without manual intervention
* Dashboard shows meaningful fraud analytics (not just raw counts)
* Architecture and tradeoffs are clearly explained in documentation

---

## 3. Dataset Requirements

### 3.1 Dataset

* **Name**: PaySim – Synthetic Financial Dataset for Fraud Detection
* **Source**: Kaggle
* **Format**: CSV (offline), replayed as JSON events

### 3.2 Dataset Characteristics

* Transaction-level records
* Fields include:

  * Transaction type
  * Amount
  * Source and destination balances
  * Fraud label (ground truth)

### 3.3 Dataset Usage

* CSV is replayed row-by-row to simulate live transaction events
* Replay rate must be configurable (events/sec)
* Dataset must support both streaming and batch analytics

---

## 4. High-Level Architecture Requirements

### 4.1 Architecture Pattern

* Hybrid **Streaming + Batch** architecture
* Separation of concerns:

  * Ingestion
  * Real-time processing
  * Storage (lake + warehouse)
  * Transformation
  * Orchestration
  * Visualization

---

## 5. Streaming Ingestion Requirements

### 5.1 Producer

* Implemented as a Python application
* Reads PaySim CSV file
* Emits JSON-formatted transaction events
* Configurable rate (e.g., 5–100 events/sec)

### 5.2 Streaming Platform

* Use **Amazon Kinesis Data Streams**
* Acts as the primary ingestion layer
* Must support replay and scaling

---

## 6. Stream Processing & Fraud Scoring

### 6.1 Stream Consumer

* Implemented using **AWS Lambda**
* Triggered by Kinesis batches

### 6.2 Responsibilities

* Validate event schema
* Apply fraud scoring logic
* Enrich events with derived fields

### 6.3 Fraud Scoring (Phase 1)

Rule-based scoring, executed in real time:

* High transaction amount thresholds
* Transaction velocity (optional)
* Sudden balance drops
* Risky transaction types

### 6.4 Enriched Fields

* `risk_score` (0–100)
* `risk_level` (LOW / MEDIUM / HIGH)
* `is_flagged` (boolean)
* `risk_reasons` (array of strings)

---

## 7. Data Lake (Amazon S3)

### 7.1 Storage Zones

#### Raw Zone

* Stores original transaction events
* Minimal transformation
* Used for reprocessing and audit

#### Enriched Zone

* Stores fraud-scored transactions
* Used as source for analytics and warehouse loading

### 7.2 S3 Layout & Partitioning

* Partition by ingestion time:

  * `dt=YYYY-MM-DD`
  * `hr=HH`

Example:

* `s3://<bucket>/raw/dt=2025-01-01/hr=10/`
* `s3://<bucket>/enriched/dt=2025-01-01/hr=10/`

### 7.3 File Format

* JSON or Parquet (Parquet preferred for enriched data)

### 7.4 Small Files Strategy

* Accept some small files for MVP
* Lambda processes Kinesis batches (not single events)
* Document tradeoff and future optimizations (Firehose, compaction jobs)

---

## 8. Metadata Management

### 8.1 Glue Data Catalog

* Register raw and enriched datasets
* Enable schema discovery
* Support Athena and Redshift external access

---

## 9. Data Warehouse (Amazon Redshift Serverless)

### 9.1 Purpose

* Serve curated, analytics-ready data
* Support BI dashboards and aggregations

### 9.2 Data Loading

* Load enriched data from S3 using `COPY`
* Scheduled (hourly or daily)

### 9.3 Tables

* Staging tables (raw enriched data)
* Fact tables (cleaned transactions)
* Aggregated tables for dashboards

---

## 10. Transformations (dbt)

### 10.1 Tooling

* Use **dbt with Redshift adapter**

### 10.2 Responsibilities

* Clean and standardize data
* Deduplicate transactions
* Build fact and aggregate models
* Create metrics for dashboards

### 10.3 Data Quality

* dbt tests:

  * Not null checks
  * Accepted values (risk_level)
  * Uniqueness (transaction_id)

---

## 11. Orchestration

### 11.1 Tool

* Use **Amazon EventBridge**

### 11.2 Orchestrated Tasks

* Trigger S3 → Redshift loads
* Trigger dbt runs
* Run data quality checks

### 11.3 Design Principles

* Simple, AWS-native
* No Airflow for MVP

---

## 12. Dashboard & Analytics

### 12.1 Tool

* **Amazon QuickSight**

### 12.2 Dashboard Requirements

#### Tile 1: Real-Time Fraud Monitor

* Time series (last 1h / 24h):

  * Total transactions
  * Flagged transactions
  * Fraud rate (%)
  * Fraud amount

Purpose: Monitor fraud activity over time

#### Tile 2: Fraud Drivers / Hotspots

One of:

* Fraud rate by transaction type
* Fraud amount by amount bucket
* Top risk rule contributors

Purpose: Explain *why* fraud is happening

---

## 13. CI/CD Requirements

### 13.1 Scope

CI/CD should cover:

* Infrastructure code (Terraform or CloudFormation)
* Lambda functions
* Producer code
* dbt models

### 13.2 CI (Continuous Integration)

* Triggered on pull requests
* Responsibilities:

  * Linting
  * Unit tests (where applicable)
  * dbt compile / test

### 13.3 CD (Continuous Deployment)

* Triggered on merge to `main`
* Deploy infrastructure and application code
* Environment: single dev environment for MVP

### 13.4 Tooling

* GitHub Actions (preferred)
* AWS IAM roles for deployment

---

## 14. Non-Functional Requirements

### 14.1 Simplicity

* Prefer managed AWS services
* Avoid over-engineering

### 14.2 Cost Awareness

* Use serverless where possible
* Low-volume data assumptions

### 14.3 Observability

* CloudWatch logs for Lambda
* Basic error handling and metrics
* Alarm on error rates / throttles (at least for Lambda + Redshift loads)

### 14.4 Security (Priority)

Security is **in-scope** and must be implemented in a realistic MVP form.

**Identity & Access (IAM)**

* Least-privilege IAM roles for:

  * Producer (if running outside AWS, use limited credentials or no direct AWS access)
  * Lambda Kinesis consumer
  * S3 writers/readers
  * Redshift load role
  * CI/CD deployment role
* No long-lived keys committed to repo

**Data Protection**

* S3 buckets encrypted with SSE-KMS
* Redshift encryption enabled (default for serverless) and use KMS where applicable
* Encrypt data in transit (HTTPS/TLS)

**Secrets Management**

* Store secrets in AWS Secrets Manager or SSM Parameter Store
* CI/CD uses OIDC + assumed role (recommended) instead of static AWS keys

**Network & Perimeter**

* Prefer private access where feasible:

  * VPC endpoints for S3 (Gateway endpoint)
  * Restrict S3 bucket policies to known principals
* Tight security groups if anything runs in VPC

**Audit & Logging**

* Enable CloudTrail (at least management events) for auditability
* S3 access logging or CloudTrail data events for sensitive buckets (optional if cost-conscious, but document)

**Safety Controls**

* Guardrails via bucket policies (block public access)
* Tagging for cost/security ownership

### 14.5 Documentation

* Clear README
* Architecture diagram
* Tradeoffs and future improvements documented

---

## 15. Stretch Goals (Optional) (Optional)

* SNS alerts for high fraud spikes
* ML-based fraud scoring model
* Feature store using DynamoDB
* Late-arriving data handling
* Compaction jobs for small files

---

## 16. Explicit Out of Scope (for MVP)

* Multi-region deployment
* Advanced ML model monitoring
* Complex workflow engines (Airflow)
* **Security hardening beyond an MVP baseline** (e.g., full SOC2-style controls, advanced SIEM integrations)

---

## 17. Hybrid Streaming + Batch Explanation

This project is hybrid because it has **two complementary paths**:

### 17.1 Streaming Path (Real-Time)

* Producer → Kinesis → Lambda
* Lambda validates + scores each event
* Writes raw and enriched events to S3
* Goal: low-latency fraud scoring and near-real-time monitoring

### 17.2 Batch Path (Scheduled Analytics)

* On a schedule (e.g., hourly/daily):

  * Load recent S3 enriched partitions into Redshift (`COPY`)
  * Run dbt transformations and tests
  * Refresh dashboard datasets
* Goal: consistent, analytics-ready tables and aggregates with warehouse performance

### 17.3 Why Not Only Streaming?

Streaming is great for per-event enrichment, but batch is still needed for:

* Warehouse loads and table maintenance
* Recomputing aggregates reliably
* Backfills and reprocessing
* Data quality checks and governance

---

## 18. Design Philosophy

> Build something **small, correct, explainable, and extensible**.

This project should tell a clear story:

* How data flows
* Why each tool is used
* What tradeoffs were made
* How it could evolve in production

---

## 19. Implementation Status & Decisions

### 19.1 Infrastructure (Terraform)

**Status:** ✅ **Complete**

#### Bootstrap Infrastructure
* S3 backend for Terraform state with versioning and encryption
* DynamoDB table for state locking
* KMS key for state encryption with rotation enabled
* GitHub Actions OIDC provider for CI/CD (no static credentials)
* Location: `infra/bootstrap/`

#### Dev Environment Infrastructure
* **Cost-optimized with feature flags** for portfolio projects
* S3 data lake (raw + enriched zones) with lifecycle policies
* AWS Glue Data Catalog for Athena queries
* Kinesis Data Stream (1 shard) for streaming ingestion
* Lambda fraud scorer with Kinesis trigger and DLQ
* **Optional Redshift Serverless** (disabled by default)
* CloudWatch logs (3-day retention) and alarms (disabled by default)
* KMS encryption for all services
* Location: `infra/envs/dev/`

#### Portfolio Mode Design
* **Default mode:** S3 + Glue + Athena (~$20/month)
* **Demo mode:** Enable Redshift temporarily (~$40-60/month)
* **Usage limits:** 50 RPU-hour/month guardrail on Redshift
* **Lifecycle policies:** Aggressive (7-day raw, 30-day enriched)
* **Workflow:** Build → Demo → Destroy to minimize costs

**Deployment:**
```bash
make tf-init-dev
make tf-plan-dev
make tf-apply-dev
```

### 19.2 Version Control & CI/CD

**Status:** ✅ **Complete**

#### Git Repository
* Repository: `github.com/zihan001/fraud-analytics-pipeline`
* Branch strategy: main branch (simple for portfolio)
* `.gitignore` excludes: Terraform state, secrets, Python cache, IDE files

#### GitHub Actions Workflows

**Validation Workflow** (`.github/workflows/validate.yml`)
* Runs on: Every push and pull request
* Jobs:
  1. **Terraform validation:** Format check, init, validate (bootstrap + dev)
  2. **Python linting:** Black formatting, Flake8 syntax checks
  3. **Markdown linting:** Documentation quality checks
* Purpose: Catch errors before deployment
* No AWS credentials required (uses `-backend=false`)

**Future Workflows** (Planned):
* Unit tests for Producer/Lambda (Phase 2)
* Automated deployment using OIDC role (Phase 3)

### 19.3 Cost Optimization Features

**Feature Flags** (in `variables.tf`):
* `enable_redshift` (default: false) - Toggle Redshift Serverless
* `enable_cloudwatch_alarms` (default: false) - Toggle monitoring alerts
* `enable_kinesis` (default: true) - Toggle streaming ingestion
* `enable_lambda` (default: true) - Toggle fraud scoring

**Cost Guardrails:**
* Redshift usage limit: 50 RPU-hours/month (~$19 cap)
* S3 lifecycle: 7-day expiration (raw), 30-day Glacier transition (enriched)
* CloudWatch log retention: 3 days (dev environment)
* Minimum Redshift capacity: 4 RPUs (AWS minimum)

**Monthly Cost Estimates:**
| Mode | Cost | Components |
|------|------|------------|
| Portfolio (default) | ~$20 | Kinesis + Lambda + S3 + Athena queries |
| Demo (Redshift ON) | ~$40-60 | Above + Redshift Serverless (limited usage) |

### 19.4 Architecture Decisions

#### Why Athena Instead of Always-On Redshift?
* **Cost:** Athena is pay-per-query vs. Redshift always-on costs
* **Portfolio fit:** Demonstrates data lake + SQL analytics without high costs
* **Flexibility:** Can enable Redshift temporarily for dbt/QuickSight demos
* **Production path:** Same Glue catalog works with both

#### Why No VPC?
* **Simplicity:** Faster deployment, fewer moving parts
* **Cost:** Avoids NAT Gateway (~$32/month) and VPC endpoint costs
* **Security:** Still encrypted (TLS in transit, KMS at rest)
* **Trade-off:** Acceptable for dev/portfolio, add VPC for production

#### Why Single main.tf?
* **Clarity:** All resources visible in one file (~840 lines)
* **Portfolio scale:** Manageable for small project
* **Trade-off:** Would refactor into modules for production/teams

#### Why Feature Flags?
* **Portfolio agility:** Enable/disable components without code changes
* **Cost control:** Toggle expensive resources (Redshift) on demand
* **Demo flexibility:** Turn on advanced features for specific demos
* **Learning tool:** Understand cost impact of each service

### 19.5 Next Steps

**Immediate (In Progress):**
- [ ] Deploy dev infrastructure to AWS
- [ ] Implement Producer (Python app to replay CSV → Kinesis)
- [ ] Implement Lambda fraud scorer (enrichment logic)

**Phase 2:**
- [ ] Add unit tests for Producer and Lambda
- [ ] Add GitHub Actions test workflow
- [ ] End-to-end pipeline testing

**Phase 3 (Optional - If Redshift Demo Needed):**
- [ ] Implement dbt models for Redshift transformations
- [ ] Create QuickSight dashboard
- [ ] Document Redshift vs. Athena comparison

**Phase 4:**
- [ ] Architecture diagram in docs/
- [ ] Demo video/screenshots for portfolio
- [ ] Performance and cost analysis documentation

### 19.6 Deployment Workflow

**For Portfolio Projects:**
```bash
# 1. Deploy low-cost stack
cd infra/envs/dev
cp terraform.tfvars.example terraform.tfvars
make tf-init-dev
make tf-apply-dev

# 2. Build and test with Athena
# - Run producer → Kinesis → Lambda → S3
# - Query enriched data with Athena
# - Capture screenshots/proof

# 3. Optional: Enable Redshift for advanced demo
terraform apply -var="enable_redshift=true"
# - Run dbt transformations
# - Build QuickSight dashboard
# - Capture proof IMMEDIATELY

# 4. Destroy when done
make tf-destroy-dev
```

---
