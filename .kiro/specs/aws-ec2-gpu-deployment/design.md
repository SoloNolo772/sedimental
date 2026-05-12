# Design Document: AWS EC2 GPU Deployment

## Overview

This design document describes the architecture and implementation for deploying the Sedimental sediment grain analysis application to AWS using a single EC2 GPU instance. The deployment is optimized for occasional batch processing workloads where cost efficiency is achieved by starting the instance on-demand and stopping it when not in use.

### Design Goals

1. **Simplicity**: Single-instance deployment with minimal operational complexity
2. **Cost Efficiency**: Pay only when processing images (instance can be stopped)
3. **Security**: HTTPS with automatic certificate management, restricted SSH access
4. **Persistence**: Data survives instance restarts via EBS volumes
5. **Ease of Use**: Simple scripts for non-AWS-experts to start/stop the instance

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Infrastructure as Code | AWS CloudFormation | AWS-native, no additional tooling required, integrates with AWS CLI |
| Operating System | Ubuntu 22.04 LTS | Better Docker/NVIDIA ecosystem support, wider community documentation |
| Reverse Proxy | Caddy | Automatic HTTPS via Let's Encrypt, zero-config TLS, simple configuration |
| Container Orchestration | Docker Compose | Already used in development, consistent deployment model |
| Management Scripts | PowerShell + Bash | Cross-platform support for Windows and Linux/Mac users |
| Config File Distribution | S3 Bucket | Keeps docker-compose.prod.yml and Caddyfile in version control; start script uploads to S3, instance pulls on boot |

## Architecture

### High-Level Architecture

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
│  │                                                                     │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │                    NVIDIA Container Toolkit                   │  │ │
│  │  │                    (GPU Passthrough)                          │  │ │
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

### Request Flow

```
User Request (HTTPS)
        │
        ▼
   Elastic IP
        │
        ▼
  Security Group (allow 443)
        │
        ▼
   Caddy Container
   ├── TLS Termination
   ├── Certificate Management
   └── Proxy to :8080
        │
        ▼
  Sedimental Container
   ├── FastAPI Web Server
   ├── Job Processing (GPU)
   └── SQLite Database
```

## Components and Interfaces

### 1. CloudFormation Stack

The infrastructure is defined as a single CloudFormation template that creates all required AWS resources.

**Resources Created:**
- EC2 Instance (g4dn.xlarge with Ubuntu 22.04)
- EBS Volume (50 GB, gp3)
- Elastic IP
- Security Group
- S3 Bucket (for configuration files - docker-compose.prod.yml, Caddyfile)
- IAM Role and Instance Profile (for EC2 to read from S3)

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| InstanceType | String | g4dn.xlarge | EC2 instance type with NVIDIA GPU |
| VolumeSize | Number | 50 | EBS volume size in GB |
| DomainName | String | (none) | Domain name for HTTPS (e.g., sedimental.example.com) |
| SSHAllowedCIDR | String | 0.0.0.0/0 | IP range allowed for SSH access |
| KeyPairName | String | (required) | EC2 key pair for SSH access |

**Outputs:**

| Output | Description |
|--------|-------------|
| InstanceId | EC2 instance ID for use with start/stop scripts |
| ElasticIP | Public IP address for DNS configuration |
| PublicURL | Full HTTPS URL to access the application |
| ConfigBucketName | S3 bucket name for uploading configuration files |

### 2. Configuration File Distribution via S3

Configuration files (docker-compose.prod.yml, Caddyfile) are maintained in the Git repository under `deploy/docker/` and distributed to the EC2 instance via S3. This approach:

- **Keeps configs in version control**: Changes are tracked, reviewed, and committed like any other code
- **Automatic sync on start**: The start script uploads latest configs to S3 before starting the instance
- **No embedded configs**: User Data script pulls from S3 rather than having configs embedded in CloudFormation
- **Easy updates**: Change the file locally, commit, run start script - instance gets new config

