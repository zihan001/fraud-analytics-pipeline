# Fraud Analytics Pipeline

A **hybrid streaming + batch** fraud analytics pipeline on AWS, combining real-time fraud scoring with durable batch analytics.

**Status**: ✅ **Production-Ready** — End-to-end validation complete (see [docs/VALIDATION_RESULTS.md](docs/VALIDATION_RESULTS.md))

## Architecture

```
Producer → Kinesis Data Stream ──┬→ Firehose → S3 (raw) → Athena/Redshift (batch analytics)
                                 │
                                 └→ Lambda ──┬→ S3 (enriched) → Redshift (batch analytics)
                                             ├→ DynamoDB (live metrics/state for dashboard)
                                             └→ SQS DLQ (invalid events)
```

**Validated Components**:
- ✅ Producer → Kinesis (event envelope pattern, 100% success rate)
- ✅ Lambda fraud scoring (100% validation pass, zero DLQ failures)
- ✅ DynamoDB metrics + latest state (sub-second writes)
- ✅ S3 enriched (individual JSON files with fraud_analysis)
- ✅ Firehose → S3 raw (GZIP compressed, dynamic partitioning: dt/hr)
- ✅ CloudWatch monitoring (all alarms in OK state)

### Key Components

**Streaming Layer:**
- **Kinesis Data Stream**: Central event bus for all transactions
- **Kinesis Firehose**: Durable S3 ingestion with file buffering (32MB/180s) and dynamic partitioning
- **Lambda Consumer**: Real-time fraud scoring, enrichment, and DynamoDB updates
- **SQS DLQ**: Parking lot for invalid events with error context

**Storage Layer:**
- **S3 Raw Zone**: Buffered files from Firehose (dt=YYYY-MM-DD/hr=HH partitioning)
- **S3 Enriched Zone**: Lambda-processed events with fraud analysis
- **DynamoDB**: Live metrics (time-window counters) and latest entity state

**Analytics Layer:**
- **Batch**: S3 → Athena/Redshift → dbt transforms → QuickSight
- **Live**: DynamoDB → Dashboard (real-time metrics and entity state)

## Structure
- `infra/` — Infrastructure as code (Terraform)
  - `bootstrap/` — Backend state storage (run once)
  - `envs/dev/` — Dev environment resources
- `producer/` — CSV to Kinesis producer (PaySim replay)
- `lambda/` — Fraud scoring and DynamoDB updates
- `dbt/` — dbt models and tests for Redshift
- `docs/` — Architecture diagrams and documentation
- `tests/` — Integration test checklist

## Quick Start

### 1. Infrastructure Setup

#### Bootstrap (one-time)
```bash
cd infra/bootstrap
terraform init
terraform apply
```

#### Deploy Dev Environment
```bash
cd infra/envs/dev
terraform init
make tf-plan-dev
make tf-apply-dev
```

This provisions:
- Kinesis stream (1 shard, 24h retention)
- Kinesis Firehose with S3 delivery
- Lambda function with Kinesis trigger
- DynamoDB tables (metrics, latest_state)
- S3 buckets (raw, enriched)
- SQS DLQ
- CloudWatch alarms

### 2. Deploy Lambda Code

```bash
# Run tests first
make lambda-test

# Package and deploy
make lambda-deploy
```

### 3. Run Producer

```bash
cd producer
pip install -r requirements.txt
python main.py --rate 50 --max-events 1000
```

**Producer publishes events to Kinesis. The pipeline then:**
1. Firehose buffers events → writes to S3 raw zone (3-5 min)
2. Lambda processes in real-time → writes to S3 enriched + DynamoDB (<30 sec)

### 4. Validate Integration

Follow the comprehensive checklist in [`tests/integration_checklist.md`](tests/integration_checklist.md):
- Verify S3 raw data (Firehose)
- Verify S3 enriched data (Lambda)
- Query DynamoDB metrics and latest state
- Check DLQ for invalid events
- Monitor CloudWatch logs and alarms

## Development Workflows

```bash
# Format code
make fmt

# Lint code
make lint

# Run unit tests
make test

# Run Lambda tests specifically
make lambda-test

# Deploy Lambda after changes
make lambda-deploy

# Terraform operations
make tf-plan-dev
make tf-apply-dev
make tf-destroy-dev
```

## Event Contract

**Producer Events** (JSON):
```json
{
  "event_id": "evt_12345",
  "event_type": "transaction",
  "event_ts": "2026-01-01T12:00:00Z",
  "source": "paysim/v1.0",
  "payload": {
    "type": "PAYMENT",
    "amount": 1000.50,
    "nameOrig": "C123456",
    "nameDest": "M789012",
    "isFraud": 0
  }
}
```

