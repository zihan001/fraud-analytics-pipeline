# Dev Environment Infrastructure

This directory contains the Terraform configuration for the development environment of the fraud analytics pipeline.

## 🎯 Portfolio Mode (Cost-Optimized)

**This infrastructure is designed for rapid build → demo → destroy cycles to minimize AWS costs.**

### Default Mode: Low-Cost Athena Workflow (~$15-20/month)
- ✅ S3 data lake with partitioned raw/enriched zones
- ✅ AWS Glue Data Catalog for schema management
- ✅ Query enriched data directly with **Athena** (pay-per-query)
- ✅ Kinesis + Lambda for real-time fraud scoring
- ❌ Redshift **DISABLED** by default (saves ~$200/month)

### Demo Mode: Enable Redshift for Short Windows
- 🔄 Temporarily enable Redshift Serverless for dbt demos
- 🛡️ Usage limit guardrail: 50 RPU-hours/month (~$19 cap)
- 📸 Capture proof, then disable or destroy immediately

---

## Prerequisites

1. **Bootstrap infrastructure must be deployed first** - See [../../bootstrap/README.md](../../bootstrap/README.md)
2. AWS CLI configured with appropriate credentials
3. Terraform >= 1.0 installed

---

## Quick Start (Portfolio Mode)

### 1. Create Configuration File

```bash
cd infra/envs/dev
cp terraform.tfvars.example terraform.tfvars
```

**Key settings in `terraform.tfvars`:**
```hcl
enable_redshift          = false  # Keep OFF for low cost
enable_cloudwatch_alarms = false  # Optional monitoring
enable_kinesis           = true   # Streaming demo
enable_lambda            = true   # Fraud scoring demo
```

### 2. Initialize Terraform

```bash
make tf-init-dev
```

### 3. Deploy Low-Cost Stack

```bash
make tf-plan-dev   # Review what will be created
make tf-apply-dev  # Deploy S3 + Glue + Kinesis + Lambda
```

**Monthly cost: ~$15-20** (no Redshift)

### 4. Test the Pipeline with Athena

#### Query enriched data in S3:

```sql
-- Run in Athena console
SELECT 
    risk_level, 
    COUNT(*) as transaction_count,
    AVG(risk_score) as avg_risk_score
FROM fraud_analytics_dev.enriched_transactions
WHERE dt = '2026-01-01'
GROUP BY risk_level
ORDER BY transaction_count DESC;
```

#### Capture screenshots/proof:
- Athena query results
- S3 enriched bucket with partitioned data
- Lambda CloudWatch logs showing fraud scoring
- Kinesis stream metrics

---

## Demo Mode: Temporarily Enable Redshift

### When You Need Redshift (for dbt transformations or dashboard demos):

```bash
# Enable Redshift for demo
terraform apply -var="enable_redshift=true"
```

**This adds:**
- Redshift Serverless namespace (4 RPU base capacity)
- Usage limit: 50 RPU-hours/month (~$19 guardrail)
- Secrets Manager for credentials
- CloudWatch logs

**Monthly cost increases to: ~$35-40**

### Run Your Demo:
1. Connect dbt to Redshift (see outputs for endpoint)
2. Run transformations: `dbt run`
3. Build QuickSight dashboard
4. **Capture proof immediately**

### Disable Redshift After Demo:

```bash
# Turn Redshift back OFF
terraform apply -var="enable_redshift=false"

# OR destroy everything if done
terraform destroy
```

---

## Feature Flags (Cost Control)

| Flag | Purpose | Default | Monthly Cost Impact |
|------|---------|---------|---------------------|
| `enable_redshift` | Redshift Serverless for dbt/dashboards | `false` | +$20-200 (depends on usage) |
| `enable_cloudwatch_alarms` | Email alerts for errors/throttles | `false` | +$2 |
| `enable_kinesis` | Streaming ingestion | `true` | +$11 |
| `enable_lambda` | Real-time fraud scoring | `true` | +$5 |

**Toggle in `terraform.tfvars` or via CLI:**
```bash
terraform apply -var="enable_redshift=true" -var="enable_cloudwatch_alarms=true"
```

---

## Infrastructure Components

All components below are **conditionally deployed** based on feature flags.

### Always Enabled (Core)
- **S3 Raw Bucket**: Original transaction events, 7-day expiration
- **S3 Enriched Bucket**: Fraud-scored events, Glacier transition after 30 days
- **AWS Glue Data Catalog**: Schema metadata for Athena queries
- **KMS Key**: Customer-managed encryption for all services

### Enabled by Default (Streaming Demo)
- **Kinesis Data Stream** (1 shard): Real-time event ingestion
- **Lambda Function**: Fraud scoring processor (triggered by Kinesis)
- **SQS Dead Letter Queue**: Failed event handling

