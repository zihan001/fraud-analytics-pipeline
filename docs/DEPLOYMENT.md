# Deployment Guide

Step-by-step guide for deploying the Kinesis hybrid streaming + batch pipeline.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.0
- Python >= 3.11
- Make
- Git

## Architecture Deployment

### Step 1: Bootstrap Infrastructure (One-Time Setup)

This creates the S3 backend for Terraform state storage.

```bash
cd infra/bootstrap
terraform init
terraform plan
terraform apply
```

**Outputs to save:**
- `terraform_state_bucket`
- `terraform_state_lock_table`

### Step 2: Configure Dev Environment

```bash
cd infra/envs/dev
```

**Option A: Copy and customize terraform.tfvars**
```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
aws_region = "us-west-2"  # Your preferred region
project_name = "fraud-analytics"
environment = "dev"

# Feature flags (cost control)
enable_redshift = false  # Set true only for demo/production
enable_cloudwatch_alarms = true
enable_kinesis = true
enable_lambda = true

# Kinesis configuration
kinesis_shard_count = 1
kinesis_retention_hours = 24

# Lambda configuration
lambda_batch_size = 100
lambda_timeout = 300
lambda_memory_size = 512

# Firehose buffering
firehose_buffer_size_mb = 32
firehose_buffer_interval_sec = 180

# Monitoring
cloudwatch_log_retention_days = 7
alarm_email = "your-email@example.com"  # For CloudWatch alarms
```

**Option B: Use environment variables**
```bash
export TF_VAR_aws_region="us-west-2"
export TF_VAR_alarm_email="your-email@example.com"
# ... other variables
```

### Step 3: Deploy Dev Infrastructure

```bash
# Initialize Terraform with backend config
terraform init

# Review the deployment plan
make tf-plan-dev

# Deploy resources
make tf-apply-dev
```

**This provisions:**
- ✅ Kinesis Data Stream (1 shard, 24h retention)
- ✅ Kinesis Firehose (S3 delivery with buffering)
- ✅ Lambda function (with placeholder code)
- ✅ DynamoDB tables (metrics, latest_state)
- ✅ S3 buckets (raw, enriched with encryption)
- ✅ SQS DLQ
- ✅ CloudWatch log groups and alarms
- ✅ IAM roles and policies

**Expected time:** 3-5 minutes

**Capture outputs:**
```bash
terraform output > outputs.txt
```

Key outputs to note:
- `kinesis_stream_name`
- `lambda_function_name`
- `dynamodb_metrics_table_name`
- `dynamodb_latest_state_table_name`
- `s3_raw_bucket_name`
- `s3_enriched_bucket_name`

### Step 4: Configure CloudWatch Alarms (Optional)

If you set `alarm_email` in `terraform.tfvars`, you'll receive an SNS subscription confirmation email.

1. Check your email inbox
2. Click "Confirm subscription" link
3. Verify alarms are active:
   ```bash
   aws cloudwatch describe-alarms --alarm-name-prefix fraud-analytics-dev
   ```

## Lambda Deployment

### Step 5: Run Lambda Tests

```bash
cd ../../..  # Back to repo root
make lambda-test
```

**Expected output:**
```
==================== test session starts ====================
lambda/test_handler.py::TestValidation::test_valid_event PASSED
lambda/test_handler.py::TestFraudScoring::test_low_risk_transaction PASSED
...
==================== 15 passed in 2.34s ====================
```

### Step 6: Deploy Lambda Code

```bash
make lambda-deploy
```

**This:**
1. Creates `lambda/package/` with dependencies
2. Packages `handler.py` with dependencies into `lambda.zip`
3. Uploads to Lambda function via AWS CLI

**Verify deployment:**
```bash
aws lambda get-function --function-name fraud-analytics-dev-fraud-scorer
```

**Test Lambda invocation (optional):**
```bash
# Create test event file
cat > test-event.json <<EOF
{
  "Records": [{
    "kinesis": {
      "partitionKey": "test-key",
      "sequenceNumber": "12345",
      "data": "$(echo '{"event_id":"test","event_type":"transaction","event_ts":"2026-01-01T12:00:00Z","payload":{"amount":100,"type":"PAYMENT","isFraud":0}}' | base64)",
      "approximateArrivalTimestamp": 1704110400.0
    }
  }]
}
EOF

# Invoke Lambda
aws lambda invoke \
  --function-name fraud-analytics-dev-fraud-scorer \
  --payload file://test-event.json \
  response.json

# Check response
cat response.json
```

## Producer Setup

### Step 7: Configure Producer

```bash
cd producer
pip install -r requirements.txt
```

**Create `.env` file:**
```bash
KINESIS_STREAM_NAME=fraud-analytics-dev-transactions
AWS_REGION=us-west-2
EVENT_RATE=50
MAX_EVENTS=1000
CSV_PATH=../PS_20174392719_1491204439457_log.csv
```

Or use the stream name from Terraform outputs:
```bash
STREAM_NAME=$(cd ../infra/envs/dev && terraform output -raw kinesis_stream_name)
echo "KINESIS_STREAM_NAME=$STREAM_NAME" > .env
```

### Step 8: Run Producer

```bash
python main.py
```

**Expected output:**
```
2026-01-01 12:00:00 - INFO - Starting producer
2026-01-01 12:00:00 - INFO - Kinesis stream: fraud-analytics-dev-transactions
2026-01-01 12:00:00 - INFO - Publishing at 50 events/sec
2026-01-01 12:00:05 - INFO - Progress: 250/1000 events sent (25.0%)
...
2026-01-01 12:00:20 - INFO - Producer complete. Total: 1000, Success: 1000, Failed: 0
2026-01-01 12:00:20 - INFO - Average latency: 45.2ms
```

