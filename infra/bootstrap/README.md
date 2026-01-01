# Bootstrap Infrastructure

This directory contains Terraform configuration for bootstrapping the CI/CD and remote state infrastructure for the fraud analytics pipeline.

## What This Creates

1. **S3 State Bucket**
   - Stores Terraform remote state for all environments
   - Versioning enabled for state history
   - SSE-KMS encryption for security
   - Block public access enabled
   - Bucket policies enforce encryption and TLS-only access

2. **DynamoDB Lock Table**
   - Prevents concurrent Terraform operations
   - Pay-per-request billing
   - Partition key: `LockID`

3. **KMS Key**
   - Encrypts Terraform state in S3
   - Key rotation enabled
   - Policies allow admin and GitHub Actions access

4. **GitHub Actions OIDC Setup**
   - OIDC provider for GitHub Actions authentication
   - IAM role with trust policy for your repo/branch
   - Broad permissions for MVP (can be tightened later)
   - No long-lived AWS credentials needed

## Prerequisites

- AWS CLI configured with credentials (`aws configure`)
- Terraform >= 1.5
- GitHub repository created

## Usage

### 1. Configure Variables

Copy the example tfvars file and fill in your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region    = "us-east-1"
project_name  = "fraud-analytics"
github_org    = "your-github-username"  # or organization
github_repo   = "fraud-analytics-pipeline"
github_branch = "main"
```

### 2. Initialize and Apply

```bash
# Initialize Terraform (local backend initially)
terraform init

# Review the plan
terraform plan

# Apply the bootstrap stack
terraform apply
```

### 3. Configure Remote Backend

After the bootstrap stack is created, you can migrate to using the remote backend:

1. Note the outputs from `terraform apply`:
   - `terraform_state_bucket`
   - `dynamodb_lock_table`
   - `kms_key_arn`

2. Add a backend configuration to `main.tf` (or create `backend.tf`):

```hcl
terraform {
  backend "s3" {
    bucket         = "<OUTPUT_VALUE_FOR_BUCKET>"
    key            = "bootstrap/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "<OUTPUT_VALUE_FOR_TABLE>"
    encrypt        = true
    kms_key_id     = "<OUTPUT_VALUE_FOR_KMS_ARN>"
  }
}
```

3. Migrate the state:

```bash
terraform init -migrate-state
```

### 4. Use in Other Terraform Modules

For other Terraform modules (e.g., `infra/envs/dev`), configure the backend:

```hcl
terraform {
  backend "s3" {
    bucket         = "fraud-analytics-terraform-state-<ACCOUNT_ID>"
    key            = "dev/terraform.tfstate"  # Different key per environment
    region         = "us-east-1"
    dynamodb_table = "fraud-analytics-terraform-locks"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:us-east-1:<ACCOUNT_ID>:key/<KEY_ID>"
  }
}
```

### 5. Configure GitHub Actions

In your GitHub Actions workflow, authenticate using the OIDC role:

```yaml
- name: Configure AWS Credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/fraud-analytics-github-actions-role
    aws-region: us-east-1
```

## Security Notes

- **Broad Permissions**: The GitHub Actions role has broad permissions for MVP speed. Tighten after the pipeline is stable.
- **KMS**: All state files are encrypted with KMS.
- **TLS**: Bucket policy enforces TLS (HTTPS) only.
- **Versioning**: State versioning protects against accidental deletions.

## Outputs

After applying, the following outputs are available:

- `terraform_state_bucket`: S3 bucket name
- `dynamodb_lock_table`: DynamoDB table name
- `kms_key_arn`: KMS key ARN
- `github_actions_role_arn`: IAM role ARN for GitHub Actions

## Cleanup

To destroy the bootstrap stack (⚠️ WARNING: This will delete your Terraform state infrastructure):

```bash
terraform destroy
```

Note: If you've migrated to remote backend, you'll need to migrate back to local first:

1. Comment out the `backend "s3"` block
2. Run `terraform init -migrate-state`
3. Then run `terraform destroy`

## Next Steps

After bootstrapping:

1. Configure remote backend in other Terraform modules
2. Set up GitHub Actions workflows to use the OIDC role
3. Start provisioning your pipeline infrastructure in `infra/envs/dev`
