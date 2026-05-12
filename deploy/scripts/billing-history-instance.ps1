# =============================================================================
# Temporary t2.nano Instance for Building AWS Billing History
# =============================================================================
# This script launches a minimal t2.nano instance to establish billing history
# with AWS. Run it for 1-2 weeks, pay the bill, then request GPU quota again.
#
# Cost: ~$0.0058/hour = ~$4.20/month (or ~$1.00 for 1 week)
#
# Usage:
#   .\billing-history-instance.ps1 -Action start
#   .\billing-history-instance.ps1 -Action status
#   .\billing-history-instance.ps1 -Action stop
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "status", "stop")]
    [string]$Action,
    
    [string]$Profile = "sedimental",
    [string]$Region = "us-west-2",
    [string]$KeyPairName = "sedimental-key"
)

$StackName = "billing-history-temp"

function Start-BillingInstance {
    Write-Host ""
    Write-Host "Creating temporary t2.nano instance for billing history..." -ForegroundColor Cyan
    Write-Host ""
    
    # Check if stack already exists
    $existingStack = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --profile $Profile `
        --region $Region 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Stack '$StackName' already exists." -ForegroundColor Yellow
        Write-Host "Run with -Action status to check it, or -Action stop to delete it." -ForegroundColor Yellow
        return
    }
    
    # Create a minimal CloudFormation template inline
    $template = @"
AWSTemplateFormatVersion: '2010-09-09'
Description: Temporary t2.nano instance for building AWS billing history
Parameters:
  KeyPairName:
    Type: AWS::EC2::KeyPair::KeyName
    Description: EC2 key pair for SSH access
Resources:
  BillingInstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: t2.nano
      ImageId: !Sub '{{resolve:ssm:/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id}}'
      KeyName: !Ref KeyPairName
      Tags:
        - Key: Name
          Value: billing-history-temp
        - Key: Purpose
          Value: Building AWS billing history for GPU quota approval
Outputs:
  InstanceId:
    Value: !Ref BillingInstance
  PublicIP:
    Value: !GetAtt BillingInstance.PublicIp
"@

    # Write template to temp file (UTF8 without BOM for CloudFormation compatibility)
    $tempFile = [System.IO.Path]::GetTempFileName() + ".yaml"
    [System.IO.File]::WriteAllText($tempFile, $template, [System.Text.UTF8Encoding]::new($false))
    
    # Create the stack
    Write-Host "Creating CloudFormation stack..." -ForegroundColor Cyan
    aws cloudformation create-stack `
        --stack-name $StackName `
        --template-body "file://$tempFile" `
        --parameters "ParameterKey=KeyPairName,ParameterValue=$KeyPairName" `
        --profile $Profile `
        --region $Region
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create stack." -ForegroundColor Red
        Remove-Item $tempFile -ErrorAction SilentlyContinue
        return
    }
    
    Remove-Item $tempFile -ErrorAction SilentlyContinue
    
    Write-Host "Waiting for instance to launch..." -ForegroundColor Cyan
    aws cloudformation wait stack-create-complete `
        --stack-name $StackName `
        --profile $Profile `
        --region $Region
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Billing History Instance Created!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "The instance is now running and generating billing history." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Cost: ~`$0.0058/hour (~`$0.14/day, ~`$1.00/week)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Let it run for 1-2 weeks"
    Write-Host "  2. Wait for your first AWS bill (or check Cost Explorer)"
    Write-Host "  3. Resubmit the GPU quota increase request"
    Write-Host "  4. Run: .\billing-history-instance.ps1 -Action stop"
    Write-Host ""
    
    # Show instance details
    Get-BillingInstanceStatus
}

function Get-BillingInstanceStatus {
    Write-Host ""
    Write-Host "Checking billing history instance status..." -ForegroundColor Cyan
    Write-Host ""
    
    $stackInfo = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --profile $Profile `
        --region $Region `
        --output json 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No billing history instance found." -ForegroundColor Yellow
        Write-Host "Run with -Action start to create one." -ForegroundColor Yellow
        return
    }
    
    $stack = $stackInfo | ConvertFrom-Json
    $status = $stack.Stacks[0].StackStatus
    
    Write-Host "Stack Status: $status" -ForegroundColor $(if ($status -eq "CREATE_COMPLETE") { "Green" } else { "Yellow" })
    
    if ($status -eq "CREATE_COMPLETE") {
        $outputs = $stack.Stacks[0].Outputs
        $instanceId = ($outputs | Where-Object { $_.OutputKey -eq "InstanceId" }).OutputValue
        $publicIp = ($outputs | Where-Object { $_.OutputKey -eq "PublicIP" }).OutputValue
        
        Write-Host "Instance ID: $instanceId"
        Write-Host "Public IP: $publicIp"
        
        # Get instance state
        $instanceInfo = aws ec2 describe-instances `
            --instance-ids $instanceId `
            --profile $Profile `
            --region $Region `
            --query 'Reservations[0].Instances[0].[State.Name,LaunchTime]' `
            --output json | ConvertFrom-Json
        
        $state = $instanceInfo[0]
        $launchTime = [DateTime]::Parse($instanceInfo[1])
        $runningTime = (Get-Date) - $launchTime
        
        Write-Host "State: $($state.ToUpper())" -ForegroundColor $(if ($state -eq "running") { "Green" } else { "Yellow" })
        Write-Host "Running for: $($runningTime.Days)d $($runningTime.Hours)h $($runningTime.Minutes)m"
        $estimatedCost = [math]::Round($runningTime.TotalHours * 0.0058, 2)
        Write-Host "Estimated cost so far: `$$estimatedCost"
    }
    
    Write-Host ""
}

function Stop-BillingInstance {
    Write-Host ""
    Write-Host "Deleting billing history instance..." -ForegroundColor Cyan
    Write-Host ""
    
    $existingStack = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --profile $Profile `
        --region $Region 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No billing history instance found." -ForegroundColor Yellow
        return
    }
    
    aws cloudformation delete-stack `
        --stack-name $StackName `
        --profile $Profile `
        --region $Region
    
    Write-Host "Waiting for stack deletion..." -ForegroundColor Cyan
    aws cloudformation wait stack-delete-complete `
        --stack-name $StackName `
        --profile $Profile `
        --region $Region
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Billing History Instance Deleted!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "The temporary instance has been terminated." -ForegroundColor Cyan
    Write-Host "No further charges will be incurred." -ForegroundColor Cyan
    Write-Host ""
}

# Main
switch ($Action) {
    "start"  { Start-BillingInstance }
    "status" { Get-BillingInstanceStatus }
    "stop"   { Stop-BillingInstance }
}