## Validation

### Step 9: Verify Data Flow

Follow the comprehensive integration test checklist:
```bash
cat tests/integration_checklist.md
```

**Quick validation:**

1. **Check Firehose S3 delivery (wait 3-5 minutes):**
   ```bash
   aws s3 ls s3://$(cd infra/envs/dev && terraform output -raw s3_raw_bucket_name)/raw/ --recursive
   ```

2. **Check Lambda S3 enriched output (<30 seconds):**
   ```bash
   aws s3 ls s3://$(cd infra/envs/dev && terraform output -raw s3_enriched_bucket_name)/enriched/ --recursive
   ```

3. **Query DynamoDB metrics:**
   ```bash
   aws dynamodb query \
     --table-name fraud-analytics-dev-metrics \
     --key-condition-expression "pk = :pk" \
     --expression-attribute-values '{":pk": {"S": "metric#purchases"}}' \
     --limit 10
   ```

4. **Check Lambda logs:**
   ```bash
   aws logs tail /aws/lambda/fraud-analytics-dev-fraud-scorer --follow --format short
   ```

5. **Check CloudWatch alarms:**
   ```bash
   aws cloudwatch describe-alarms \
     --alarm-names \
       fraud-analytics-dev-lambda-errors \
       fraud-analytics-dev-firehose-delivery-failures \
       fraud-analytics-dev-dynamodb-throttles
   ```

## Monitoring and Operations

### View Live Metrics

**Lambda metrics:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=fraud-analytics-dev-fraud-scorer \
  --statistics Sum \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300
```

**Kinesis metrics:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Kinesis \
  --metric-name IncomingRecords \
  --dimensions Name=StreamName,Value=fraud-analytics-dev-transactions \
  --statistics Sum \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300
```

**DynamoDB metrics:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --dimensions Name=TableName,Value=fraud-analytics-dev-metrics \
  --statistics Sum \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300
```

### Troubleshooting

**Lambda errors:**
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fraud-analytics-dev-fraud-scorer \
  --filter-pattern "ERROR"
```

**DLQ messages:**
```bash
aws sqs receive-message \
  --queue-url $(cd infra/envs/dev && terraform output -raw lambda_dlq_url) \
  --max-number-of-messages 10
```

**Firehose errors:**
```bash
aws logs tail /aws/kinesisfirehose/fraud-analytics-dev-transactions --follow
```

## Updating the Pipeline

### Update Lambda Code
```bash
# Make changes to lambda/handler.py
make lambda-test
make lambda-deploy
```

### Update Infrastructure
```bash
cd infra/envs/dev
# Edit .tf files
terraform plan
terraform apply
```

### Update Firehose Buffering
Edit `terraform.tfvars`:
```hcl
firehose_buffer_size_mb = 64  # Increase buffer size
firehose_buffer_interval_sec = 300  # Increase interval
```

Then:
```bash
make tf-apply-dev
```

## Cost Management

### Monitor Costs
```bash
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '30 days ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://<(echo '{
    "Tags": {
      "Key": "Environment",
      "Values": ["dev"]
    }
  }')
```

### Cost-Saving Tips

1. **Disable Redshift for dev:**
   ```hcl
   enable_redshift = false  # in terraform.tfvars
   ```

2. **Reduce log retention:**
   ```hcl
   cloudwatch_log_retention_days = 3  # Default is 7
   ```

3. **Enable S3 lifecycle policies** (already configured):
   - Raw data expires after 7 days
   - Enriched data transitions to Glacier after 30 days

4. **Scale down for testing:**
   ```hcl
   kinesis_shard_count = 1
   lambda_memory_size = 256  # Reduce from 512
   ```

## Cleanup

### Temporary Cleanup (Keep Infrastructure)
```bash
# Purge DLQ
aws sqs purge-queue --queue-url $(cd infra/envs/dev && terraform output -raw lambda_dlq_url)

# Delete S3 data (keeps buckets)
aws s3 rm s3://$(cd infra/envs/dev && terraform output -raw s3_raw_bucket_name)/raw/ --recursive
aws s3 rm s3://$(cd infra/envs/dev && terraform output -raw s3_enriched_bucket_name)/enriched/ --recursive
```

### Full Teardown
```bash
cd infra/envs/dev
make tf-destroy-dev
```

**Note:** Terraform will prompt for confirmation. Type `yes` to proceed.

**If destroy fails due to S3 buckets:**
```bash
# Empty buckets first
aws s3 rm s3://$(terraform output -raw s3_raw_bucket_name) --recursive
aws s3 rm s3://$(terraform output -raw s3_enriched_bucket_name) --recursive

# Retry destroy
make tf-destroy-dev
```

## Next Steps

1. **Build dbt models** for Redshift analytics
2. **Set up QuickSight dashboard** with DynamoDB data source for live metrics
3. **Implement CI/CD pipeline** for automated deployments
4. **Add more event types** and fraud detection rules
5. **Scale to production** with multi-shard Kinesis and reserved Lambda concurrency

## Support

For issues or questions:
- Check [REQUIREMENTS.md](../REQUIREMENTS.md) for architecture details
- Review [tests/integration_checklist.md](../tests/integration_checklist.md)
- Check CloudWatch logs for debugging
- Open an issue in the repository
