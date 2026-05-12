# =============================================================================
# Sedimental EC2 GPU Instance - Start Script (PowerShell)
# =============================================================================
# This script starts the Sedimental EC2 GPU instance and waits for it to become
# accessible. It uploads configuration files to S3 before starting the instance
# to ensure the latest docker-compose.prod.yml and Caddyfile are used.
#
# Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
#
# Usage:
#   .\start-instance.ps1
#   .\start-instance.ps1 -ConfigFile "path\to\config.env"
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - config.env file with INSTANCE_ID, REGION, CONFIG_BUCKET, and AWS_PROFILE
#   - deploy/docker/docker-compose.prod.yml and Caddyfile exist
# =============================================================================

param(
    [string]$ConfigFile = "$PSScriptRoot\config.env"
)

# -----------------------------------------------------------------------------
# Configuration Loading
# -----------------------------------------------------------------------------

function Load-Config {
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        Write-Host ""
        Write-Host "ERROR: Configuration file not found: $Path" -ForegroundColor Red
        Write-Host ""
        Write-Host "To fix this:" -ForegroundColor Yellow
        Write-Host "  1. Copy config.env.example to config.env:"
        Write-Host "     cp $PSScriptRoot\config.env.example $PSScriptRoot\config.env"
        Write-Host ""
        Write-Host "  2. Deploy the CloudFormation stack (if not already done)"
        Write-Host ""
        Write-Host "  3. Fill in the values from CloudFormation outputs:"
        Write-Host "     - INSTANCE_ID: From stack output 'InstanceId'"
        Write-Host "     - CONFIG_BUCKET: From stack output 'ConfigBucketName'"
        Write-Host "     - ELASTIC_IP: From stack output 'ElasticIP'"
        Write-Host ""
        exit 1
    }
    
    $config = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        # Skip empty lines and comments
        if ($line -and -not $line.StartsWith('#')) {
            $parts = $line -split '=', 2
            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()
                $config[$key] = $value
            }
        }
    }
    
    return $config
}