### Optional (Demo Only)
- **Redshift Serverless**: Analytics warehouse (disabled by default)
  - Minimum 4 RPU base capacity
  - Usage limit: 50 RPU-hours/month guardrail
  - Secrets Manager for admin credentials
- **CloudWatch Alarms**: Error/throttle monitoring (disabled by default)
- **EventBridge Rule**: Daily S3→Redshift load schedule (always created, needs targets)

---

## Cost Breakdown

### Low-Cost Mode (Default: `enable_redshift=false`)
| Service | Cost/Month | Notes |
|---------|------------|-------|
| Kinesis (1 shard) | ~$11 | Handles up to 1K TPS |
| Lambda | ~$5 | Light usage, generous free tier |
| S3 | ~$3 | With aggressive lifecycle policies |
| Glue Catalog | Free | First 1M objects/month |
| KMS | ~$1 | Per key |
| CloudWatch Logs | ~$1 | 3-day retention |
| **Total** | **~$20** | **Portfolio-friendly** |

### Demo Mode (Redshift Enabled)
| Additional Service | Cost/Month | Notes |
|-------------------|------------|-------|
| Redshift Serverless | ~$19-40 | 50 RPU-hour limit enforced |
| Secrets Manager | ~$0.40 | Per secret |
| **New Total** | **~$40-60** | **Enable only for demos** |

---

## Configuration Variables

| Variable | Description | Default | Portfolio Recommendation |
|----------|-------------|---------|--------------------------|
| `enable_redshift` | Enable Redshift Serverless | `false` | Keep `false`, toggle for demos |
| `enable_cloudwatch_alarms` | Email alerts | `false` | Optional |
| `enable_kinesis` | Streaming ingestion | `true` | Required for demo |
| `enable_lambda` | Fraud scoring | `true` | Required for demo |
| `redshift_base_capacity` | RPUs (min 4) | `4` | Use minimum |
| `redshift_rpu_hour_limit` | Monthly usage cap | `50` | Prevents runaway costs |
| `s3_raw_expiration_days` | Raw data retention | `7` | Aggressive for dev |
| `cloudwatch_log_retention_days` | Log retention | `3` | Minimize storage costs |

See [variables.tf](variables.tf) for complete list.

---

## Outputs

Key outputs after deployment (null if feature disabled):

- **Kinesis Stream Name**: For producer configuration
- **Lambda Function Name**: For code deployment
- **S3 Bucket Names**: For data inspection
- **Glue Database Name**: For Athena queries
- **Redshift Endpoint**: For dbt connection (if enabled)
- **Redshift Usage Limit ID**: Verify guardrail is active

```bash
terraform output  # View all outputs
terraform output kinesis_stream_name  # Get specific value
```

---

## Workflow: Build → Demo → Destroy

### Phase 1: Build & Test with Athena
```bash
# Deploy low-cost stack
make tf-apply-dev

# Run producer to generate data
cd ../../../producer
python main.py --stream-name=$(terraform -chdir=../infra/envs/dev output -raw kinesis_stream_name)

# Query with Athena
# Use AWS Console → Athena → Query enriched_transactions table
# Capture screenshots of:
#   - Partitioned S3 data
#   - Athena query results
#   - Lambda execution logs
```

### Phase 2: Enable Redshift for Advanced Demo (Optional)
```bash
# Turn on Redshift temporarily
terraform apply -var="enable_redshift=true"

# Connect dbt
cd ../../../dbt
dbt run --profiles-dir .

# Build QuickSight dashboard
# Connect to Redshift endpoint (see outputs)

# Capture proof immediately
```

### Phase 3: Destroy to Stop Costs
```bash
# Option A: Disable Redshift but keep other resources
terraform apply -var="enable_redshift=false"

# Option B: Destroy everything
make tf-destroy-dev

# Verify in AWS Console that resources are gone
```

---

## Athena Query Examples

Once data is in S3 enriched bucket:

```sql
-- High-risk transactions by type
SELECT 
    type,
    risk_level,
    COUNT(*) as count,
    AVG(amount) as avg_amount,
    MAX(risk_score) as max_risk
FROM fraud_analytics_dev.enriched_transactions
WHERE dt >= '2026-01-01'
    AND risk_level IN ('high', 'critical')
GROUP BY type, risk_level
ORDER BY count DESC;

-- Risk distribution over time
SELECT 
    dt,
    hr,
    risk_level,
    COUNT(*) as transaction_count
FROM fraud_analytics_dev.enriched_transactions
WHERE dt BETWEEN '2026-01-01' AND '2026-01-07'
GROUP BY dt, hr, risk_level
ORDER BY dt, hr, risk_level;

-- Flagged transactions (potential fraud)
SELECT 
    nameOrig,
    nameDest,
    amount,
    risk_score,
    risk_reasons
FROM fraud_analytics_dev.enriched_transactions
WHERE is_flagged = true
    AND dt = '2026-01-01'
ORDER BY risk_score DESC
LIMIT 100;
```

