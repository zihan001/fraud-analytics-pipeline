# Integration Test Checklist

Comprehensive testing checklist for the Kinesis hybrid streaming + batch pipeline.

## Prerequisites

- [ ] Infrastructure deployed via Terraform (`make tf-apply`)
- [ ] Lambda function deployed with actual handler code
- [ ] CloudWatch alarms configured and enabled
- [ ] Producer configured with correct Kinesis stream name

## 1. Producer → Kinesis Stream

### Test: Event Publication
```bash
# Run producer to publish 1000 events
cd producer
python main.py --rate 50 --max-events 1000
```

**Expected Results:**
- [ ] Producer reports 1000 events sent successfully
- [ ] Average latency < 100ms
- [ ] No errors or retries in producer logs
- [ ] Kinesis stream metrics show incoming records (CloudWatch → Kinesis → IncomingRecords)

**Validation Commands:**
```bash
# Check Kinesis stream metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Kinesis \
  --metric-name IncomingRecords \
  --dimensions Name=StreamName,Value=fraud-analytics-dev-transactions \
  --statistics Sum \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300
```

## 2. Firehose → S3 (Batch Layer)

### Test: S3 Raw Data Delivery
**Wait Time:** 3-5 minutes (for buffering: 180s + processing)

**Expected Results:**
- [ ] Files appear in S3 raw bucket under `raw/dt=YYYY-MM-DD/hr=HH/`
- [ ] File sizes are reasonable (target: 16-64MB after GZIP, ~32MB buffer)
- [ ] File format is GZIP-compressed JSON Lines
- [ ] Each line is valid JSON with newline delimiter
- [ ] Partitions match event timestamps (not ingestion time)

**Validation Commands:**
```bash
# List S3 objects in raw zone
aws s3 ls s3://fraud-analytics-dev-raw-<account-id>/raw/ --recursive | head -20

# Download and inspect a file
aws s3 cp s3://fraud-analytics-dev-raw-<account-id>/raw/dt=2026-01-01/hr=12/<file> - | gunzip | head -5

# Count records in a file
aws s3 cp s3://fraud-analytics-dev-raw-<account-id>/raw/dt=2026-01-01/hr=12/<file> - | gunzip | wc -l

# Validate JSON format
aws s3 cp s3://fraud-analytics-dev-raw-<account-id>/raw/dt=2026-01-01/hr=12/<file> - | gunzip | jq -c '.' | head -1
```

### Test: Firehose Metrics
**Expected Results:**
- [ ] `DeliveryToS3.Success` metric > 0
- [ ] `DeliveryToS3.DataFreshness` < 900 seconds
- [ ] No errors in Firehose CloudWatch logs

**Validation Commands:**
```bash
# Check Firehose delivery metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Firehose \
  --metric-name DeliveryToS3.Success \
  --dimensions Name=DeliveryStreamName,Value=fraud-analytics-dev-transactions \
  --statistics Sum \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300

# Check Firehose logs
aws logs tail /aws/kinesisfirehose/fraud-analytics-dev-transactions --follow --format short
```

## 3. Lambda → DynamoDB (Speed Layer)

### Test: DynamoDB Metrics Updates
**Expected Results:**
- [ ] `metrics` table has records with PK `metric#purchases` and SK `window#YYYY-MM-DDTHH:MM`
- [ ] Counter values match approximately (allow for some deduplication/sampling)
- [ ] `updated_ts` is recent (within last few minutes)

**Validation Commands:**
```bash
# Query metrics table for recent windows
aws dynamodb query \
  --table-name fraud-analytics-dev-metrics \
  --key-condition-expression "pk = :pk AND begins_with(sk, :sk_prefix)" \
  --expression-attribute-values '{
    ":pk": {"S": "metric#purchases"},
    ":sk_prefix": {"S": "window#2026-01-01T12"}
  }' \
  --limit 10

# Get total count for a specific window
aws dynamodb get-item \
  --table-name fraud-analytics-dev-metrics \
  --key '{
    "pk": {"S": "metric#purchases"},
    "sk": {"S": "window#2026-01-01T12:30"}
  }'
```

### Test: DynamoDB Latest State Updates
**Expected Results:**
- [ ] `latest_state` table has records for users/devices from events
- [ ] PK format: `user#C123456` or `device#dev_001`
- [ ] `state` attribute contains event-specific fields
- [ ] `last_event_ts` matches most recent event

