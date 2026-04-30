# Requirements Document

## Introduction

This document specifies the requirements for deploying the Sedimental sediment grain analysis application to AWS using a single EC2 GPU instance. The deployment is designed for occasional batch processing workloads where the instance can be started on-demand and stopped when not in use to minimize costs. The solution prioritizes simplicity over high availability, using Caddy as a reverse proxy for automatic HTTPS and EBS volumes for data persistence.

## Glossary

- **EC2_Instance**: An Amazon EC2 virtual server running the Sedimental application with GPU capabilities (g4dn.xlarge or similar NVIDIA GPU instance type)
- **Caddy_Proxy**: The Caddy web server configured as a reverse proxy that handles TLS termination and automatic HTTPS certificate management via Let's Encrypt
- **EBS_Volume**: An Amazon Elastic Block Store volume attached to the EC2 instance for persistent storage of job data, results, and the SQLite database
- **Elastic_IP**: A static public IPv4 address associated with the EC2 instance that persists across instance stop/start cycles
- **Start_Script**: A CLI script (PowerShell or bash) that starts the stopped EC2 instance and waits for it to become accessible
- **Stop_Script**: A CLI script (PowerShell or bash) that gracefully stops the running EC2 instance
- **Security_Group**: An AWS security group that controls inbound and outbound network traffic to the EC2 instance
- **User_Data_Script**: A shell script that runs on EC2 instance boot to configure and start the application services
- **Docker_Compose**: The container orchestration tool used to run the Sedimental application and Caddy proxy together

## Requirements

### Requirement 1: EC2 GPU Instance Provisioning

**User Story:** As a system administrator, I want to provision an EC2 GPU instance with the necessary configuration, so that the Sedimental application can run with GPU acceleration.

#### Acceptance Criteria

1. THE EC2_Instance SHALL use a g4dn.xlarge instance type (or user-configurable GPU instance type) with NVIDIA GPU support
2. THE EC2_Instance SHALL run Amazon Linux 2023 or Ubuntu 22.04 LTS as the base operating system
3. THE EC2_Instance SHALL have Docker and Docker Compose installed and configured to use the NVIDIA Container Toolkit
4. THE EC2_Instance SHALL have the NVIDIA GPU drivers installed and functional
5. WHEN the EC2_Instance starts, THE User_Data_Script SHALL automatically start the Sedimental application and Caddy proxy

### Requirement 2: Persistent Data Storage

**User Story:** As a user, I want my job data and results to persist across instance restarts, so that I don't lose my work when the instance is stopped.

#### Acceptance Criteria

1. THE EBS_Volume SHALL be attached to the EC2_Instance at a consistent mount point (/data)
2. THE EBS_Volume SHALL persist independently of the EC2_Instance lifecycle (not deleted when instance is terminated)
3. THE EBS_Volume SHALL store the SQLite jobs database, uploaded images, and processing results
4. WHEN the EC2_Instance restarts, THE EBS_Volume SHALL be automatically remounted at the same mount point
5. THE EBS_Volume SHALL have a minimum size of 50 GB (configurable based on expected workload)

### Requirement 3: HTTPS with Automatic Certificate Management

**User Story:** As a user, I want to access the application over HTTPS with a valid certificate, so that my data is transmitted securely.

#### Acceptance Criteria

1. THE Caddy_Proxy SHALL obtain and renew TLS certificates automatically via Let's Encrypt
2. THE Caddy_Proxy SHALL redirect all HTTP requests (port 80) to HTTPS (port 443)
3. THE Caddy_Proxy SHALL proxy HTTPS requests to the Sedimental application running on port 8080
4. WHEN a valid domain name is configured, THE Caddy_Proxy SHALL serve the application on that domain with a valid TLS certificate
5. THE Caddy_Proxy SHALL store certificate data on the EBS_Volume so certificates persist across restarts

### Requirement 4: Network Configuration and Security

**User Story:** As a system administrator, I want the instance to be securely accessible from the internet, so that users can access the application while minimizing attack surface.

#### Acceptance Criteria

1. THE Elastic_IP SHALL be associated with the EC2_Instance and persist across stop/start cycles
2. THE Security_Group SHALL allow inbound traffic on port 443 (HTTPS) from any IP address (0.0.0.0/0)
3. THE Security_Group SHALL allow inbound traffic on port 80 (HTTP) from any IP address for certificate validation and redirect
4. THE Security_Group SHALL allow inbound traffic on port 22 (SSH) from a configurable IP range for administration
5. THE Security_Group SHALL deny all other inbound traffic by default
6. THE Security_Group SHALL allow all outbound traffic for package updates and Let's Encrypt validation