**Flow:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Configuration Distribution Flow                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Developer edits deploy/docker/docker-compose.prod.yml locally       │
│                              │                                           │
│                              ▼                                           │
│  2. Developer commits changes to Git                                     │
│                              │                                           │
│                              ▼                                           │
│  3. Developer runs start-instance.ps1 (or .sh)                          │
│                              │                                           │
│                              ▼                                           │
│  4. Start script uploads deploy/docker/* to S3 bucket                   │
│     (aws s3 sync deploy/docker/ s3://{bucket}/)                         │
│                              │                                           │
│                              ▼                                           │
│  5. Start script starts EC2 instance                                     │
│                              │                                           │
│                              ▼                                           │
│  6. User Data script on instance pulls configs from S3                  │
│     (aws s3 cp s3://{bucket}/docker-compose.prod.yml /data/)            │
│                              │                                           │
│                              ▼                                           │
│  7. Docker Compose starts with latest configuration                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**S3 Bucket Contents:**
```
s3://{stack-name}-config-{account-id}/
├── docker-compose.prod.yml    # Production Docker Compose configuration
└── Caddyfile                  # Caddy reverse proxy configuration
```

### 3. User Data Script

The user data script runs on every instance boot and performs:

1. **EBS Volume Mount**: Mounts the data volume to `/data`
2. **Docker Setup**: Ensures Docker and NVIDIA Container Toolkit are running
3. **Config Download**: Pulls docker-compose.prod.yml and Caddyfile from S3
4. **Application Startup**: Runs Docker Compose to start Caddy and Sedimental

```bash
#!/bin/bash
# User data script structure (simplified)

# 1. Wait for EBS volume attachment
# 2. Format volume if new (ext4)
# 3. Mount to /data
# 4. Create directory structure
# 5. Download docker-compose.prod.yml from S3
# 6. Download Caddyfile from S3 (with domain substitution)
# 7. Pull latest images
# 8. Start services with docker compose
```

### 4. Docker Compose Production Configuration

**File: `/data/docker-compose.prod.yml`**

The production Docker Compose configuration differs from development:
- Uses pre-built image from Docker Hub or ECR (not local build)
- Caddy service added for reverse proxy
- Production restart policies
- GPU resource reservations
- Persistent volume mounts from EBS

**Services:**

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| caddy | caddy:2-alpine | 80, 443 | Reverse proxy, TLS termination |
| sedimental | sedimental:latest | 8080 (internal) | Application server |

### 5. Caddy Configuration

**File: `/data/Caddyfile`**

```
{domain_name} {
    reverse_proxy sedimental:8080
    
    # Health check endpoint bypass (no TLS required internally)
    handle /health* {
        reverse_proxy sedimental:8080
    }
}
```

Caddy automatically:
- Obtains Let's Encrypt certificates
- Renews certificates before expiry
- Redirects HTTP to HTTPS
- Stores certificates in `/data/caddy_data`

### 6. Management Scripts

#### Start Script (PowerShell: `start-instance.ps1`, Bash: `start-instance.sh`)

```
┌─────────────────────────────────────────┐
│           Start Instance Flow           │
├─────────────────────────────────────────┤
│ 1. Upload config files to S3            │
│    └─ deploy/docker/* → S3 bucket       │
│ 2. Check current instance state         │
│    └─ If running: show URL and exit     │
│ 3. Start instance via AWS CLI           │
│ 4. Wait for "running" state             │
│ 5. Wait for health endpoint (retry)     │
│ 6. Display success message with URL     │
│ 7. Handle timeout with error guidance   │
└─────────────────────────────────────────┘
```

#### Stop Script (PowerShell: `stop-instance.ps1`, Bash: `stop-instance.sh`)

```
┌─────────────────────────────────────────┐
│           Stop Instance Flow            │
├─────────────────────────────────────────┤
│ 1. Check current instance state         │
│    └─ If stopped: show status and exit  │
│ 2. Stop instance via AWS CLI            │
│ 3. Wait for "stopped" state             │
│ 4. Display confirmation message         │
│ 5. Handle timeout with error guidance   │
└─────────────────────────────────────────┘
```

#### Status Script (PowerShell: `status-instance.ps1`, Bash: `status-instance.sh`)

```
┌─────────────────────────────────────────┐
│          Status Check Flow              │
├─────────────────────────────────────────┤
│ 1. Get instance state from AWS          │
│ 2. If running:                          │
│    ├─ Show public URL                   │
│    ├─ Check health endpoint             │
│    └─ Show uptime estimate              │
│ 3. Show EBS volume status               │
│ 4. Estimate current billing period cost │
└─────────────────────────────────────────┘
```

### 7. Directory Structure

```
deploy/
├── cloudformation/
│   └── sedimental-stack.yaml       # CloudFormation template
├── scripts/
│   ├── start-instance.ps1          # PowerShell start script
│   ├── start-instance.sh           # Bash start script
│   ├── stop-instance.ps1           # PowerShell stop script
│   ├── stop-instance.sh            # Bash stop script
│   ├── status-instance.ps1         # PowerShell status script
│   ├── status-instance.sh          # Bash status script
│   └── config.env                  # Configuration (instance ID, region)
├── docker/
│   ├── docker-compose.prod.yml     # Production compose file
│   └── Caddyfile                   # Caddy configuration template
└── docs/
    └── DEPLOYMENT.md               # Deployment documentation
```

## Data Models

### CloudFormation Parameters Schema

```yaml
Parameters:
  InstanceType:
    Type: String
    Default: g4dn.xlarge
    AllowedValues:
      - g4dn.xlarge
      - g4dn.2xlarge
      - g5.xlarge
      - g5.2xlarge
    Description: GPU instance type

  VolumeSize:
    Type: Number
    Default: 50
    MinValue: 20
    MaxValue: 1000
    Description: EBS volume size in GB

  DomainName:
    Type: String
    Default: ""
    Description: Domain name for HTTPS (leave empty for IP-only access)

  SSHAllowedCIDR:
    Type: String
    Default: "0.0.0.0/0"
    AllowedPattern: ^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$
    Description: CIDR range for SSH access

  KeyPairName:
    Type: AWS::EC2::KeyPair::KeyName
    Description: EC2 key pair for SSH access
```

### Script Configuration Schema

**File: `config.env`**

```bash
# AWS Profile - REQUIRED for all AWS CLI commands
# This ensures scripts use the project-specific IAM credentials
# instead of system default credentials
AWS_PROFILE=sedimental

# Required - set after CloudFormation deployment
INSTANCE_ID=i-0123456789abcdef0
REGION=us-west-2
CONFIG_BUCKET=sedimental-stack-config-123456789012

# Optional - for status display
DOMAIN_NAME=sedimental.example.com
ELASTIC_IP=1.2.3.4

# Timeouts (seconds)
START_TIMEOUT=300
STOP_TIMEOUT=120
HEALTH_CHECK_TIMEOUT=180
```

**Important:** All management scripts will use the `AWS_PROFILE` setting from config.env. This ensures:
- Scripts never accidentally use default/other AWS credentials
- The project remains isolated from other AWS work on the same machine
- Users must explicitly configure the profile name for their setup

**CONFIG_BUCKET:** This is the S3 bucket created by CloudFormation for storing configuration files. The start script uses this to upload docker-compose.prod.yml and Caddyfile before starting the instance.

### EBS Volume Directory Structure

```
/data/
├── jobs/                    # Job storage (SQLite + files)
│   ├── jobs.db             # SQLite database
│   └── {job-id}/           # Per-job directories
│       ├── input/          # Uploaded images
│       ├── output/         # Results and masks
│       └── metadata.json   # Job metadata
├── input/                   # CLI input directory
├── output/                  # CLI output directory
├── temp/                    # Temporary processing files
├── caddy_data/             # Caddy certificates and state
│   └── certificates/       # Let's Encrypt certificates
├── docker-compose.prod.yml # Production compose file (downloaded from S3 on boot)
└── Caddyfile               # Caddy configuration (downloaded from S3 on boot)
```

## Error Handling

### Instance Startup Errors

| Error Condition | Detection | Recovery Action |
|-----------------|-----------|-----------------|
| Instance fails to start | AWS API returns error | Display error message, suggest checking AWS console |
| Instance stuck in pending | Timeout after 5 minutes | Display timeout error, suggest manual check |
| Health check fails | HTTP request fails after retries | Display troubleshooting steps (SSH, logs) |
| EBS mount fails | User data script logs error | Check CloudWatch logs, remount manually |

### Application Errors

| Error Condition | Detection | Recovery Action |
|-----------------|-----------|-----------------|
| Docker service not running | Health check fails | SSH and restart Docker service |
| GPU not detected | Application logs error | Check NVIDIA driver, restart instance |
| Certificate error | Caddy logs, HTTPS fails | Check domain DNS, Caddy logs |
| Disk full | Application errors | Increase EBS volume size |

### Script Error Messages

```
ERROR: Instance failed to start within 5 minutes.
Troubleshooting steps:
1. Check AWS Console for instance status
2. Review CloudWatch logs for user data script errors
3. SSH to instance and check: sudo journalctl -u docker

ERROR: Health check failed after 3 minutes.
The instance is running but the application is not responding.
Troubleshooting steps:
1. SSH to instance: ssh -i your-key.pem ubuntu@{ELASTIC_IP}
2. Check Docker status: docker compose -f /data/docker-compose.prod.yml ps
3. View application logs: docker compose -f /data/docker-compose.prod.yml logs
```

## Testing Strategy

### Infrastructure Testing

Since this feature involves Infrastructure as Code (CloudFormation), UI-less scripts, and AWS service integration, **property-based testing is not applicable**. The testing strategy focuses on:

1. **CloudFormation Validation**
   - Template syntax validation (`aws cloudformation validate-template`)
   - Parameter constraint testing with example values
   - Drift detection after deployment

2. **Script Testing**
   - Manual testing with real AWS resources
   - Error path testing (instance already running, already stopped, etc.)
   - Timeout behavior verification

3. **Integration Testing**
   - End-to-end deployment to a test AWS account
   - Verify instance starts and application responds
   - Verify data persistence across stop/start cycles
   - Verify HTTPS certificate issuance (with real domain)

4. **Documentation Testing**
   - Follow deployment guide on fresh AWS account
   - Verify all commands work as documented
   - Test troubleshooting steps

### Test Scenarios

| Scenario | Test Method | Success Criteria |
|----------|-------------|------------------|
| Fresh deployment | Manual CloudFormation deploy | Stack creates successfully, outputs valid |
| Instance start | Run start script | Instance running, health check passes |
| Instance stop | Run stop script | Instance stopped, confirmation shown |
| Data persistence | Stop/start cycle | Jobs database and files preserved |
| HTTPS access | Browser test | Valid certificate, no warnings |
| GPU detection | SSH and verify | `nvidia-smi` shows GPU |

### Pre-Deployment Checklist

- [ ] AWS CLI configured with named profile (e.g., `aws configure --profile sedimental`)
- [ ] AWS_PROFILE set in config.env to match your profile name
- [ ] EC2 key pair created in target region
- [ ] Domain DNS configured (if using custom domain)
- [ ] Service quotas allow g4dn instance launch
- [ ] VPC has internet gateway (default VPC works)