**Enriched Events** (Lambda output):
```json
{
  "event_id": "evt_12345",
  "event_type": "transaction",
  "event_ts": "2026-01-01T12:00:00Z",
  "source": "paysim/v1.0",
  "payload": { ... },
  "ingested_ts": "2026-01-01T12:00:05Z",
  "schema_version": "1.0",
  "kinesis_metadata": {
    "partitionKey": "C123456",
    "sequenceNumber": "49624...",
    "approxArrivalTimestamp": 1704110400.0
  },
  "fraud_analysis": {
    "risk_score": 65,
    "risk_level": "MEDIUM",
    "is_flagged": true,
    "risk_reasons": ["high_amount", "round_amount"],
    "scored_at": "2026-01-01T12:00:05Z"
  }
}
```

## DynamoDB Schema

### Metrics Table (Time-Series Counters)
```
PK: metric#{metric_name}       (e.g., "metric#purchases")
SK: window#{YYYY-MM-DDTHH:MM}  (e.g., "window#2026-01-01T12:30")
Attributes:
  - count: Number (atomic increment)
  - updated_ts: String (ISO8601)
```

**Supported Metrics:**
- `purchases`: Transaction count
- `revenue_cents`: Total revenue (cents)
- `page_views`: Page view count
- `errors`: Error count
- `heartbeats`: Device heartbeat count

### Latest State Table (Entity State)
```
PK: {entity_type}#{entity_id}  (e.g., "user#C123456")
Attributes:
  - last_event_ts: String (ISO8601)
  - updated_ts: String (ISO8601)
  - state: Map (event-specific fields)
```

**Example State:**
```json
{
  "pk": "user#C123456",
  "last_event_ts": "2026-01-01T12:00:00Z",
  "updated_ts": "2026-01-01T12:00:05Z",
  "state": {
    "last_purchase_cents": 100050,
    "last_purchase_ts": "2026-01-01T12:00:00Z",
    "transaction_type": "PAYMENT"
  }
}
```

## Fraud Scoring Rules

**Risk Score (0-100):**
- High amount (>$5000): +30 points
- Round amount (e.g., $5000.00): +20 points
- Upstream fraud flag: +50 points
- High-risk type (CASH_OUT, TRANSFER): +15 points

**Risk Level:**
- 0-39: LOW (not flagged)
- 40-69: MEDIUM (flagged)
- 70-100: HIGH (flagged)

## Monitoring

**CloudWatch Alarms:**
- Lambda errors > 0
- Lambda throttles
- Kinesis iterator age too high
- DLQ messages > 0
- Firehose delivery failures
- DynamoDB throttling

**Structured Logs:**
- JSON format with correlation fields
- Metrics: `total_records`, `success`, `dlq_count`, `transient_failures`
- Traceability: `event_id`, `event_type`, `sequence_number`

## Cost Optimization

**Current Configuration (Dev):**
- Kinesis: 1 shard (~$15/month)
- Lambda: Pay per invocation (batch processing)
- DynamoDB: On-demand billing (scales with load)
- S3: Storage + requests (lifecycle policies reduce costs)
- Firehose: Data ingestion volume

**Feature Flags:**
Set in `infra/envs/dev/terraform.tfvars`:
- `enable_redshift = false` — Disable expensive Redshift (use Athena)
- `enable_cloudwatch_alarms = false` — Disable alarms for testing

## Testing

### Test Infrastructure

**Install Test Dependencies:**
```bash
pip install -r requirements-test.txt
```

### Running Tests

**All Tests:**
```bash
make test
# or
pytest -v
```

**With Coverage Report:**
```bash
pytest --cov=producer --cov=lambda --cov-report=term --cov-report=html
```

**Component-Specific Tests:**
```bash
# Lambda tests
pytest lambda/test_handler.py -v
# or
make lambda-test

# Producer tests
pytest tests/producer/ -v
```

**By Test Marker:**
```bash
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests only
pytest -m "not slow"     # Skip slow tests
```

### Test Categories

**Unit Tests** (Fast, no AWS required):
- `lambda/test_handler.py` — Lambda fraud scoring logic (15 tests)
- `tests/producer/` — Producer component tests (CSV, Kinesis client, config)

**Integration Tests** (Requires AWS):
- See [`tests/integration_checklist.md`](tests/integration_checklist.md) for manual validation
- Automated integration tests in `tests/integration/` (upcoming)

### Testing Philosophy

- **Unit tests**: Fast, mocked AWS services (boto3 mocked with moto)
- **Integration tests**: Manual validation checklist (comprehensive, real AWS services)
- **Coverage reporting**: No threshold enforcement, report-only for visibility
- **CI/CD**: All unit tests run automatically on PR and merge

## Contributing

See [REQUIREMENTS.md](REQUIREMENTS.md) for project requirements and architecture details. PRs and issues welcome!

## License

MIT