**Cost:** ~$5 per TB scanned (with partitioning, queries are cheap)

---
## Cleanup

To destroy all dev environment resources:

```bash
make tf-destroy-dev
```

⚠️ **Warning**: This will delete all data in S3 buckets. Export data you want to keep first.

**Verify deletion:**
```bash
# Check S3 buckets are gone
aws s3 ls | grep fraud-analytics-dev

# Check Kinesis streams
aws kinesis list-streams --region ca-west-1

# Check Lambda functions
aws lambda list-functions --region ca-west-1 | grep fraud-analytics
```

---

## Troubleshooting

### Backend Initialization Fails
```bash
# Verify bootstrap is deployed
terraform -chdir=infra/bootstrap output

# Check AWS credentials
aws sts get-caller-identity
```

### Lambda Placeholder Warning
Expected on first deployment. Deploy actual code after infrastructure is ready:
```bash
cd ../../../lambda
# Package and deploy your fraud scoring logic
```

### Redshift Connection Issues
```bash
# Retrieve password from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id $(terraform output -raw redshift_admin_password_secret_arn) \
  --query SecretString --output text | jq -r .password

# Get endpoint
terraform output redshift_workgroup_endpoint
```

### Usage Limit Reached (Redshift)
```bash
# Check current usage
aws redshift-serverless list-usage-limits \
  --region ca-west-1

# If you hit the 50 RPU-hour limit:
# Option 1: Wait for monthly reset
# Option 2: Increase limit temporarily (cost increases)
# Option 3: Disable Redshift and use Athena
```

### High Costs Detected
```bash
# Check Redshift is disabled
terraform output redshift_workgroup_id
# Should return: null

# Verify no orphaned resources
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=Project,Values=fraud-analytics \
  --region ca-west-1
```

---

## Architecture Decisions

### Why Athena by Default?
- **Cost-effective**: Pay only for queries run ($5/TB scanned)
- **No idle costs**: Unlike Redshift, nothing running when not querying
- **Sufficient for portfolio**: Demonstrates partitioning, SQL analytics, Glue integration
- **Easy migration**: Same Glue catalog works with Redshift when enabled

### Why Feature Flags?
- **Portfolio agility**: Build fast, demo, destroy without ongoing costs
- **Flexibility**: Enable/disable components without code changes
- **Cost control**: Usage limits prevent runaway bills
- **Learning tool**: Understand cost impact of each service

### Why No VPC?
- **Simplicity**: Faster deployment, fewer moving parts
- **Cost**: No NAT Gateway (~$32/month), no VPC endpoints
- **Security**: Still encrypted (TLS in transit, KMS at rest)
- **Trade-off**: Acceptable for dev/portfolio, add VPC for production

### Single main.tf
- **Clarity**: All resources visible in one file
- **Portfolio scale**: ~800 lines manageable for small project
- **Trade-off**: Would refactor into modules for production/teams

---

## Next Steps After Infrastructure Deployment

1. **Deploy Lambda Code**: Replace placeholder with actual fraud scoring logic
   ```bash
   cd ../../../lambda
   # Package dependencies, deploy to Lambda function
   ```

2. **Configure Producer**: Point to your Kinesis stream
   ```bash
   cd ../../../producer
   # Update config with stream name from outputs
   ```

3. **Test End-to-End**: Generate sample data, verify enrichment
   ```bash
   # Run producer
   python main.py
   
   # Check S3 for enriched data
   aws s3 ls s3://$(terraform output -raw s3_enriched_bucket_name)/
   
   # Query with Athena (via AWS Console)
   ```

4. **Optional: dbt Setup** (if Redshift enabled)
   ```bash
   cd ../../../dbt
   # Configure profiles.yml with Redshift endpoint
   dbt run
   dbt test
   ```

5. **Capture Portfolio Proof**:
   - Screenshots of Athena queries and results
   - S3 bucket structure with partitions
   - Lambda CloudWatch logs showing fraud scoring
   - Architecture diagram in docs/
   - Optional: QuickSight dashboard (if Redshift enabled)

6. **Destroy to Stop Costs**:
   ```bash
   make tf-destroy-dev
   ```

---

## Portfolio Documentation Checklist

Before destroying:

- [ ] README with architecture explanation
- [ ] Screenshots of Athena query results
- [ ] S3 bucket structure showing partitioning
- [ ] Lambda execution logs with fraud scoring output
- [ ] Optional: Redshift demo (dbt runs, dashboard)
- [ ] Cost analysis (before/after Redshift)
- [ ] Architecture diagram in docs/
- [ ] GitHub repo with clear instructions
