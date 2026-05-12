# Sedimental AWS EC2 GPU Deployment Guide

This guide walks you through deploying the Sedimental sediment grain analysis application to AWS using a single EC2 GPU instance. The deployment is designed for occasional batch processing workloads where you can start the instance on-demand and stop it when not in use to minimize costs.

## Table of Contents

- [Prerequisites](#prerequisites)
- [AWS Account Setup](#aws-account-setup)
- [CloudFormation Deployment](#cloudformation-deployment)
- [Custom Domain Configuration](#custom-domain-configuration)
- [Using the Management Scripts](#using-the-management-scripts)
- [Troubleshooting](#troubleshooting)
- [Cost Estimation](#cost-estimation)
- [Architecture Overview](#architecture-overview)

---

## Prerequisites

Before you begin, ensure you have the following:

### Required Software

1. **AWS CLI** (version 2.x recommended)
   - Windows: Download from [AWS CLI Installation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
   - Verify installation: `aws --version`

2. **PowerShell** (Windows) or **Bash** (Linux/Mac)
   - Windows: PowerShell 5.1+ (included with Windows 10/11)
   - Linux/Mac: Bash shell (included with most distributions)

### Required AWS Resources

1. **AWS Account** with permissions to create:
   - EC2 instances (including GPU instances)
   - EBS volumes
   - Elastic IPs
   - Security Groups
   - S3 buckets
   - IAM roles and policies
   - CloudFormation stacks

2. **EC2 Key Pair** for SSH access
   - This is an AWS resource (not a local SSH key) that you create via the AWS Console or CLI
   - Must be created in the same region where you'll deploy the instance
   - You'll create this in [Step 3 of AWS Account Setup](#step-3-create-an-ec2-key-pair) below

3. **Service Quota** for GPU instances (g4dn or g5 family) in your target region

4. **NVIDIA Driver Requirements**
   - The Docker image uses CUDA 12.1, which requires NVIDIA driver version 525 or higher (535+ recommended)
   - The AWS Deep Learning AMI typically includes NVIDIA drivers, but they may need updating
   - See [GPU Not Detected](#gpu-not-detected) troubleshooting section if you encounter driver issues

### Optional

- **Custom Domain** with access to DNS settings (for HTTPS with Let's Encrypt)

---

## AWS Account Setup

### Step 1: Create an IAM User (Recommended)

For security, create a dedicated IAM user for Sedimental deployment instead of using your root account.

1. Sign in to the [AWS Console](https://console.aws.amazon.com/)

2. Navigate to **IAM** → **Users** → **Create user**

3. Enter a username (e.g., `sedimental-admin`)

4. Select **Attach policies directly** and add one of these options:
   
   **Option A: AdministratorAccess** (simplest)
   - `AdministratorAccess` - covers everything needed
   
   **Option B: Specific policies** (more restrictive)
   - `AmazonEC2FullAccess`
   - `AmazonS3FullAccess`
   - `IAMFullAccess`
   - `AWSCloudFormationFullAccess`

   **Option C: Minimum permissions** (most restrictive)
   - See [Minimum IAM Permissions](#minimum-iam-permissions) below

5. Complete the user creation and save the access keys

### Step 2: Configure AWS CLI Profile

Create a named profile for Sedimental to keep credentials separate from other AWS work:

```powershell
# Windows PowerShell
aws configure --profile sedimental
```

```bash
# Linux/Mac
aws configure --profile sedimental
```

Enter the following when prompted:
- **AWS Access Key ID**: Your IAM user's access key
- **AWS Secret Access Key**: Your IAM user's secret key
- **Default region name**: `us-east-1` (or your preferred region with GPU availability)
- **Default output format**: `json`

Verify the configuration:

```powershell
aws sts get-caller-identity --profile sedimental
```

### Step 3: Create an EC2 Key Pair

An EC2 Key Pair is an AWS resource that enables SSH access to your instance. When you create it, AWS generates a public/private key pair - AWS keeps the public key, and you download the private key (`.pem` file). This private key is your only way to SSH into the instance.

**Option A: Create via AWS Console (easier)**

1. **First, select your target region** in the top-right dropdown (e.g., `us-east-1`)
   - Key pairs are region-specific - they only exist in the region where you create them
2. Go to **EC2** → **Key Pairs** (under Network & Security)
3. Click **Create key pair**
4. Enter name: `sedimental-key`
5. Select **RSA** and **.pem** format
6. Click **Create key pair** - the `.pem` file downloads automatically
7. Move the file to a secure location and restrict permissions

**Option B: Create via AWS CLI**

```powershell
# Windows PowerShell - Create key pair and save the private key
aws ec2 create-key-pair `
    --key-name sedimental-key `
    --query 'KeyMaterial' `
    --output text `
    --profile sedimental `
    --region us-east-1 > sedimental-key-east.pem
```

```bash
# Linux/Mac
aws ec2 create-key-pair \
    --key-name sedimental-key \
    --query 'KeyMaterial' \
    --output text \
    --profile sedimental \
    --region us-east-1 > sedimental-key-east.pem

# Set correct permissions (required on Linux/Mac)
chmod 400 sedimental-key-east.pem
```

**Important**: 
- Store this `.pem` file securely - you cannot download it again
- You'll need it every time you SSH to the instance
- The key pair must be in the same region as your deployment

**Windows users**: Move the key to your `.ssh` folder and fix permissions:
```powershell
# Create .ssh folder and move key there
mkdir -Force $env:USERPROFILE\.ssh
Move-Item sedimental-key-east.pem $env:USERPROFILE\.ssh\sedimental-key.pem

# Fix permissions (required for SSH to accept the key)
icacls $env:USERPROFILE\.ssh\sedimental-key-east.pem /inheritance:r
icacls $env:USERPROFILE\.ssh\sedimental-key-east.pem /grant:r "$($env:USERNAME):(R)"
```

**Linux/Mac users**: Set permissions:
```bash
chmod 400 sedimental-key-east.pem
# Optionally move to ~/.ssh/
mv sedimental-key-east.pem ~/.ssh/sedimental-key-east.pem
```

### Step 4: Check GPU Instance Quota

Verify you have quota for GPU instances in your region:

```powershell
aws service-quotas get-service-quota `
    --service-code ec2 `
    --quota-code L-DB2E81BA `
    --profile sedimental `
    --region us-east-1
```

If the quota is 0, request an increase through the AWS Console:
1. Go to **Service Quotas** → **Amazon EC2**
2. Search for "Running On-Demand G and VT instances"
3. Request a quota increase (4 vCPUs minimum for g4dn.xlarge)

---

## CloudFormation Deployment

### Step 1: Deploy the Stack

Navigate to the `deploy/cloudformation/` directory and deploy the stack:

```powershell
# Windows PowerShell
aws cloudformation create-stack `
    --stack-name sedimental-stack `
    --template-body file://sedimental-stack.yaml `
    --parameters `
        ParameterKey=KeyPairName,ParameterValue=sedimental-key `
        ParameterKey=InstanceType,ParameterValue=g4dn.xlarge `
        ParameterKey=VolumeSize,ParameterValue=50 `
        ParameterKey=SSHAllowedCIDR,ParameterValue=0.0.0.0/0 `
    --capabilities CAPABILITY_NAMED_IAM `
    --profile sedimental `
    --region us-east-1
```

```bash
# Linux/Mac
aws cloudformation create-stack \
    --stack-name sedimental-stack \
    --template-body file://sedimental-stack.yaml \
    --parameters \
        ParameterKey=KeyPairName,ParameterValue=sedimental-key \
        ParameterKey=InstanceType,ParameterValue=g4dn.xlarge \
        ParameterKey=VolumeSize,ParameterValue=50 \
        ParameterKey=SSHAllowedCIDR,ParameterValue=0.0.0.0/0 \
    --capabilities CAPABILITY_NAMED_IAM \
    --profile sedimental \
    --region us-east-1
```

### Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `KeyPairName` | (required) | Name of your EC2 key pair for SSH access |
| `InstanceType` | `g4dn.xlarge` | GPU instance type (g4dn.xlarge, g4dn.2xlarge, g5.xlarge, etc.) |
| `VolumeSize` | `50` | EBS data volume size in GB (20-1000) |
| `DomainName` | (empty) | Custom domain for HTTPS (e.g., `sedimental.example.com`) |
| `SSHAllowedCIDR` | `0.0.0.0/0` | IP range for SSH access (restrict for security) |

### Step 2: Wait for Stack Creation

Monitor the stack creation progress:

```powershell
aws cloudformation wait stack-create-complete `
    --stack-name sedimental-stack `
    --profile sedimental `
    --region us-east-1
```

This typically takes 5-10 minutes. You can also monitor progress in the AWS Console under **CloudFormation** → **Stacks**.

### Step 3: Get Stack Outputs

Retrieve the deployment outputs:

```powershell
aws cloudformation describe-stacks `
    --stack-name sedimental-stack `
    --query 'Stacks[0].Outputs' `
    --output table `
    --profile sedimental `
    --region us-east-1
```

You'll see outputs like:
- **InstanceId**: `i-0123456789abcdef0` (for management scripts)
- **ElasticIP**: `52.10.20.30` (for DNS configuration)
- **PublicURL**: `https://52.10.20.30` (application URL)
- **ConfigBucketName**: `sedimental-stack-config-123456789012` (for config distribution)

### Step 4: Configure Management Scripts

1. Copy the example configuration file:

   ```powershell
   # Windows
   Copy-Item deploy\scripts\config.env.example deploy\scripts\config.env
   ```

   ```bash
   # Linux/Mac
   cp deploy/scripts/config.env.example deploy/scripts/config.env
   ```

2. Edit `deploy/scripts/config.env` with the CloudFormation outputs:

   ```bash
   # AWS Profile - must match your configured profile
   AWS_PROFILE=sedimental

   # From CloudFormation outputs
   INSTANCE_ID=i-0123456789abcdef0
   REGION=us-east-1
   CONFIG_BUCKET=sedimental-stack-config-123456789012
   ELASTIC_IP=52.10.20.30

   # Optional - if using custom domain
   DOMAIN_NAME=
   ```

### Step 5: Build the Docker Image on EC2

The Docker image should be built directly on the EC2 instance rather than locally. This ensures the image is built in the same environment where it will run (Linux x86_64 with NVIDIA GPU support).

**Why build on EC2?**
- Same architecture as the runtime environment
- NVIDIA Container Toolkit available during build
- Avoids transferring multi-GB images over the network
- No cross-platform compatibility concerns

**Build Steps:**

1. **SSH to the instance** (after CloudFormation deployment completes):

   ```bash
   ssh -i ~/.ssh/sedimental-key-east.pem ubuntu@<elastic-ip>
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/your-username/sedimental.git /home/ubuntu/sedimental
   cd /home/ubuntu/sedimental
   ```

   Or if using a private repository, you can:
   - Use SSH keys (add your deploy key to the instance)
   - Use HTTPS with a personal access token
   - Copy the code via `scp` from your local machine:
     ```powershell
     # From your local machine (PowerShell)
     scp -i ~/.ssh/sedimental-key-east.pem -r . ubuntu@<elastic-ip>:/home/ubuntu/sedimental
     ```

3. **Build the Docker image**:

   ```bash
   cd /home/ubuntu/sedimental
   docker build -t sedimental:latest .
   ```

   This may take 15-25 minutes on first build as it:
   - Downloads base images and installs dependencies
   - Pre-initializes PyImageJ (downloads ImageJ2 JARs from Maven Central)
   - Pre-downloads Cellpose models (cyto2 and nuclei) from the internet
   
   The model pre-download ensures that processing jobs don't fail due to network issues when trying to download models at runtime.

4. **Verify the build**:

   ```bash
   docker images | grep sedimental
   
   # Verify Cellpose models were downloaded
   docker run --rm sedimental:latest ls -la /home/sedimental/.cellpose/models/
   ```

5. **Verify GPU access** (important!):

   ```bash
   # Check NVIDIA driver version on host
   nvidia-smi
   
   # If driver version is below 525, update it:
   sudo apt-get update
   sudo apt-get install -y nvidia-driver-535
   sudo reboot
   # After reboot, reconnect via SSH and continue
   
   # Verify GPU is accessible from Docker
   docker run --rm --gpus all sedimental:latest python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"
   ```

6. **Exit SSH and run the start script** from your local machine to start the services:

   ```powershell
   .\deploy\scripts\start-instance.ps1
   ```

**Alternative: Amazon ECR (for CI/CD pipelines)**

For automated deployments, you can use Amazon ECR:
1. Create an ECR repository
2. Build and push from a CI/CD pipeline
3. Update `docker-compose.prod.yml` to reference the ECR image URL
4. Grant the EC2 instance's IAM role permission to pull from ECR

This is more complex but useful for production workflows with automated builds

---

## Custom Domain Configuration

To use a custom domain with automatic HTTPS certificates from Let's Encrypt:

### Step 1: Update CloudFormation with Domain Name

If you didn't specify a domain during initial deployment, update the stack:

```powershell
aws cloudformation update-stack `
    --stack-name sedimental-stack `
    --use-previous-template `
    --parameters `
        ParameterKey=KeyPairName,UsePreviousValue=true `
        ParameterKey=InstanceType,UsePreviousValue=true `
        ParameterKey=VolumeSize,UsePreviousValue=true `
        ParameterKey=SSHAllowedCIDR,UsePreviousValue=true `
        ParameterKey=DomainName,ParameterValue=sedimental.io `
    --capabilities CAPABILITY_NAMED_IAM `
    --profile sedimental `
    --region us-east-1
```

### Step 2: Configure DNS

Add a DNS A record pointing your domain to the Elastic IP:

| Record Type | Name | Value |
|-------------|------|-------|
| A | `sedimental.example.com` | `52.10.20.30` (your Elastic IP) |

DNS propagation can take up to 48 hours, but typically completes within minutes to a few hours.

### Step 3: Update config.env

Add your domain to the configuration:

```bash
DOMAIN_NAME=sedimental.example.com
```

### Step 4: Restart the Instance

Stop and start the instance to apply the new configuration:

```powershell
.\deploy\scripts\stop-instance.ps1
.\deploy\scripts\start-instance.ps1
```

Caddy will automatically obtain a Let's Encrypt certificate for your domain.

---

## Using the Management Scripts

The management scripts are located in `deploy/scripts/` and are available in both PowerShell (Windows) and Bash (Linux/Mac) versions.

### Starting the Instance

```powershell
# Windows
.\deploy\scripts\start-instance.ps1
```

```bash
# Linux/Mac
./deploy/scripts/start-instance.sh
```

The start script:
1. Uploads the latest `docker-compose.prod.yml` and `Caddyfile` to S3
2. Starts the EC2 instance
3. Waits for the instance to reach "running" state
4. Waits for the health endpoint to respond
5. Displays the application URL

### Stopping the Instance

```powershell
# Windows
.\deploy\scripts\stop-instance.ps1
```

```bash
# Linux/Mac
./deploy/scripts/stop-instance.sh
```

The stop script:
1. Stops the EC2 instance
2. Waits for the instance to reach "stopped" state
3. Displays cost savings information

**Important**: Stop the instance when not in use to avoid unnecessary charges. Your data is preserved on the EBS volume.

### Checking Status

```powershell
# Windows
.\deploy\scripts\status-instance.ps1
```

```bash
# Linux/Mac
./deploy/scripts/status-instance.sh
```

The status script displays:
- Instance state (running, stopped, etc.)
- Public URL and health check status
- EBS volume attachment status
- Estimated costs for the current billing period

---

## Troubleshooting

### Instance Won't Start

**Symptoms**: Start script times out or AWS Console shows instance stuck in "pending"

**Possible Causes and Solutions**:

1. **Insufficient GPU quota**
   - Check your service quota for G instances
   - Request a quota increase in the AWS Console

2. **Capacity issues in the region**
   - Try a different availability zone
   - Try a different instance type (e.g., g5.xlarge instead of g4dn.xlarge)

3. **Key pair not found**
   - Verify the key pair exists in the correct region
   - Create a new key pair if needed

**Diagnostic Commands**:

```powershell
# Check instance state and reason
aws ec2 describe-instances `
    --instance-ids <instance-id> `
    --query 'Reservations[0].Instances[0].[State,StateReason]' `
    --profile sedimental `
    --region us-east-1
```

### Certificate Errors

**Symptoms**: Browser shows certificate warning, HTTPS not working

**Possible Causes and Solutions**:

1. **Using IP-only mode (no domain configured)**
   - This is expected behavior - Caddy uses a self-signed certificate
   - Accept the browser warning to proceed
   - Configure a custom domain for valid certificates

2. **DNS not propagated**
   - Wait for DNS propagation (can take up to 48 hours)
   - Verify DNS with: `nslookup sedimental.example.com`

3. **Let's Encrypt rate limits**
   - Let's Encrypt has rate limits (50 certificates per domain per week)
   - Wait and try again later

4. **Caddy certificate storage issue**
   - SSH to instance and check Caddy logs:
     ```bash
     docker compose -f /data/docker-compose.prod.yml logs caddy
     ```

### GPU Not Detected

**Symptoms**: Application errors about GPU not available, slow processing, or CUDA version mismatch warnings

**Possible Causes and Solutions**:

1. **NVIDIA drivers not installed**
   - SSH to instance and check: `nvidia-smi`
   - If not found, the user data script may have failed

2. **NVIDIA driver version too old for CUDA 12.1**
   - The Docker image uses CUDA 12.1, which requires NVIDIA driver 525+ (535+ recommended)
   - Check current driver version: `nvidia-smi` (look for "Driver Version" in output)
   - If you see warnings like "NVIDIA driver on your system is too old (found version 12020)", update the driver:
     ```bash
     # Update to driver 535 (supports CUDA 12.1)
     sudo apt-get update
     sudo apt-get install -y nvidia-driver-535
     sudo reboot
     ```
   - After reboot, verify: `nvidia-smi` should show Driver Version 535.x or higher

3. **First boot after driver installation**
   - Reboot the instance: `sudo reboot`
   - NVIDIA drivers may require a reboot after first installation

4. **Docker not configured for GPU**
   - Check NVIDIA Container Toolkit: `docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi`

**Diagnostic Commands**:

```bash
# SSH to instance
ssh -i ~/.ssh/sedimental-key-east.pem ubuntu@<elastic-ip>

# Check GPU status and driver version
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi

# Check user data script logs
sudo cat /var/log/user-data.log

# Check if GPU is being used by the container
docker exec sedimental python3 -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

### Health Check Failures

**Symptoms**: Start script reports health check failed, application not responding

**Possible Causes and Solutions**:

1. **Docker services still starting**
   - Wait a few more minutes - initial startup can take time
   - Check service status: `docker compose -f /data/docker-compose.prod.yml ps`

2. **Application crashed**
   - Check application logs: `docker compose -f /data/docker-compose.prod.yml logs sedimental`

3. **Configuration files not downloaded from S3**
   - Check user data logs: `sudo cat /var/log/user-data.log`
   - Verify S3 bucket has the config files

4. **Port not accessible**
   - Verify security group allows ports 80 and 443
   - Check if Caddy is running: `docker compose -f /data/docker-compose.prod.yml ps caddy`

**Diagnostic Commands**:

```bash
# SSH to instance
ssh -i ~/.ssh/sedimental-key-east.pem ubuntu@<elastic-ip>

# Check all services
docker compose -f /data/docker-compose.prod.yml ps

# View logs
docker compose -f /data/docker-compose.prod.yml logs

# Check if config files exist
ls -la /data/docker-compose.prod.yml /data/Caddyfile

# Test health endpoint locally
curl http://localhost:8080/health
```

### Job Shows "Completed" But No Output Files

**Symptoms**: Job status shows "completed" but output folder is empty, or mask files are missing

**Possible Causes and Solutions**:

1. **All images failed to process**
   - Check the job status API for error details:
     ```bash
     docker exec sedimental curl -s http://localhost:8080/api/jobs/<job-id>
     ```
   - If `progress.current` is 0 but `progress.total` is > 0, all images failed
   - The `error_message` field will contain details about what went wrong

2. **Cellpose model download failed**
   - Check if models exist in the container:
     ```bash
     docker exec sedimental ls -la /home/sedimental/.cellpose/models/
     ```
   - If empty, the model download failed during processing
   - The Docker image now pre-downloads models during build, so rebuild the image:
     ```bash
     docker compose build
     docker compose -f /data/docker-compose.prod.yml down
     docker compose -f /data/docker-compose.prod.yml up -d
     ```

3. **Permissions issue on output directory**
   - Check permissions:
     ```bash
     ls -la /data/jobs/<job-id>/output/
     ```
   - Fix if needed:
     ```bash
     sudo chmod -R 777 /data/jobs/
     ```

4. **Segmentation error**
   - Check the full container logs for errors:
     ```bash
     docker logs sedimental 2>&1 | grep -A 10 "<job-id>"
     ```

**Note**: The application now properly reports failures. If all images fail, the job status will be "failed" with a detailed error message. Partial failures show "completed" but include error details in the `error_message` field.

### EBS Volume Issues

**Symptoms**: Data not persisting, disk full errors

**Possible Causes and Solutions**:

1. **Volume not mounted**
   - Check mount: `df -h /data`
   - Check fstab: `cat /etc/fstab`

2. **Disk full**
   - Check usage: `df -h`
   - Clean up old job data or increase volume size

3. **Volume in wrong availability zone**
   - EBS volumes must be in the same AZ as the instance
   - This shouldn't happen with CloudFormation but check if manually modified

---

## Cost Estimation

### Hourly Costs (USEast 1 Region)

| Resource | Cost | Notes |
|----------|------|-------|
| g4dn.xlarge | ~$0.526/hour | Only when running |
| g4dn.2xlarge | ~$0.752/hour | Only when running |
| g5.xlarge | ~$1.006/hour | Only when running |
| EBS gp3 (50 GB) | ~$4.00/month | Always (even when stopped) |
| Elastic IP | ~$0.005/hour | Only when instance is stopped |

### Example Usage Patterns

**Light Usage (10 hours/month)**:
- Compute: 10 × $0.526 = $5.26
- Storage: $4.00
- **Total: ~$9.26/month**

**Moderate Usage (40 hours/month)**:
- Compute: 40 × $0.526 = $21.04
- Storage: $4.00
- **Total: ~$25.04/month**

**Heavy Usage (160 hours/month)**:
- Compute: 160 × $0.526 = $84.16
- Storage: $4.00
- **Total: ~$88.16/month**

### Cost Optimization Tips

1. **Stop the instance when not in use** - This is the biggest cost saver
2. **Use spot instances** for non-critical workloads (requires CloudFormation modification)
3. **Right-size the instance** - g4dn.xlarge is sufficient for most workloads
4. **Monitor with AWS Cost Explorer** - Set up billing alerts

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Internet                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │   Elastic IP    │
                          │  (Static IPv4)  │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │  Security Group │
                          │  ┌───────────┐  │
                          │  │ 443 HTTPS │  │
                          │  │ 80 HTTP   │  │
                          │  │ 22 SSH    │  │
                          │  └───────────┘  │
                          └────────┬────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│                         EC2 Instance (g4dn.xlarge)                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        Ubuntu 22.04 LTS                             │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │                      Docker Compose                           │  │ │
│  │  │  ┌─────────────────┐      ┌─────────────────────────────┐   │  │ │
│  │  │  │      Caddy      │      │       Sedimental            │   │  │ │
│  │  │  │  (Reverse Proxy)│─────▶│    (FastAPI + GPU)          │   │  │ │
│  │  │  │   :443, :80     │      │        :8080                │   │  │ │
│  │  │  └─────────────────┘      └─────────────────────────────┘   │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                   │                                      │
│                          ┌────────▼────────┐                            │
│                          │   /data mount   │                            │
│                          └────────┬────────┘                            │
└───────────────────────────────────┼─────────────────────────────────────┘
                                    │
                          ┌─────────▼─────────┐
                          │    EBS Volume     │
                          │   (Persistent)    │
                          │  ┌─────────────┐  │
                          │  │ /data/jobs  │  │
                          │  │ /data/input │  │
                          │  │ /data/output│  │
                          │  │ caddy_data  │  │
                          │  └─────────────┘  │
                          └───────────────────┘
```

### Configuration Distribution Flow

```
1. Edit deploy/docker/docker-compose.prod.yml locally
                    │
                    ▼
2. Commit changes to Git
                    │
                    ▼
3. Run start-instance.ps1 (or .sh)
                    │
                    ▼
4. Script uploads deploy/docker/* to S3 bucket
                    │
                    ▼
5. Script starts EC2 instance
                    │
                    ▼
6. User Data script downloads configs from S3
                    │
                    ▼
7. Docker Compose starts with latest configuration
```

---

## Minimum IAM Permissions

If you prefer to use minimum permissions instead of full access policies, create a custom IAM policy with these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:StartInstances",
                "ec2:StopInstances",
                "ec2:DescribeVolumes",
                "ec2:CreateKeyPair",
                "ec2:DescribeKeyPairs"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::sedimental-stack-config-*",
                "arn:aws:s3:::sedimental-stack-config-*/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "cloudformation:CreateStack",
                "cloudformation:UpdateStack",
                "cloudformation:DeleteStack",
                "cloudformation:DescribeStacks",
                "cloudformation:DescribeStackEvents"
            ],
            "Resource": "arn:aws:cloudformation:*:*:stack/sedimental-*/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:AttachRolePolicy",
                "iam:DetachRolePolicy",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:CreateInstanceProfile",
                "iam:DeleteInstanceProfile",
                "iam:AddRoleToInstanceProfile",
                "iam:RemoveRoleFromInstanceProfile",
                "iam:PassRole"
            ],
            "Resource": [
                "arn:aws:iam::*:role/sedimental-*",
                "arn:aws:iam::*:instance-profile/sedimental-*"
            ]
        }
    ]
}
```

---

## Deleting the Deployment

To completely remove the deployment:

1. **Stop the instance** (if running):
   ```powershell
   .\deploy\scripts\stop-instance.ps1
   ```

2. **Delete the CloudFormation stack**:
   ```powershell
   aws cloudformation delete-stack `
       --stack-name sedimental-stack `
       --profile sedimental `
       --region us-east-1
   ```

3. **Delete the EBS volume** (if you want to remove all data):
   
   The EBS volume has `DeletionPolicy: Retain` to prevent accidental data loss. To delete it manually:
   ```powershell
   aws ec2 delete-volume `
       --volume-id <volume-id> `
       --profile sedimental `
       --region us-east-1
   ```

4. **Delete the EC2 key pair** (optional):
   ```powershell
   aws ec2 delete-key-pair `
       --key-name sedimental-key `
       --profile sedimental `
       --region us-east-1
   ```

---

## Getting Help

If you encounter issues not covered in this guide:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review CloudWatch logs for the EC2 instance
3. SSH to the instance and check `/var/log/user-data.log`
4. Check Docker logs: `docker compose -f /data/docker-compose.prod.yml logs`
