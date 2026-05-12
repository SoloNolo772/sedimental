# =============================================================================
# Sedimental EC2 GPU Instance - Status Script (PowerShell)
# =============================================================================
# This script reports the current status of the Sedimental EC2 GPU instance,
# including instance state, health check status, EBS volume attachment, and
# estimated costs for the current billing period.
#
# Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
#
# Usage:
#   .\status-instance.ps1
#   .\status-instance.ps1 -ConfigFile "path\to\config.env"
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

function Get-InstanceDetails {
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
            --output json 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            throw "AWS CLI error: $result"
        }
        
        return $result | ConvertFrom-Json
    }
    catch {
        Write-Host ""
        Write-Host "ERROR: Failed to get instance details" -ForegroundColor Red
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
        return $null
    }
}

function Get-HealthStatus {
    param([string]$Url)
    
    if (-not $Url) {
        return @{
            Status = "unknown"
            Message = "No URL configured"
        }
    }
    
    $healthUrl = "$Url/health"
    
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 10 -SkipCertificateCheck -ErrorAction Stop
        
        if ($response.StatusCode -eq 200) {
            return @{
                Status = "healthy"
                Message = "Application is responding"
                StatusCode = $response.StatusCode
            }
        }
        else {
            return @{
                Status = "unhealthy"
                Message = "Unexpected status code"
                StatusCode = $response.StatusCode
            }
        }
    }
    catch {
        return @{
            Status = "unreachable"
            Message = "Health endpoint not responding"
            Error = $_.Exception.Message
        }
    }
}

function Get-VolumeDetails {
    param(
        [string]$InstanceId,
        [string]$Region,
        [string]$Profile
    )
    
    try {
        $result = aws ec2 describe-volumes `
            --filters "Name=attachment.instance-id,Values=$InstanceId" `
            --region $Region `
            --profile $Profile `
            --output json 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        
        return ($result | ConvertFrom-Json).Volumes
    }
    catch {
        return $null
    }
}

function Get-InstanceLaunchTime {
    param($InstanceData)
    
    try {
        $launchTimeStr = $InstanceData.Reservations[0].Instances[0].LaunchTime
        if ($launchTimeStr) {
            return [DateTime]::Parse($launchTimeStr)
        }
    }
    catch {
        # Ignore parsing errors
    }
    return $null
}

# -----------------------------------------------------------------------------
# Cost Estimation Functions
# -----------------------------------------------------------------------------

function Get-EstimatedCosts {
    param(
        [string]$InstanceType,
        [int]$VolumeSizeGB,
        [DateTime]$LaunchTime,
        [string]$InstanceState
    )
    
    # Approximate hourly costs (us-west-2 pricing, may vary by region)
    $instanceCosts = @{
        "g4dn.xlarge"  = 0.526
        "g4dn.2xlarge" = 0.752
        "g5.xlarge"    = 1.006
        "g5.2xlarge"   = 1.212
    }
    
    $hourlyRate = if ($instanceCosts.ContainsKey($InstanceType)) { 
        $instanceCosts[$InstanceType] 
    } else { 
        0.526  # Default to g4dn.xlarge
    }
    
    # EBS gp3 storage cost: ~$0.08/GB/month
    $ebsMonthlyRate = 0.08
    $ebsDailyRate = $ebsMonthlyRate / 30
    
    # Elastic IP cost when not attached to running instance: ~$0.005/hour
    $eipHourlyRate = 0.005
    
    # Calculate costs
    $costs = @{
        InstanceHourlyRate = $hourlyRate
        EBSMonthlyRate = $ebsMonthlyRate * $VolumeSizeGB
        EIPHourlyRate = $eipHourlyRate
    }
    
    # Calculate running time and costs if instance is running
    if ($InstanceState -eq "running" -and $LaunchTime) {
        $runningHours = [math]::Ceiling(((Get-Date) - $LaunchTime).TotalHours)
        $costs.RunningHours = $runningHours
        $costs.ComputeCost = [math]::Round($runningHours * $hourlyRate, 2)
    }
    else {
        $costs.RunningHours = 0
        $costs.ComputeCost = 0
    }
    
    # Estimate monthly costs based on current billing period
    $today = Get-Date
    $daysInMonth = [DateTime]::DaysInMonth($today.Year, $today.Month)
    $dayOfMonth = $today.Day
    
    $costs.EBSCostThisMonth = [math]::Round(($dayOfMonth / $daysInMonth) * $ebsMonthlyRate * $VolumeSizeGB, 2)
    
    # EIP cost (charged when not attached to running instance)
    if ($InstanceState -ne "running") {
        $costs.EIPCostEstimate = [math]::Round($eipHourlyRate * 24 * $dayOfMonth, 2)
    }
    else {
        $costs.EIPCostEstimate = 0
    }
    
    return $costs
}

# -----------------------------------------------------------------------------
# Display Functions
# -----------------------------------------------------------------------------

