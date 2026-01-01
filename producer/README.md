# Fraud Analytics Producer

Python application that replays PaySim transaction data to AWS Kinesis to simulate live transaction streaming for fraud detection.

## Overview

The producer reads the PaySim CSV dataset row-by-row and emits JSON-formatted transaction events to a Kinesis stream at a configurable rate (5–100 events/sec). This enables real-time fraud detection by simulating a live transaction feed from historical data.

## Architecture

```
PaySim CSV → CSV Reader → Rate Limiter → Kinesis Publisher → Kinesis Stream
                                                                    ↓
                                                              Lambda Consumer
```

## Components

- **`main.py`**: CLI entry point with argument parsing and orchestration
- **`csv_reader.py`**: PaySim CSV parser with type conversion
- **`kinesis_client.py`**: Boto3 wrapper for Kinesis publishing with retry logic
- **`config.py`**: Configuration management (env vars, CLI args, defaults)

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure
cp .env.example .env
# Edit .env with your settings
```

## Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
AWS_REGION=us-east-1                              # AWS region
KINESIS_STREAM_NAME=fraud-analytics-dev-transactions  # Kinesis stream name
EVENTS_PER_SECOND=10                              # Event rate (5-100)
CSV_PATH=PS_20174392719_1491204439457_log.csv     # PaySim CSV path
```

### Get Kinesis Stream Name

If you deployed infrastructure with Terraform:

```bash
cd ../infra/envs/dev
terraform output kinesis_stream_name
```

## Usage

### Basic Usage

```bash
# Run with default settings (from .env)
python main.py

# Run with CLI arguments (override .env)
python main.py \
  --stream-name fraud-analytics-dev-transactions \
  --region us-east-1 \
  --rate 20 \
  --csv ../PS_20174392719_1491204439457_log.csv
```

### Options

```bash
python main.py --help

Options:
  --stream-name TEXT         Kinesis stream name
  --region TEXT              AWS region
  --rate EVENTS_PER_SEC      Event rate (5-100 events/sec)
  --csv PATH                 Path to PaySim CSV file
  --max-events N             Maximum events to send (default: all)
  -v, --verbose              Enable debug logging
```

### Examples

```bash
# Test with limited events
python main.py --max-events 100 --rate 5

# High throughput replay
python main.py --rate 100

# Verbose logging for debugging
python main.py --verbose --max-events 10
```

## Data Flow

### Input (CSV)
```csv
step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,nameDest,oldbalanceDest,newbalanceDest,isFraud,isFlaggedFraud
1,PAYMENT,9839.64,C1231006815,170136.00,160296.36,M1979787155,0.00,0.00,0,0
```

### Output (JSON to Kinesis)
```json
{
  "step": 1,
  "type": "PAYMENT",
  "amount": 9839.64,
  "nameOrig": "C1231006815",
  "oldbalanceOrg": 170136.0,
  "newbalanceOrig": 160296.36,
  "nameDest": "M1979787155",
  "oldbalanceDest": 0.0,
  "newbalanceDest": 0.0,
  "isFraud": 0,
  "isFlaggedFraud": 0
}
```

## Features

- ✅ **Rate limiting**: Configurable 5–100 events/sec per REQUIREMENTS.md §5.1
- ✅ **Partition key strategy**: Uses `nameOrig` for even distribution across shards
- ✅ **Retry logic**: Exponential backoff for Kinesis throttling
- ✅ **Progress tracking**: Logs every 1,000 events and 10,000 CSV rows
- ✅ **Metrics**: Success rate, average latency, throughput
- ✅ **Error handling**: Graceful shutdown, detailed error logging
- ✅ **Type safety**: Proper CSV-to-JSON type conversion

## Monitoring

The producer emits the following logs and metrics:

- **Progress logs**: Every 1,000 events published
- **CSV read progress**: Every 10,000 rows read
- **Final summary**: Runtime, events processed, success rate, latency, throughput
- **Errors**: Throttling, connection errors, retry attempts

Example output:
```
2026-01-01 12:00:00 - main - INFO - Fraud Analytics Producer - Starting
2026-01-01 12:00:00 - config - INFO - Configuration: ProducerConfig(...)
2026-01-01 12:00:01 - kinesis_client - INFO - Stream fraud-analytics-dev-transactions is active with 1 shard(s)
2026-01-01 12:01:00 - kinesis_client - INFO - Published 1,000 events (avg latency: 45.23ms)
2026-01-01 12:02:00 - csv_reader - INFO - Read 10,000 transactions
2026-01-01 12:05:00 - main - INFO - Fraud Analytics Producer - Summary
2026-01-01 12:05:00 - main - INFO - Events sent: 5,000
2026-01-01 12:05:00 - main - INFO - Success rate: 99.98%
```

## Troubleshooting

### Stream Not Found
```bash
# Verify stream exists
aws kinesis describe-stream --stream-name fraud-analytics-dev-transactions --region us-east-1
```

### Permission Errors
Ensure your AWS credentials have the following permissions:
- `kinesis:PutRecord`
- `kinesis:DescribeStream`

### Throttling
If you see `ProvisionedThroughputExceededException`:
- Reduce `--rate` value
- Increase Kinesis shard count in Terraform

### CSV Not Found
Ensure the CSV file path is correct (relative to working directory):
```bash
ls -lh PS_20174392719_1491204439457_log.csv
```

## Next Steps

After running the producer, verify data flow:

```bash
# Check S3 raw bucket for incoming data
aws s3 ls s3://$(cd ../infra/envs/dev && terraform output -raw s3_raw_bucket_name)/ --recursive

# Check S3 enriched bucket for Lambda-processed data
aws s3 ls s3://$(cd ../infra/envs/dev && terraform output -raw s3_enriched_bucket_name)/ --recursive

# Check CloudWatch logs for Lambda execution
aws logs tail /aws/lambda/fraud-analytics-dev-processor --follow
```

## References

- [REQUIREMENTS.md](../REQUIREMENTS.md) §5.1 - Producer specifications
- [infra/envs/dev/](../infra/envs/dev/) - Infrastructure configuration
- [lambda/](../lambda/) - Lambda consumer for fraud scoring
