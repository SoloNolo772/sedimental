# Implementation Plan: AWS EC2 GPU Deployment

## Overview

This implementation plan creates the infrastructure and tooling for deploying the Sedimental application to AWS using a single EC2 GPU instance. The implementation follows a bottom-up approach: first creating the CloudFormation template for AWS resources, then the Docker Compose and Caddy configurations, followed by management scripts, and finally comprehensive documentation.

Since this is an Infrastructure as Code feature, testing will be manual validation and CloudFormation template validation rather than property-based tests.

**Configuration File Distribution:** Docker Compose and Caddy configuration files are maintained in the Git repository (`deploy/docker/`) and distributed to the EC2 instance via S3. The start script uploads these files to S3 before starting the instance, and the User Data script downloads them on boot. This keeps configurations version-controlled while ensuring the instance always gets the latest version.

## Tasks

- [x] 1. Create deployment directory structure
  - Create `deploy/cloudformation/`, `deploy/scripts/`, `deploy/docker/`, and `deploy/docs/` directories
  - _Requirements: 7.1, 7.2_

- [ ] 2. Create CloudFormation template
  - [x] 2.1 Create the base CloudFormation template with parameters
    - Create `deploy/cloudformation/sedimental-stack.yaml`
    - Define parameters: InstanceType, VolumeSize, DomainName, SSHAllowedCIDR, KeyPairName
    - Add parameter constraints and validation (AllowedValues, MinValue, MaxValue, AllowedPattern)
    - _Requirements: 7.3, 7.4_
  
  - [x] 2.2 Add Security Group resource
    - Allow inbound HTTPS (443) from 0.0.0.0/0
    - Allow inbound HTTP (80) from 0.0.0.0/0 for certificate validation
    - Allow inbound SSH (22) from configurable CIDR range
    - Allow all outbound traffic
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [x] 2.3 Add Elastic IP resource
    - Create Elastic IP that persists across instance stop/start cycles
    - Associate with EC2 instance
    - _Requirements: 4.1_
  
  - [x] 2.4 Add EBS Volume resource
    - Create gp3 volume with configurable size (default 50 GB)
    - Configure to persist independently of instance lifecycle (DeletionPolicy: Retain)
    - _Requirements: 2.1, 2.2, 2.5_
  
  - [x] 2.5 Add EC2 Instance resource with User Data script
    - Configure g4dn.xlarge instance type with Ubuntu 22.04 LTS AMI
    - Include User Data script that:
      - Installs Docker and NVIDIA Container Toolkit
      - Mounts EBS volume to /data
      - Creates directory structure for jobs, input, output, temp, caddy_data
      - Downloads docker-compose.prod.yml and Caddyfile from S3 bucket
      - Starts Docker Compose services on boot
    - Enable GPU support via NVIDIA drivers
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.4, 8.1, 8.2_
  
  - [x] 2.6 Add S3 Bucket and IAM Role for configuration distribution
    - Create S3 bucket for storing docker-compose.prod.yml and Caddyfile
    - Create IAM Role with S3 read permissions for the EC2 instance
    - Create Instance Profile to attach the IAM Role to EC2
    - Update EC2 Instance to use the Instance Profile
    - Output ConfigBucketName for use with start script
    - _Requirements: 8.1, 8.2_
  
  - [x] 2.7 Add CloudFormation Outputs
    - Output InstanceId for use with management scripts
    - Output ElasticIP address for DNS configuration
    - Output PublicURL for application access
    - Output ConfigBucketName for use with start script (S3 bucket for configs)
    - _Requirements: 7.4_

- [x] 3. Checkpoint - Validate CloudFormation template
  - Validate template syntax using `aws cloudformation validate-template`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create Docker Compose production configuration
  - [x] 4.1 Create docker-compose.prod.yml
    - Create `deploy/docker/docker-compose.prod.yml`
    - Define Caddy service with ports 80 and 443 exposed
    - Define Sedimental service with internal port 8080
    - Configure GPU resource reservations for Sedimental container
    - Mount /data volumes for persistent storage
    - Configure restart policies (unless-stopped)
    - Mount caddy_data volume for certificate persistence
    - **Note:** This file is uploaded to S3 by start script and downloaded by instance on boot
    - _Requirements: 8.3, 8.4, 8.5, 8.6, 3.5_

- [x] 5. Create Caddy configuration
  - [x] 5.1 Create Caddyfile template
    - Create `deploy/docker/Caddyfile`
    - Configure reverse proxy to sedimental:8080
    - Enable automatic HTTPS via Let's Encrypt
    - Configure HTTP to HTTPS redirect
    - Handle health check endpoint
    - Use placeholder `{$DOMAIN_NAME}` for domain (substituted by User Data script)
    - **Note:** This file is uploaded to S3 by start script and downloaded by instance on boot
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 6. Create configuration file
  - [x] 6.1 Create config.env template
    - Create `deploy/scripts/config.env`
    - Include AWS_PROFILE setting (REQUIRED) to ensure scripts use project-specific IAM credentials
    - Include placeholders for INSTANCE_ID, REGION, DOMAIN_NAME, ELASTIC_IP
    - Include CONFIG_BUCKET for S3 bucket name (from CloudFormation output)
    - Include timeout configuration variables
    - Add comments explaining each variable
    - Document that AWS_PROFILE must match the user's configured profile name
    - _Requirements: 5.1, 6.1, 10.1_

