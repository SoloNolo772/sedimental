# =============================================================================
# Sedimental EC2 GPU Instance - Stop Script (PowerShell)
# =============================================================================
# This script stops the Sedimental EC2 GPU instance to save costs when not in
# use. The EBS volume and Elastic IP persist, so data is preserved and the
# instance can be started again with the same IP address.
#
# Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
#
# Usage:
#   .\stop-instance.ps1
#   .\stop-instance.ps1 -ConfigFile "path\to\config.env"
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - config.env file with INSTANCE_ID, REGION, and AWS_PROFILE
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
    
    $required = @('AWS_PROFILE', 'INSTANCE_ID', 'REGION')
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

# -----------------------------------------------------------------------------
# Instance Management Functions
# -----------------------------------------------------------------------------

function Stop-Instance {
    param(
        [string]$InstanceId,
        [string]$Region,
        [string]$Profile
    )
    
    Write-Host "Stopping instance $InstanceId..." -ForegroundColor Cyan
    
    $result = aws ec2 stop-instances `
        --instance-ids $InstanceId `
        --region $Region `
        --profile $Profile 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Failed to stop instance" -ForegroundColor Red
        Write-Host "Details: $result" -ForegroundColor Red
        Write-Host ""
        Write-Host "Troubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Check AWS Console for instance status and any errors"
        Write-Host "  2. Verify your AWS profile has ec2:StopInstances permission"
        Write-Host "  3. Check if the instance is in a state that allows stopping"
        Write-Host "  4. If instance is stuck, try force-stopping via AWS Console"
        Write-Host ""
        exit 1
    }
}

function Wait-ForStoppedState {
    param(
        [string]$InstanceId,
        [string]$Region,
        [string]$Profile,
        [int]$TimeoutSeconds
    )
    
    Write-Host "Waiting for instance to reach 'stopped' state..." -ForegroundColor Cyan
    
    $startTime = Get-Date
    $lastState = ""
    
    while ($true) {
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        
        if ($elapsed -gt $TimeoutSeconds) {
            Write-Host ""
            Write-Host "ERROR: Instance failed to stop within $TimeoutSeconds seconds" -ForegroundColor Red
            Write-Host ""
            Write-Host "Troubleshooting:" -ForegroundColor Yellow
            Write-Host "  1. Check AWS Console for instance status and any errors"
            Write-Host "  2. The instance may be stuck - try force-stopping via AWS Console"
            Write-Host "  3. Check CloudWatch logs for any issues during shutdown"
            Write-Host "  4. If the instance has a stuck process, you may need to force stop"
            Write-Host ""
            Write-Host "To force stop via AWS CLI:" -ForegroundColor Yellow
            Write-Host "  aws ec2 stop-instances --instance-ids $InstanceId --force --region $Region --profile $Profile"
            Write-Host ""
            exit 1
        }
        
        $state = Get-InstanceState -InstanceId $InstanceId -Region $Region -Profile $Profile
        
        if ($state -ne $lastState) {
            Write-Host "  Instance state: $state (elapsed: $([math]::Round($elapsed))s)"
            $lastState = $state
        }
        
        if ($state -eq "stopped") {
            Write-Host "  Instance is now stopped" -ForegroundColor Green
            return
        }
        
        Start-Sleep -Seconds 5
    }
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Sedimental EC2 GPU Instance - Stop" -ForegroundColor Cyan
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
Write-Host ""

# Get timeout value (with default)
$stopTimeout = if ($config['STOP_TIMEOUT']) { [int]$config['STOP_TIMEOUT'] } else { 120 }

# Check current instance state
Write-Host "Checking current instance state..." -ForegroundColor Cyan
$currentState = Get-InstanceState `
    -InstanceId $config['INSTANCE_ID'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE']

Write-Host "  Current state: $currentState"
Write-Host ""

# Handle already stopped instance
if ($currentState -eq "stopped") {
    Write-Host "Instance is already stopped." -ForegroundColor Green
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Instance Status: STOPPED" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "No charges are being incurred for compute time." -ForegroundColor Cyan
    Write-Host "Note: EBS storage charges still apply while the volume exists." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To start the instance again:" -ForegroundColor Cyan
    Write-Host "  .\start-instance.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 0
}

# Check if instance is in a stoppable state
if ($currentState -eq "stopping") {
    Write-Host "Instance is already stopping. Waiting for it to stop..." -ForegroundColor Yellow
    Write-Host ""
}
elseif ($currentState -eq "pending") {
    Write-Host "WARNING: Instance is in 'pending' state (starting up)." -ForegroundColor Yellow
    Write-Host "It's recommended to wait for the instance to fully start before stopping." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Do you want to stop it anyway? This may cause issues." -ForegroundColor Yellow
    $response = Read-Host "Continue? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
    Write-Host ""
}
elseif ($currentState -eq "terminated") {
    Write-Host "ERROR: Instance has been terminated and cannot be stopped." -ForegroundColor Red
    Write-Host ""
    Write-Host "A terminated instance is permanently deleted." -ForegroundColor Yellow
    Write-Host "You will need to redeploy the CloudFormation stack to create a new instance." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
elseif ($currentState -ne "running") {
    Write-Host "WARNING: Instance is in unexpected state: $currentState" -ForegroundColor Yellow
    Write-Host "Attempting to stop anyway..." -ForegroundColor Yellow
    Write-Host ""
}

# Stop the instance (if not already stopping)
if ($currentState -ne "stopping") {
    Stop-Instance `
        -InstanceId $config['INSTANCE_ID'] `
        -Region $config['REGION'] `
        -Profile $config['AWS_PROFILE']
}

# Wait for stopped state
Wait-ForStoppedState `
    -InstanceId $config['INSTANCE_ID'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE'] `
    -TimeoutSeconds $stopTimeout

# Success!
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Instance Stopped Successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Instance ID: $($config['INSTANCE_ID'])" -ForegroundColor Green
Write-Host "  Status: STOPPED" -ForegroundColor Green
Write-Host ""
Write-Host "Cost savings:" -ForegroundColor Cyan
Write-Host "  - No compute charges while stopped"
Write-Host "  - EBS storage charges continue (~$0.08/GB/month for gp3)"
Write-Host "  - Elastic IP charges apply if not attached to running instance (~$0.005/hour)"
Write-Host ""
Write-Host "Your data is preserved:" -ForegroundColor Cyan
Write-Host "  - EBS volume with jobs database and results is retained"
Write-Host "  - Elastic IP address is preserved for next start"
Write-Host "  - TLS certificates are stored on the EBS volume"
Write-Host ""
Write-Host "To start the instance again:" -ForegroundColor Cyan
Write-Host "  .\start-instance.ps1" -ForegroundColor Cyan
Write-Host ""
