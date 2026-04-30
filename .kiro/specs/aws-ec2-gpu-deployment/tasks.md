# Implementation Plan: AWS EC2 GPU Deployment

## Overview

This implementation plan creates the infrastructure and tooling for deploying the Sedimental application to AWS using a single EC2 GPU instance. The implementation follows a bottom-up approach: first creating the CloudFormation template for AWS resources, then the Docker Compose and Caddy configurations, followed by management scripts, and finally comprehensive documentation.

Since this is an Infrastructure as Code feature, testing will be manual validation and CloudFormation template validation rather than property-based tests.

## Tasks

- [ ] 1. Create deployment directory structure
  - Create `deploy/cloudformation/`, `deploy/scripts/`, `deploy/docker/`, and `deploy/docs/` directories
  - _Requirements: 7.1, 7.2_

- [ ] 2. Create CloudFormation template
  - [ ] 2.1 Create the base CloudFormation template with parameters
    - Create `deploy/cloudformation/sedimental-stack.yaml`
    - Define parameters: InstanceType, VolumeSize, DomainName, SSHAllowedCIDR, KeyPairName
    - Add parameter constraints and validation (AllowedValues, MinValue, MaxValue, AllowedPattern)
    - _Requirements: 7.3, 7.4_
  
  - [ ] 2.2 Add Security Group resource
    - Allow inbound HTTPS (443) from 0.0.0.0/0
    - Allow inbound HTTP (80) from 0.0.0.0/0 for certificate validation
    - Allow inbound SSH (22) from configurable CIDR range
    - Allow all outbound traffic
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [ ] 2.3 Add Elastic IP resource
    - Create Elastic IP that persists across instance stop/start cycles
    - Associate with EC2 instance
    - _Requirements: 4.1_
  
  - [ ] 2.4 Add EBS Volume resource
    - Create gp3 volume with configurable size (default 50 GB)
    - Configure to persist independently of instance lifecycle (DeletionPolicy: Retain)
    - _Requirements: 2.1, 2.2, 2.5_
  
  - [ ] 2.5 Add EC2 Instance resource with User Data script
    - Configure g4dn.xlarge instance type with Ubuntu 22.04 LTS AMI
    - Include User Data script that:
      - Installs Docker and NVIDIA Container Toolkit
      - Mounts EBS volume to /data
      - Creates directory structure for jobs, input, output, temp, caddy_data
      - Writes docker-compose.prod.yml and Caddyfile to /data
      - Starts Docker Compose services on boot
    - Enable GPU support via NVIDIA drivers
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.4, 8.1, 8.2_
  
  - [ ] 2.6 Add CloudFormation Outputs
    - Output InstanceId for use with management scripts
    - Output ElasticIP address for DNS configuration
    - Output PublicURL for application access
    - _Requirements: 7.4_

- [ ] 3. Checkpoint - Validate CloudFormation template
  - Validate template syntax using `aws cloudformation validate-template`
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Create Docker Compose production configuration
  - [ ] 4.1 Create docker-compose.prod.yml
    - Create `deploy/docker/docker-compose.prod.yml`
    - Define Caddy service with ports 80 and 443 exposed
    - Define Sedimental service with internal port 8080
    - Configure GPU resource reservations for Sedimental container
    - Mount /data volumes for persistent storage
    - Configure restart policies (unless-stopped)
    - Mount caddy_data volume for certificate persistence
    - _Requirements: 8.3, 8.4, 8.5, 8.6, 3.5_

- [ ] 5. Create Caddy configuration
  - [ ] 5.1 Create Caddyfile template
    - Create `deploy/docker/Caddyfile`
    - Configure reverse proxy to sedimental:8080
    - Enable automatic HTTPS via Let's Encrypt
    - Configure HTTP to HTTPS redirect
    - Handle health check endpoint
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 6. Create configuration file
  - [ ] 6.1 Create config.env template
    - Create `deploy/scripts/config.env`
    - Include placeholders for INSTANCE_ID, REGION, DOMAIN_NAME, ELASTIC_IP
    - Include timeout configuration variables
    - Add comments explaining each variable
    - _Requirements: 5.1, 6.1, 10.1_

- [ ] 7. Create management scripts
  - [ ] 7.1 Create PowerShell start script
    - Create `deploy/scripts/start-instance.ps1`
    - Load configuration from config.env
    - Check if instance is already running (report status and URL if so)
    - Start instance using AWS CLI
    - Wait for "running" state with timeout
    - Wait for health endpoint to respond
    - Display public URL on success
    - Handle errors with troubleshooting guidance
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [ ] 7.2 Create Bash start script
    - Create `deploy/scripts/start-instance.sh`
    - Implement same functionality as PowerShell version
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [ ] 7.3 Create PowerShell stop script
    - Create `deploy/scripts/stop-instance.ps1`
    - Load configuration from config.env
    - Check if instance is already stopped (report status if so)
    - Stop instance using AWS CLI
    - Wait for "stopped" state with timeout
    - Display confirmation message on success
    - Handle errors with troubleshooting guidance
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [ ] 7.4 Create Bash stop script
    - Create `deploy/scripts/stop-instance.sh`
    - Implement same functionality as PowerShell version
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [ ] 7.5 Create PowerShell status script
    - Create `deploy/scripts/status-instance.ps1`
    - Load configuration from config.env
    - Report current instance state (running, stopped, pending, etc.)
    - If running: report public URL and check health endpoint
    - Report EBS volume attachment status
    - Display estimated costs for current billing period
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ] 7.6 Create Bash status script
    - Create `deploy/scripts/status-instance.sh`
    - Implement same functionality as PowerShell version
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 8. Checkpoint - Review scripts
  - Ensure all scripts have consistent error handling and messaging
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Create deployment documentation
  - [ ] 9.1 Create DEPLOYMENT.md
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

- [ ] 10. Final checkpoint - Review all artifacts
  - Verify all files are created in correct locations
  - Verify CloudFormation template is valid
  - Verify documentation is complete and accurate
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- This is an Infrastructure as Code feature; property-based testing is not applicable
- Testing will be manual validation and CloudFormation template validation
- Scripts are provided in both PowerShell (Windows) and Bash (Linux/Mac) for cross-platform support
- The CloudFormation template creates all resources as a single deployable unit
- EBS volume is configured with DeletionPolicy: Retain to prevent accidental data loss
- User Data script handles all instance boot configuration automatically