function Write-StatusHeader {
    param([string]$Title)
    
    Write-Host ""
    Write-Host "--------------------------------------------" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "--------------------------------------------" -ForegroundColor Cyan
}

function Write-StatusLine {
    param(
        [string]$Label,
        [string]$Value,
        [string]$Color = "White"
    )
    
    $paddedLabel = $Label.PadRight(20)
    Write-Host "  $paddedLabel : " -NoNewline
    Write-Host $Value -ForegroundColor $Color
}

function Get-StateColor {
    param([string]$State)
    
    switch ($State) {
        "running"    { return "Green" }
        "stopped"    { return "Yellow" }
        "pending"    { return "Cyan" }
        "stopping"   { return "Cyan" }
        "terminated" { return "Red" }
        default      { return "White" }
    }
}

function Get-HealthColor {
    param([string]$Status)
    
    switch ($Status) {
        "healthy"     { return "Green" }
        "unhealthy"   { return "Red" }
        "unreachable" { return "Yellow" }
        default       { return "White" }
    }
}

function Get-AttachmentColor {
    param([string]$Status)
    
    switch ($Status) {
        "attached" { return "Green" }
        "detached" { return "Yellow" }
        default    { return "White" }
    }
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Sedimental EC2 GPU Instance - Status" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Load and validate configuration
Write-Host "Loading configuration..." -ForegroundColor Gray
$config = Load-Config -Path $ConfigFile
Validate-Config -Config $config

# Set AWS_PROFILE environment variable for any child processes
$env:AWS_PROFILE = $config['AWS_PROFILE']

# Get instance details
Write-Host "Fetching instance details..." -ForegroundColor Gray
$instanceData = Get-InstanceDetails `
    -InstanceId $config['INSTANCE_ID'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE']

$instance = $instanceData.Reservations[0].Instances[0]
$instanceState = $instance.State.Name
$instanceType = $instance.InstanceType
$publicIp = $instance.PublicIpAddress
$launchTime = Get-InstanceLaunchTime -InstanceData $instanceData

# Get volume details
$volumes = Get-VolumeDetails `
    -InstanceId $config['INSTANCE_ID'] `
    -Region $config['REGION'] `
    -Profile $config['AWS_PROFILE']

# -----------------------------------------------------------------------------
# Display Instance Status
# -----------------------------------------------------------------------------

Write-StatusHeader "Instance Status"
Write-StatusLine "Instance ID" $config['INSTANCE_ID']
Write-StatusLine "Instance Type" $instanceType
Write-StatusLine "Region" $config['REGION']
Write-StatusLine "State" $instanceState.ToUpper() -Color (Get-StateColor $instanceState)

if ($launchTime -and $instanceState -eq "running") {
    $uptime = (Get-Date) - $launchTime
    $uptimeStr = "{0}d {1}h {2}m" -f $uptime.Days, $uptime.Hours, $uptime.Minutes
    Write-StatusLine "Uptime" $uptimeStr
    Write-StatusLine "Launch Time" $launchTime.ToString("yyyy-MM-dd HH:mm:ss UTC")
}

# -----------------------------------------------------------------------------
# Display Network Status (if running)
# -----------------------------------------------------------------------------

Write-StatusHeader "Network Status"

if ($publicIp) {
    Write-StatusLine "Public IP" $publicIp -Color "Green"
}
elseif ($config['ELASTIC_IP']) {
    Write-StatusLine "Elastic IP" "$($config['ELASTIC_IP']) (configured)" -Color "Yellow"
}
else {
    Write-StatusLine "Public IP" "Not assigned" -Color "Yellow"
}

if ($config['DOMAIN_NAME'] -and $config['DOMAIN_NAME'] -ne '') {
    Write-StatusLine "Domain" $config['DOMAIN_NAME'] -Color "Green"
}

$publicUrl = Get-PublicUrl -Config $config
if ($publicUrl) {
    Write-StatusLine "Application URL" $publicUrl
}

# -----------------------------------------------------------------------------
# Display Health Status (if running)
# -----------------------------------------------------------------------------

if ($instanceState -eq "running") {
    Write-StatusHeader "Application Health"
    
    if ($publicUrl) {
        Write-Host "  Checking health endpoint..." -ForegroundColor Gray
        $health = Get-HealthStatus -Url $publicUrl
        
        Write-StatusLine "Health Status" $health.Status.ToUpper() -Color (Get-HealthColor $health.Status)
        Write-StatusLine "Health Endpoint" "$publicUrl/health"
        
        if ($health.Status -eq "healthy") {
            Write-StatusLine "Message" $health.Message -Color "Green"
        }
        elseif ($health.Status -eq "unreachable") {
            Write-Host ""
            Write-Host "  The application is not responding. This could mean:" -ForegroundColor Yellow
            Write-Host "    - Docker services are still starting up" -ForegroundColor Yellow
            Write-Host "    - The application crashed" -ForegroundColor Yellow
            Write-Host "    - Network/firewall issues" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "  Troubleshooting:" -ForegroundColor Cyan
            Write-Host "    1. SSH to instance and check Docker status:"
            Write-Host "       ssh -i ~/.ssh/sedimental-key.pem ubuntu@$publicIp"
            Write-Host "       docker compose -f /data/docker-compose.prod.yml ps"
            Write-Host ""
            Write-Host "    2. View application logs:"
            Write-Host "       docker compose -f /data/docker-compose.prod.yml logs"
        }
    }
    else {
        Write-StatusLine "Health Status" "UNKNOWN" -Color "Yellow"
        Write-Host "  No URL configured - cannot check health endpoint" -ForegroundColor Yellow
    }
}

# -----------------------------------------------------------------------------
# Display EBS Volume Status
# -----------------------------------------------------------------------------

Write-StatusHeader "EBS Volume Status"

if ($volumes -and $volumes.Count -gt 0) {
    $totalSize = 0
    foreach ($volume in $volumes) {
        $volumeId = $volume.VolumeId
        $volumeSize = $volume.Size
        $volumeState = $volume.State
        $attachmentState = if ($volume.Attachments.Count -gt 0) { 
            $volume.Attachments[0].State 
        } else { 
            "detached" 
        }
        $deviceName = if ($volume.Attachments.Count -gt 0) { 
            $volume.Attachments[0].Device 
        } else { 
            "N/A" 
        }
        
        $totalSize += $volumeSize
        
        Write-StatusLine "Volume ID" $volumeId
        Write-StatusLine "Size" "$volumeSize GB"
        Write-StatusLine "Volume State" $volumeState
        Write-StatusLine "Attachment" $attachmentState -Color (Get-AttachmentColor $attachmentState)
        Write-StatusLine "Device" $deviceName
        
        if ($volumes.Count -gt 1) {
            Write-Host ""
        }
    }
}
else {
    Write-Host "  No EBS volumes found attached to this instance" -ForegroundColor Yellow
    Write-Host "  This may indicate a configuration issue" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# Display Cost Estimation
# -----------------------------------------------------------------------------

Write-StatusHeader "Cost Estimation (Current Billing Period)"

$volumeSize = if ($volumes -and $volumes.Count -gt 0) { 
    ($volumes | Measure-Object -Property Size -Sum).Sum 
} else { 
    50  # Default assumption
}

$costs = Get-EstimatedCosts `
    -InstanceType $instanceType `
    -VolumeSizeGB $volumeSize `
    -LaunchTime $launchTime `
    -InstanceState $instanceState

Write-Host ""
Write-Host "  Pricing (approximate, us-west-2):" -ForegroundColor Gray
Write-StatusLine "Instance Rate" "`$$($costs.InstanceHourlyRate)/hour ($instanceType)"
Write-StatusLine "EBS Storage" "`$$([math]::Round($costs.EBSMonthlyRate, 2))/month ($volumeSize GB)"

if ($instanceState -eq "running") {
    Write-Host ""
    Write-Host "  Current Session:" -ForegroundColor Gray
    Write-StatusLine "Running Time" "$($costs.RunningHours) hours"
    Write-StatusLine "Compute Cost" "`$$($costs.ComputeCost)" -Color "Cyan"
}

Write-Host ""
Write-Host "  This Billing Period (estimated):" -ForegroundColor Gray
Write-StatusLine "EBS Storage" "`$$($costs.EBSCostThisMonth)"

if ($instanceState -ne "running" -and $costs.EIPCostEstimate -gt 0) {
    Write-StatusLine "Elastic IP" "`$$($costs.EIPCostEstimate) (charged when instance stopped)" -Color "Yellow"
}

$totalEstimate = $costs.ComputeCost + $costs.EBSCostThisMonth + $costs.EIPCostEstimate
Write-StatusLine "Total Estimate" "`$$([math]::Round($totalEstimate, 2))" -Color "Cyan"

Write-Host ""
Write-Host "  Note: Actual costs may vary. Check AWS Cost Explorer for accurate billing." -ForegroundColor Gray

# -----------------------------------------------------------------------------
# Display Quick Actions
# -----------------------------------------------------------------------------

Write-StatusHeader "Quick Actions"

if ($instanceState -eq "running") {
    Write-Host "  To stop the instance and save costs:" -ForegroundColor Cyan
    Write-Host "    .\stop-instance.ps1"
    Write-Host ""
    if ($publicUrl) {
        Write-Host "  To access the application:" -ForegroundColor Cyan
        Write-Host "    $publicUrl"
    }
}
elseif ($instanceState -eq "stopped") {
    Write-Host "  To start the instance:" -ForegroundColor Cyan
    Write-Host "    .\start-instance.ps1"
}
elseif ($instanceState -eq "pending") {
    Write-Host "  Instance is starting up. Please wait..." -ForegroundColor Yellow
    Write-Host "  Run this script again in a few minutes to check status."
}
elseif ($instanceState -eq "stopping") {
    Write-Host "  Instance is shutting down. Please wait..." -ForegroundColor Yellow
    Write-Host "  Run this script again in a few minutes to check status."
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