### Requirement 5: Instance Start Script

**User Story:** As a user, I want a simple script to start the EC2 instance, so that I can quickly bring up the application when I need to process images.

#### Acceptance Criteria

1. THE Start_Script SHALL start the EC2_Instance using the AWS CLI
2. WHEN the EC2_Instance is already running, THE Start_Script SHALL report the current status and public URL
3. THE Start_Script SHALL wait for the instance to reach the "running" state before completing
4. THE Start_Script SHALL display the public URL (Elastic_IP or domain name) where the application is accessible
5. THE Start_Script SHALL verify the application health endpoint responds before reporting success
6. IF the EC2_Instance fails to start within a timeout period, THEN THE Start_Script SHALL report an error with troubleshooting guidance

### Requirement 6: Instance Stop Script

**User Story:** As a user, I want a simple script to stop the EC2 instance, so that I can minimize costs when I'm not processing images.

#### Acceptance Criteria

1. THE Stop_Script SHALL stop the EC2_Instance using the AWS CLI
2. WHEN the EC2_Instance is already stopped, THE Stop_Script SHALL report the current status
3. THE Stop_Script SHALL wait for the instance to reach the "stopped" state before completing
4. THE Stop_Script SHALL display a confirmation message when the instance is successfully stopped
5. IF the EC2_Instance fails to stop within a timeout period, THEN THE Stop_Script SHALL report an error with troubleshooting guidance

### Requirement 7: Infrastructure as Code

**User Story:** As a system administrator, I want the infrastructure defined as code, so that I can reliably create, update, and destroy the deployment.

#### Acceptance Criteria

1. THE infrastructure definition SHALL use AWS CloudFormation or Terraform to define all AWS resources
2. THE infrastructure definition SHALL create the EC2_Instance, EBS_Volume, Elastic_IP, and Security_Group as a single deployable unit
3. THE infrastructure definition SHALL accept parameters for instance type, EBS volume size, domain name, and SSH allowed IP range
4. THE infrastructure definition SHALL output the Elastic_IP address and instance ID after deployment
5. THE infrastructure definition SHALL include the User_Data_Script for automatic application startup

### Requirement 8: Application Startup Configuration

**User Story:** As a system administrator, I want the application to start automatically when the instance boots, so that the service is available without manual intervention.

#### Acceptance Criteria

1. WHEN the EC2_Instance boots, THE User_Data_Script SHALL mount the EBS_Volume to /data
2. WHEN the EC2_Instance boots, THE User_Data_Script SHALL start Docker Compose with the Sedimental and Caddy services
3. THE Docker_Compose configuration SHALL mount the /data directory for persistent storage
4. THE Docker_Compose configuration SHALL configure Caddy to proxy requests to the Sedimental container
5. THE Docker_Compose configuration SHALL restart containers automatically if they crash
6. THE Docker_Compose configuration SHALL enable GPU access for the Sedimental container

### Requirement 9: Deployment Documentation

**User Story:** As a user who is not an AWS expert, I want clear documentation for deploying and managing the infrastructure, so that I can set up and operate the system without deep AWS knowledge.

#### Acceptance Criteria

1. THE documentation SHALL include step-by-step instructions for initial AWS account setup (IAM user, CLI configuration)
2. THE documentation SHALL include instructions for deploying the infrastructure using the provided templates
3. THE documentation SHALL include instructions for configuring a custom domain name with DNS
4. THE documentation SHALL include instructions for using the start and stop scripts
5. THE documentation SHALL include troubleshooting guidance for common issues (instance won't start, certificate errors, GPU not detected)
6. THE documentation SHALL include cost estimation guidance for typical usage patterns

### Requirement 10: Status and Monitoring Script

**User Story:** As a user, I want to check the current status of my deployment, so that I can understand whether the instance is running and the application is healthy.

#### Acceptance Criteria

1. THE Status_Script SHALL report the current EC2_Instance state (running, stopped, pending, etc.)
2. WHEN the EC2_Instance is running, THE Status_Script SHALL report the public URL
3. WHEN the EC2_Instance is running, THE Status_Script SHALL check and report the application health endpoint status
4. THE Status_Script SHALL report the EBS_Volume attachment status
5. THE Status_Script SHALL display estimated costs for the current billing period (if instance has been running)