function Validate-Config {
    param([hashtable]$Config)
    
    $required = @('AWS_PROFILE', 'INSTANCE_ID', 'REGION', 'CONFIG_BUCKET')
    $missing = @()
    
    foreach ($key in $required) {
        if (-not $Config[$key] -or $Config[$key] -eq '') {
            $missing += $key
        }
    }
    
    if ($missing.Count -gt 0) {
        Write-Host ""
        Write-Host "ERROR: Missing required configuration values:" -ForegroundColor Red
        foreach ($key in $missing) {
            Write-Host "  - $key" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "Please update your config.env file with values from CloudFormation outputs." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}

# -----------------------------------------------------------------------------
# AWS CLI Helpers
# -----------------------------------------------------------------------------

function Get-InstanceState {
    param(
        [string]$InstanceId,
        [string]$Region,
        [string]$Profile
    )
    
    try {
        $result = aws ec2 describe-instances `
            --instance-ids $InstanceId `
            --region $Region `
            --profile $Profile `
            --query 'Reservations[0].Instances[0].State.Name' `
            --output text 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            throw "AWS CLI error: $result"
        }
        
        return $result.Trim()
    }
    catch {
        Write-Host ""
        Write-Host "ERROR: Failed to get instance state" -ForegroundColor Red
        Write-Host "Details: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "Troubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Verify AWS CLI is installed: aws --version"
        Write-Host "  2. Verify AWS profile exists: aws configure list --profile $Profile"
        Write-Host "  3. Verify instance ID is correct: $InstanceId"
        Write-Host "  4. Verify region is correct: $Region"
        Write-Host ""
        exit 1
    }
}

function Get-PublicUrl {
    param([hashtable]$Config)
    
    if ($Config['DOMAIN_NAME'] -and $Config['DOMAIN_NAME'] -ne '') {
        return "https://$($Config['DOMAIN_NAME'])"
    }
    elseif ($Config['ELASTIC_IP'] -and $Config['ELASTIC_IP'] -ne '') {
        return "https://$($Config['ELASTIC_IP'])"
    }
    else {
        # Try to get Elastic IP from AWS
        try {
            $ip = aws ec2 describe-instances `
                --instance-ids $Config['INSTANCE_ID'] `
                --region $Config['REGION'] `
                --profile $Config['AWS_PROFILE'] `
                --query 'Reservations[0].Instances[0].PublicIpAddress' `
                --output text 2>&1
            
            if ($LASTEXITCODE -eq 0 -and $ip -and $ip -ne 'None') {
                return "https://$($ip.Trim())"
            }
        }
        catch {
            # Ignore errors, return placeholder
        }
        return "https://<elastic-ip>"
    }
}

# -----------------------------------------------------------------------------
# S3 Upload Functions
# -----------------------------------------------------------------------------

function Upload-ConfigFiles {
    param(
        [string]$Bucket,
        [string]$Region,
        [string]$Profile
    )
    
    # Find the deploy/docker directory relative to the scripts directory
    $dockerDir = Join-Path (Split-Path $PSScriptRoot -Parent) "docker"
    
    if (-not (Test-Path $dockerDir)) {
        Write-Host ""
        Write-Host "ERROR: Docker configuration directory not found: $dockerDir" -ForegroundColor Red
        Write-Host ""
        Write-Host "Expected files:" -ForegroundColor Yellow
        Write-Host "  - deploy/docker/docker-compose.prod.yml"
        Write-Host "  - deploy/docker/Caddyfile"
        Write-Host ""
        exit 1
    }
    
    $composeFile = Join-Path $dockerDir "docker-compose.prod.yml"
    $caddyFile = Join-Path $dockerDir "Caddyfile"
    
    # Validate required files exist
    $missingFiles = @()
    if (-not (Test-Path $composeFile)) { $missingFiles += "docker-compose.prod.yml" }
    if (-not (Test-Path $caddyFile)) { $missingFiles += "Caddyfile" }
    
    if ($missingFiles.Count -gt 0) {
        Write-Host ""
        Write-Host "ERROR: Missing configuration files in deploy/docker/:" -ForegroundColor Red
        foreach ($file in $missingFiles) {
            Write-Host "  - $file" -ForegroundColor Red
        }
        Write-Host ""
        exit 1
    }
    
    Write-Host "Uploading configuration files to S3..." -ForegroundColor Cyan
    Write-Host "  Bucket: $Bucket"
    
    # Upload docker-compose.prod.yml
    Write-Host "  Uploading docker-compose.prod.yml..."
    $result = aws s3 cp $composeFile "s3://$Bucket/docker-compose.prod.yml" `
        --region $Region `
        --profile $Profile 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Failed to upload docker-compose.prod.yml to S3" -ForegroundColor Red
        Write-Host "Details: $result" -ForegroundColor Red
        Write-Host ""
        Write-Host "Troubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Verify the S3 bucket exists: $Bucket"
        Write-Host "  2. Verify your AWS profile has s3:PutObject permission"
        Write-Host "  3. Check if the bucket name matches CloudFormation output 'ConfigBucketName'"
        Write-Host ""
        exit 1
    }
    
    # Upload Caddyfile
    Write-Host "  Uploading Caddyfile..."
    $result = aws s3 cp $caddyFile "s3://$Bucket/Caddyfile" `
        --region $Region `
        --profile $Profile 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Failed to upload Caddyfile to S3" -ForegroundColor Red
        Write-Host "Details: $result" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    Write-Host "  Configuration files uploaded successfully" -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------------------------
# Instance Management Functions
# -----------------------------------------------------------------------------

function Start-Instance {
    param(
        [string]$InstanceId,
        [string]$Region,
        [string]$Profile
    )
    
    Write-Host "Starting instance $InstanceId..." -ForegroundColor Cyan
    
    $result = aws ec2 start-instances `
        --instance-ids $InstanceId `
        --region $Region `
        --profile $Profile 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Failed to start instance" -ForegroundColor Red
        Write-Host "Details: $result" -ForegroundColor Red
        Write-Host ""
        Write-Host "Troubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Check AWS Console for instance status and any errors"
        Write-Host "  2. Verify your AWS profile has ec2:StartInstances permission"
        Write-Host "  3. Check if the instance is in a state that allows starting"
        Write-Host "  4. Verify service quotas allow GPU instance launch in $Region"
        Write-Host ""
        exit 1
    }
}

function Wait-ForRunningState {
    param(
        [string]$InstanceId,
        [string]$Region,
        [string]$Profile,
        [int]$TimeoutSeconds
    )
    
    Write-Host "Waiting for instance to reach 'running' state..." -ForegroundColor Cyan
    
    $startTime = Get-Date
    $lastState = ""
    
    while ($true) {
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        
        if ($elapsed -gt $TimeoutSeconds) {
            Write-Host ""
            Write-Host "ERROR: Instance failed to start within $TimeoutSeconds seconds" -ForegroundColor Red
            Write-Host ""
            Write-Host "Troubleshooting:" -ForegroundColor Yellow
            Write-Host "  1. Check AWS Console for instance status and any errors"
            Write-Host "  2. Review CloudWatch logs for user data script errors"
            Write-Host "  3. Try stopping and starting the instance manually"
            Write-Host "  4. Check if there are capacity issues in the region"
            Write-Host ""
            exit 1
        }
        
        $state = Get-InstanceState -InstanceId $InstanceId -Region $Region -Profile $Profile
        
        if ($state -ne $lastState) {
            Write-Host "  Instance state: $state (elapsed: $([math]::Round($elapsed))s)"
            $lastState = $state
        }
        
        if ($state -eq "running") {
            Write-Host "  Instance is now running" -ForegroundColor Green
            return
        }
        
        Start-Sleep -Seconds 5
    }
}

function Wait-ForHealthCheck {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [int]$IntervalSeconds
    )
    
    $healthUrl = "$Url/health"
    Write-Host "Waiting for application health check..." -ForegroundColor Cyan
    Write-Host "  Health endpoint: $healthUrl"
    
    $startTime = Get-Date
    $attempts = 0
    
    while ($true) {
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        $attempts++
        
        if ($elapsed -gt $TimeoutSeconds) {
            Write-Host ""
            Write-Host "ERROR: Health check failed after $TimeoutSeconds seconds ($attempts attempts)" -ForegroundColor Red
            Write-Host ""
            Write-Host "The instance is running but the application is not responding." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Troubleshooting:" -ForegroundColor Yellow
            Write-Host "  1. SSH to instance and check Docker status:"
            Write-Host "     ssh -i ~/.ssh/sedimental-key.pem ubuntu@<elastic-ip>"
            Write-Host "     docker compose -f /data/docker-compose.prod.yml ps"
            Write-Host ""
            Write-Host "  2. View application logs:"
            Write-Host "     docker compose -f /data/docker-compose.prod.yml logs"
            Write-Host ""
            Write-Host "  3. Check user data script logs:"
            Write-Host "     sudo cat /var/log/user-data.log"
            Write-Host ""
            Write-Host "  4. Verify GPU is detected:"
            Write-Host "     nvidia-smi"
            Write-Host ""
            exit 1
        }
        
        try {
            # Use -SkipCertificateCheck for self-signed certificates (IP-only mode)
            $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 10 -SkipCertificateCheck -ErrorAction Stop
            
            if ($response.StatusCode -eq 200) {
                Write-Host "  Health check passed (attempt $attempts, elapsed: $([math]::Round($elapsed))s)" -ForegroundColor Green
                return
            }
        }
        catch {
            # Expected to fail while services are starting
            if ($attempts % 3 -eq 0) {
                Write-Host "  Waiting... (attempt $attempts, elapsed: $([math]::Round($elapsed))s)"
            }
        }
        
        Start-Sleep -Seconds $IntervalSeconds
    }
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Sedimental EC2 GPU Instance - Start" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Load and validate configuration
Write-Host "Loading configuration from $ConfigFile..." -ForegroundColor Cyan
$config = Load-Config -Path $ConfigFile
Validate-Config -Config $config

# Set AWS_PROFILE environment variable for any child processes
$env:AWS_PROFILE = $config['AWS_PROFILE']

Write-Host "  AWS Profile: $($config['AWS_PROFILE'])"
Write-Host "  Instance ID: $($config['INSTANCE_ID'])"
Write-Host "  Region: $($config['REGION'])"
Write-Host "  Config Bucket: $($config['CONFIG_BUCKET'])"
Write-Host ""

# Get timeout values (with defaults)
$startTimeout = if ($config['START_TIMEOUT']) { [int]$config['START_TIMEOUT'] } else { 300 }
$healthTimeout = if ($config['HEALTH_CHECK_TIMEOUT']) { [int]$config['HEALTH_CHECK_TIMEOUT'] } else { 180 }
$healthInterval = if ($config['HEALTH_CHECK_INTERVAL']) { [int]$config['HEALTH_CHECK_INTERVAL'] } else { 10 }

# Check current instance state
Write-Host "Checking current instance state..." -ForegroundColor Cyan
$currentState = Get-InstanceState `
    -InstanceId $config['INSTANCE_ID'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE']

Write-Host "  Current state: $currentState"
Write-Host ""

# Handle already running instance
if ($currentState -eq "running") {
    $publicUrl = Get-PublicUrl -Config $config
    
    Write-Host "Instance is already running!" -ForegroundColor Green
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Application URL: $publicUrl" -ForegroundColor Green
    Write-Host "  Health Check: $publicUrl/health" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "To update configuration files, stop the instance first," -ForegroundColor Yellow
    Write-Host "then start it again to pull the latest configs from S3." -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# Check if instance is in a startable state
if ($currentState -notin @("stopped", "stopping")) {
    Write-Host "WARNING: Instance is in '$currentState' state." -ForegroundColor Yellow
    Write-Host "Instance must be 'stopped' to start. Current state may require waiting." -ForegroundColor Yellow
    Write-Host ""
    
    if ($currentState -eq "pending") {
        Write-Host "Instance is already starting. Waiting for it to become running..." -ForegroundColor Cyan
    }
    elseif ($currentState -eq "stopping") {
        Write-Host "Instance is stopping. Please wait for it to stop, then try again." -ForegroundColor Yellow
        exit 1
    }
    else {
        Write-Host "Unexpected state. Please check AWS Console." -ForegroundColor Red
        exit 1
    }
}

# Upload configuration files to S3 (before starting instance)
Upload-ConfigFiles `
    -Bucket $config['CONFIG_BUCKET'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE']

# Start the instance (if stopped)
if ($currentState -eq "stopped") {
    Start-Instance `
        -InstanceId $config['INSTANCE_ID'] `
        -Region $config['REGION'] `
        -Profile $config['AWS_PROFILE']
}

# Wait for running state
Wait-ForRunningState `
    -InstanceId $config['INSTANCE_ID'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE'] `
    -TimeoutSeconds $startTimeout

# Get public URL for health check
$publicUrl = Get-PublicUrl -Config $config

# Wait for health check
Wait-ForHealthCheck `
    -Url $publicUrl `
    -TimeoutSeconds $healthTimeout `
    -IntervalSeconds $healthInterval

# Success!
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Instance Started Successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Application URL: $publicUrl" -ForegroundColor Green
Write-Host "  Health Check: $publicUrl/health" -ForegroundColor Green
Write-Host ""

if (-not $config['DOMAIN_NAME'] -or $config['DOMAIN_NAME'] -eq '') {
    Write-Host "NOTE: Using IP-only mode with self-signed certificate." -ForegroundColor Yellow
    Write-Host "Your browser will show a security warning - this is expected." -ForegroundColor Yellow
    Write-Host "To use a custom domain with valid certificate, configure" -ForegroundColor Yellow
    Write-Host "DOMAIN_NAME in config.env and update DNS to point to the Elastic IP." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "To stop the instance and save costs when not in use:" -ForegroundColor Cyan
Write-Host "  .\stop-instance.ps1" -ForegroundColor Cyan
Write-Host ""