- [x] 7. Create management scripts
  - [x] 7.1 Create PowerShell start script
    - Create `deploy/scripts/start-instance.ps1`
    - Load configuration from config.env
    - Set AWS_PROFILE environment variable from config before any AWS CLI calls
    - **Upload deploy/docker/* files to S3 bucket** (ensures instance gets latest configs)
    - Check if instance is already running (report status and URL if so)
    - Start instance using AWS CLI with --profile flag
    - Wait for "running" state with timeout
    - Wait for health endpoint to respond
    - Display public URL on success
    - Handle errors with troubleshooting guidance
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [x] 7.2 Create Bash start script
    - Create `deploy/scripts/start-instance.sh`
    - Implement same functionality as PowerShell version
    - Export AWS_PROFILE from config.env before AWS CLI calls
    - **Upload deploy/docker/* files to S3 bucket** (ensures instance gets latest configs)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [x] 7.3 Create PowerShell stop script
    - Create `deploy/scripts/stop-instance.ps1`
    - Load configuration from config.env
    - Set AWS_PROFILE environment variable from config before any AWS CLI calls
    - Check if instance is already stopped (report status if so)
    - Stop instance using AWS CLI with --profile flag
    - Wait for "stopped" state with timeout
    - Display confirmation message on success
    - Handle errors with troubleshooting guidance
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [x] 7.4 Create Bash stop script
    - Create `deploy/scripts/stop-instance.sh`
    - Implement same functionality as PowerShell version
    - Export AWS_PROFILE from config.env before AWS CLI calls
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [x] 7.5 Create PowerShell status script
    - Create `deploy/scripts/status-instance.ps1`
    - Load configuration from config.env
    - Set AWS_PROFILE environment variable from config before any AWS CLI calls
    - Report current instance state (running, stopped, pending, etc.)
    - If running: report public URL and check health endpoint
    - Report EBS volume attachment status
    - Display estimated costs for current billing period
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [x] 7.6 Create Bash status script
    - Create `deploy/scripts/status-instance.sh`
    - Implement same functionality as PowerShell version
    - Export AWS_PROFILE from config.env before AWS CLI calls
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 8. Checkpoint - Review scripts
  - Ensure all scripts have consistent error handling and messaging
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Create deployment documentation
  - [x] 9.1 Create DEPLOYMENT.md
    - Create `deploy/docs/DEPLOYMENT.md`
    - Include prerequisites section (AWS account, CLI, key pair)
    - Include step-by-step AWS account setup instructions (IAM user, CLI configuration)
    - Include CloudFormation deployment instructions with example commands
    - Include custom domain configuration instructions (DNS setup)
    - Include start/stop/status script usage instructions
    - Include troubleshooting section for common issues:
      - Instance won't start
      - Certificate errors
      - GPU not detected
      - Health check failures
    - Include cost estimation guidance for typical usage patterns
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 10. Final checkpoint - Review all artifacts
  - Verify all files are created in correct locations
  - Verify CloudFormation template is valid
  - Verify documentation is complete and accurate
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- This is an Infrastructure as Code feature; property-based testing is not applicable
- Testing will be manual validation and CloudFormation template validation
- Scripts are provided in both PowerShell (Windows) and Bash (Linux/Mac) for cross-platform support
- **All scripts use AWS_PROFILE from config.env** to ensure project-specific IAM credentials are used, never system defaults
- The CloudFormation template creates all resources as a single deployable unit
- EBS volume is configured with DeletionPolicy: Retain to prevent accidental data loss
- Default region is us-west-2 (user's available region)

### Configuration File Distribution (S3 Approach)

Configuration files (`docker-compose.prod.yml`, `Caddyfile`) are stored in the Git repository under `deploy/docker/` and distributed via S3:

1. **Files in repo**: Edit `deploy/docker/docker-compose.prod.yml` or `deploy/docker/Caddyfile` locally
2. **Commit changes**: Changes are tracked in Git like any other code
3. **Start script uploads**: When you run `start-instance.ps1` (or `.sh`), it uploads these files to S3
4. **Instance downloads**: User Data script on the EC2 instance downloads configs from S3 on boot
5. **Services start**: Docker Compose starts with the latest configuration

This ensures:
- Configuration is version-controlled and reviewable
- No need to redeploy CloudFormation to change configs
- Instance always gets the latest config when started
- No credentials needed on the instance (uses IAM role for S3 access)