**Validation Commands:**
```bash
# Get latest state for a user
aws dynamodb get-item \
  --table-name fraud-analytics-dev-latest-state \
  --key '{
    "pk": {"S": "user#C123456"}
  }'

# Scan for recent updates (limit for cost)
aws dynamodb scan \
  --table-name fraud-analytics-dev-latest-state \
  --limit 10
```

## 4. Lambda → S3 Enriched (Speed Layer Persistence)

### Test: S3 Enriched Data
**Expected Results:**
- [ ] Files appear in S3 enriched bucket under `enriched/dt=YYYY-MM-DD/hr=HH/`
- [ ] Each file is a single JSON object (not JSON Lines)
- [ ] Files contain `fraud_analysis` field with `risk_score`, `risk_level`, `is_flagged`
- [ ] Files contain `kinesis_metadata` and `ingested_ts`

**Validation Commands:**
```bash
# List enriched files
aws s3 ls s3://fraud-analytics-dev-enriched-<account-id>/enriched/ --recursive | head -20

# Inspect an enriched file
aws s3 cp s3://fraud-analytics-dev-enriched-<account-id>/enriched/dt=2026-01-01/hr=12/<event-id>.json - | jq '.'

# Verify fraud_analysis presence
aws s3 cp s3://fraud-analytics-dev-enriched-<account-id>/enriched/dt=2026-01-01/hr=12/<event-id>.json - | jq '.fraud_analysis'
```

## 5. DLQ → SQS (Error Handling)

### Test: Invalid Event Handling
**Test Setup:**
1. Publish an invalid JSON event:
   ```bash
   aws kinesis put-record \
     --stream-name fraud-analytics-dev-transactions \
     --partition-key test-invalid \
     --data "not-valid-json"
   ```

2. Publish event with missing fields:
   ```bash
   echo '{"event_id":"test","bad":"data"}' | base64 | xargs -I {} aws kinesis put-record \
     --stream-name fraud-analytics-dev-transactions \
     --partition-key test-validation \
     --data {}
   ```

**Expected Results:**
- [ ] DLQ receives 2 messages
- [ ] DLQ messages contain `error_type`, `error_message`, `kinesis` metadata
- [ ] Lambda does NOT retry these records (no `batchItemFailures` for them)
- [ ] CloudWatch alarm for DLQ messages triggers

**Validation Commands:**
```bash
# Check DLQ message count
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name fraud-analytics-dev-lambda-dlq --query QueueUrl --output text) \
  --attribute-names ApproximateNumberOfMessages

# Receive and inspect a DLQ message
aws sqs receive-message \
  --queue-url $(aws sqs get-queue-url --queue-name fraud-analytics-dev-lambda-dlq --query QueueUrl --output text) \
  --max-number-of-messages 1 | jq '.Messages[0].Body | fromjson'
```

## 6. CloudWatch Logs and Metrics

### Test: Lambda Structured Logging
**Expected Results:**
- [ ] Lambda logs are in JSON format
- [ ] Logs contain `total_records`, `success`, `dlq_count`, `transient_failures`
- [ ] Logs include `event_id`, `event_type`, `sequence_number` for traceability
- [ ] No ERROR level logs for valid events

**Validation Commands:**
```bash
# Tail Lambda logs
aws logs tail /aws/lambda/fraud-analytics-dev-fraud-scorer --follow --format short

# Search for batch processing summaries
aws logs filter-log-events \
  --log-group-name /aws/lambda/fraud-analytics-dev-fraud-scorer \
  --filter-pattern "\"Batch processing complete\"" \
  --max-items 5

# Check for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/fraud-analytics-dev-fraud-scorer \
  --filter-pattern "ERROR" \
  --max-items 10
```

### Test: Lambda Metrics
**Expected Results:**
- [ ] Lambda `Invocations` > 0
- [ ] Lambda `Duration` < timeout (300s)
- [ ] Lambda `Errors` = 0 (for valid events)
- [ ] Lambda `ConcurrentExecutions` within reserved capacity

**Validation Commands:**
```bash
# Check Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=fraud-analytics-dev-fraud-scorer \
  --statistics Sum \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300
```

## 7. CloudWatch Alarms

