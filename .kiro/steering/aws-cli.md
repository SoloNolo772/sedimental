# AWS CLI Usage Requirements

This project uses AWS services for deployment. All AWS CLI commands must follow these requirements.

## Required Flags

**Every AWS CLI command MUST include both:**

1. `--profile sedimental` - Use the project-specific IAM credentials
2. `--region us-east-1` - Explicitly specify the deployment region

## Why This Matters

- **Profile**: Prevents accidentally using default credentials or credentials from other projects
- **Region**: Ensures commands target the correct region where our GPU quota and resources exist

## Examples

### Correct Usage

```powershell
# Validate CloudFormation template
aws cloudformation validate-template `
    --template-body file://deploy/cloudformation/sedimental-stack.yaml `
    --region us-east-1 `
    --profile sedimental

# Check instance status
aws ec2 describe-instances `
    --instance-ids i-0123456789abcdef0 `
    --region us-east-1 `
    --profile sedimental

# Upload to S3
aws s3 cp file.txt s3://bucket-name/ `
    --region us-east-1 `
    --profile sedimental
```

### Incorrect Usage (will fail or use wrong credentials)

```powershell
# Missing profile - uses default credentials
aws cloudformation validate-template --template-body file://template.yaml --region us-east-1

# Missing region - uses profile's default region (may be wrong)
aws ec2 describe-instances --instance-ids i-xxx --profile sedimental

# Missing both - unpredictable behavior
aws s3 ls
```

## Project Configuration

- **AWS Profile Name**: `sedimental`
- **IAM User**: `sedimental-admin`
- **Primary Region**: `us-east-1` (GPU quota approved here)
- **EC2 Key Pair**: `sedimental-key-east` (in us-east-1)

## Management Scripts

The management scripts in `deploy/scripts/` automatically load these values from `config.env`:
- `AWS_PROFILE=sedimental`
- `REGION=us-east-1`

When running scripts directly, they handle profile/region automatically. This steering rule applies when running ad-hoc AWS CLI commands.

## CloudFormation Template Guidelines

### Validation Limitations

`aws cloudformation validate-template` only checks syntax and structure. It does **not** validate:
- Service-specific field constraints (character limits, allowed characters)
- Whether resources will actually create (quotas, permissions)
- Runtime parameter values

Always test deployments in a non-production environment first.

### Fields That Must Be Single-Line

Several AWS resource properties reject multi-line strings or have strict character restrictions. **Never use YAML multi-line syntax (`>`, `|`) for these fields:**

| Resource Type | Property | Constraint |
|---------------|----------|------------|
| `AWS::EC2::SecurityGroup` | `GroupDescription` | Max 255 chars, no newlines, limited charset: `a-zA-Z0-9. _-:/()#,@[]+=&;{}!$*` |
| `AWS::IAM::Role` | `RoleName` | Max 64 chars, alphanumeric + `+=,.@_-` |
| `AWS::IAM::Policy` | `PolicyName` | Max 128 chars, alphanumeric + `+=,.@_-` |
| `AWS::S3::Bucket` | `BucketName` | Max 63 chars, lowercase + numbers + hyphens |
| `AWS::EC2::KeyPair` | `KeyName` | Max 255 chars, no leading/trailing spaces |
| `AWS::CloudFormation::Stack` | `StackName` | Max 128 chars, alphanumeric + hyphens |

### Correct vs Incorrect Examples

```yaml
# WRONG - multi-line will include newlines
GroupDescription: >
  Security group for Sedimental application.
  Allows HTTPS, HTTP, and SSH access.

# CORRECT - single line
GroupDescription: Security group for Sedimental - allows HTTPS (443), HTTP (80), and SSH (22)
```

### Fields Where Multi-Line Is OK

These fields accept multi-line content:
- `UserData` (base64 encoded, newlines expected)
- `Description` on most resources (stack description, parameter descriptions)
- IAM policy `Statement` blocks (JSON structure)
- `Metadata` sections