### Test: Alarm States
**Expected Results:**
- [ ] All alarms are in `OK` state after successful test run
- [ ] Alarms are configured with SNS topic
- [ ] DLQ alarm triggered when invalid events sent (expected behavior)

**Validation Commands:**
```bash
# List all alarms
aws cloudwatch describe-alarms \
  --alarm-name-prefix fraud-analytics-dev

# Check specific alarm state
aws cloudwatch describe-alarms \
  --alarm-names fraud-analytics-dev-lambda-errors fraud-analytics-dev-firehose-delivery-failures fraud-analytics-dev-dynamodb-throttles
```

## 8. End-to-End Data Flow

### Test: Complete Pipeline
**Expected Results:**
1. [ ] Event published to Kinesis appears in both:
   - Raw S3 (via Firehose) within 3-5 minutes
   - Enriched S3 (via Lambda) within 10-30 seconds
   - DynamoDB (via Lambda) within 10-30 seconds

2. [ ] Event data is consistent across layers:
   - Raw: Original event unchanged
   - Enriched: Contains fraud_analysis + metadata
   - DynamoDB: Counter incremented, state updated

**Validation:**
Pick a specific `event_id` from producer logs and trace through:
```bash
EVENT_ID="evt_12345"

# 1. Check raw S3 (wait for Firehose)
aws s3 cp s3://fraud-analytics-dev-raw-<account-id>/raw/dt=2026-01-01/hr=12/<file> - | gunzip | jq ". | select(.event_id == \"$EVENT_ID\")"

# 2. Check enriched S3
aws s3 cp s3://fraud-analytics-dev-enriched-<account-id>/enriched/dt=2026-01-01/hr=12/${EVENT_ID}.json - | jq '.'

# 3. Check DynamoDB metrics (aggregate, not per-event)
aws dynamodb query --table-name fraud-analytics-dev-metrics \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk": {"S": "metric#purchases"}}' \
  --limit 5
```

## 9. Performance and Scale

### Test: Throughput
**Test Setup:**
```bash
# Publish at max rate
cd producer
python main.py --rate 100 --max-events 10000
```

**Expected Results:**
- [ ] Producer sustains 100 events/sec
- [ ] Lambda processes batches without throttling
- [ ] DynamoDB writes succeed (on-demand billing scales automatically)
- [ ] Kinesis IteratorAge remains low (< 10000ms)
- [ ] No alarm triggers

**Validation:**
Monitor CloudWatch dashboard for:
- Kinesis IncomingRecords rate
- Lambda Duration percentiles (p50, p95, p99)
- DynamoDB ConsumedWriteCapacityUnits
- Firehose buffer fullness

## 10. Cost Validation

### Test: Resource Usage
**Expected Results:**
- [ ] DynamoDB on-demand billing within budget
- [ ] S3 storage reasonable for retention policy
- [ ] Lambda invocations charged per batch (not per record)
- [ ] Kinesis shard hours = 1 shard × hours

**Validation Commands:**
```bash
# Check S3 bucket size
aws s3 ls s3://fraud-analytics-dev-raw-<account-id> --recursive --summarize | grep "Total Size"

# Check DynamoDB table size
aws dynamodb describe-table --table-name fraud-analytics-dev-metrics --query 'Table.TableSizeBytes'

# Estimate Lambda costs (invocations × duration)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=fraud-analytics-dev-fraud-scorer \
  --statistics Sum \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400
```

## Summary Checklist

After completing all tests:
- [ ] Producer successfully publishes events to Kinesis
- [ ] Firehose delivers buffered data to S3 raw zone
- [ ] Lambda processes events and writes to S3 enriched + DynamoDB
- [ ] DLQ captures invalid events correctly
- [ ] CloudWatch logs show structured JSON with metrics
- [ ] CloudWatch alarms are green (OK state)
- [ ] Data is consistent across batch and speed layers
- [ ] No errors or throttling under load
- [ ] Costs are within expected range

## Cleanup

After testing:
```bash
# Stop producer
# Ctrl+C in producer terminal

# Optionally purge DLQ
aws sqs purge-queue --queue-url $(aws sqs get-queue-url --queue-name fraud-analytics-dev-lambda-dlq --query QueueUrl --output text)

# Optionally destroy infrastructure
cd infra/envs/dev
terraform destroy
```
