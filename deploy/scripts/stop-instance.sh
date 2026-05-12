#!/bin/bash
# =============================================================================
# Sedimental EC2 GPU Instance - Stop Script (Bash)
# =============================================================================
# This script stops the Sedimental EC2 GPU instance to save costs when not in
# use. The EBS volume and Elastic IP persist, so data is preserved and the
# instance can be started again with the same IP address.
#
# Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
#
# Usage:
#   ./stop-instance.sh
#   ./stop-instance.sh /path/to/config.env
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - config.env file with INSTANCE_ID, REGION, and AWS_PROFILE
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Color Output Helpers
# -----------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_error() {
    echo -e "${RED}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

print_info() {
    echo -e "${CYAN}$1${NC}"
}

# -----------------------------------------------------------------------------
# Script Directory Detection
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-$SCRIPT_DIR/config.env}"

# -----------------------------------------------------------------------------
# Configuration Loading
# -----------------------------------------------------------------------------

load_config() {
    local config_file="$1"
    
    if [[ ! -f "$config_file" ]]; then
        echo ""
        print_error "ERROR: Configuration file not found: $config_file"
        echo ""
        print_warning "To fix this:"
        echo "  1. Copy config.env.example to config.env:"
        echo "     cp $SCRIPT_DIR/config.env.example $SCRIPT_DIR/config.env"
        echo ""
        echo "  2. Deploy the CloudFormation stack (if not already done)"
        echo ""
        echo "  3. Fill in the values from CloudFormation outputs:"
        echo "     - INSTANCE_ID: From stack output 'InstanceId'"
        echo "     - CONFIG_BUCKET: From stack output 'ConfigBucketName'"
        echo "     - ELASTIC_IP: From stack output 'ElasticIP'"
        echo ""
        exit 1
    fi
    
    # Read config file line by line
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        # Skip empty lines and comments
        key=$(echo "$key" | xargs)  # Trim whitespace
        if [[ -z "$key" || "$key" == \#* ]]; then
            continue
        fi
        
        # Remove any inline comments and trim
        value=$(echo "$value" | sed 's/#.*//' | xargs)
        
        # Export the variable
        export "$key=$value"
    done < "$config_file"
}

validate_config() {
    local missing=()
    
    [[ -z "$AWS_PROFILE" ]] && missing+=("AWS_PROFILE")
    [[ -z "$INSTANCE_ID" ]] && missing+=("INSTANCE_ID")
    [[ -z "$REGION" ]] && missing+=("REGION")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo ""
        print_error "ERROR: Missing required configuration values:"
        for key in "${missing[@]}"; do
            print_error "  - $key"
        done
        echo ""
        print_warning "Please update your config.env file with values from CloudFormation outputs."
        echo ""
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# AWS CLI Helpers
# -----------------------------------------------------------------------------

get_instance_state() {
    local instance_id="$1"
    local region="$2"
    local profile="$3"
    
    local result
    result=$(aws ec2 describe-instances \
        --instance-ids "$instance_id" \
        --region "$region" \
        --profile "$profile" \
        --query 'Reservations[0].Instances[0].State.Name' \
        --output text 2>&1)
    
    if [[ $? -ne 0 ]]; then
        echo ""
        print_error "ERROR: Failed to get instance state"
        print_error "Details: $result"
        echo ""
        print_warning "Troubleshooting:"
        echo "  1. Verify AWS CLI is installed: aws --version"
        echo "  2. Verify AWS profile exists: aws configure list --profile $profile"
        echo "  3. Verify instance ID is correct: $instance_id"
        echo "  4. Verify region is correct: $region"
        echo ""
        exit 1
    fi
    
    echo "$result" | tr -d '[:space:]'
}

# -----------------------------------------------------------------------------
# Instance Management Functions
# -----------------------------------------------------------------------------

stop_instance() {
    local instance_id="$1"
    local region="$2"
    local profile="$3"
    
    print_info "Stopping instance $instance_id..."
    
    local result
    result=$(aws ec2 stop-instances \
        --instance-ids "$instance_id" \
        --region "$region" \
        --profile "$profile" 2>&1)
    
    if [[ $? -ne 0 ]]; then
        echo ""
        print_error "ERROR: Failed to stop instance"
        print_error "Details: $result"
        echo ""
        print_warning "Troubleshooting:"
        echo "  1. Check AWS Console for instance status and any errors"
        echo "  2. Verify your AWS profile has ec2:StopInstances permission"
        echo "  3. Check if the instance is in a state that allows stopping"
        echo "  4. If instance is stuck, try force-stopping via AWS Console"
        echo ""
        exit 1
    fi
}

wait_for_stopped_state() {
    local instance_id="$1"
    local region="$2"
    local profile="$3"
    local timeout_seconds="$4"
    
    print_info "Waiting for instance to reach 'stopped' state..."
    
    local start_time=$(date +%s)
    local last_state=""
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [[ $elapsed -gt $timeout_seconds ]]; then
            echo ""
            print_error "ERROR: Instance failed to stop within $timeout_seconds seconds"
            echo ""
            print_warning "Troubleshooting:"
            echo "  1. Check AWS Console for instance status and any errors"
            echo "  2. The instance may be stuck - try force-stopping via AWS Console"
            echo "  3. Check CloudWatch logs for any issues during shutdown"
            echo "  4. If the instance has a stuck process, you may need to force stop"
            echo ""
            print_warning "To force stop via AWS CLI:"
            echo "  aws ec2 stop-instances --instance-ids $instance_id --force --region $region --profile $profile"
            echo ""
            exit 1
        fi
        
        local state
        state=$(get_instance_state "$instance_id" "$region" "$profile")
        
        if [[ "$state" != "$last_state" ]]; then
            echo "  Instance state: $state (elapsed: ${elapsed}s)"
            last_state="$state"
        fi
        
        if [[ "$state" == "stopped" ]]; then
            print_success "  Instance is now stopped"
            return
        fi
        
        sleep 5
    done
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

echo ""
print_info "============================================"
print_info "  Sedimental EC2 GPU Instance - Stop"
print_info "============================================"
echo ""

# Load and validate configuration
print_info "Loading configuration from $CONFIG_FILE..."
load_config "$CONFIG_FILE"
validate_config

# Export AWS_PROFILE for any child processes
export AWS_PROFILE

echo "  AWS Profile: $AWS_PROFILE"
echo "  Instance ID: $INSTANCE_ID"
echo "  Region: $REGION"
echo ""

# Get timeout value (with default)
STOP_TIMEOUT="${STOP_TIMEOUT:-120}"

# Check current instance state
print_info "Checking current instance state..."
current_state=$(get_instance_state "$INSTANCE_ID" "$REGION" "$AWS_PROFILE")

echo "  Current state: $current_state"
echo ""

# Handle already stopped instance
if [[ "$current_state" == "stopped" ]]; then
    print_success "Instance is already stopped."
    echo ""
    print_success "============================================"
    print_success "  Instance Status: STOPPED"
    print_success "============================================"
    echo ""
    print_info "No charges are being incurred for compute time."
    print_warning "Note: EBS storage charges still apply while the volume exists."
    echo ""
    print_info "To start the instance again:"
    print_info "  ./start-instance.sh"
    echo ""
    exit 0
fi

# Check if instance is in a stoppable state
if [[ "$current_state" == "stopping" ]]; then
    print_warning "Instance is already stopping. Waiting for it to stop..."
    echo ""
elif [[ "$current_state" == "pending" ]]; then
    print_warning "WARNING: Instance is in 'pending' state (starting up)."
    print_warning "It's recommended to wait for the instance to fully start before stopping."
    echo ""
    print_warning "Do you want to stop it anyway? This may cause issues."
    read -p "Continue? (y/N) " response
    if [[ "$response" != "y" && "$response" != "Y" ]]; then
        print_warning "Aborted."
        exit 0
    fi
    echo ""
elif [[ "$current_state" == "terminated" ]]; then
    print_error "ERROR: Instance has been terminated and cannot be stopped."
    echo ""
    print_warning "A terminated instance is permanently deleted."
    print_warning "You will need to redeploy the CloudFormation stack to create a new instance."
    echo ""
    exit 1
elif [[ "$current_state" != "running" ]]; then
    print_warning "WARNING: Instance is in unexpected state: $current_state"
    print_warning "Attempting to stop anyway..."
    echo ""
fi

# Stop the instance (if not already stopping)
if [[ "$current_state" != "stopping" ]]; then
    stop_instance "$INSTANCE_ID" "$REGION" "$AWS_PROFILE"
fi

# Wait for stopped state
wait_for_stopped_state "$INSTANCE_ID" "$REGION" "$AWS_PROFILE" "$STOP_TIMEOUT"

# Success!
echo ""
print_success "============================================"
print_success "  Instance Stopped Successfully!"
print_success "============================================"
echo ""
print_success "  Instance ID: $INSTANCE_ID"
print_success "  Status: STOPPED"
echo ""
print_info "Cost savings:"
echo "  - No compute charges while stopped"
echo "  - EBS storage charges continue (~\$0.08/GB/month for gp3)"
echo "  - Elastic IP charges apply if not attached to running instance (~\$0.005/hour)"
echo ""
print_info "Your data is preserved:"
echo "  - EBS volume with jobs database and results is retained"
echo "  - Elastic IP address is preserved for next start"
echo "  - TLS certificates are stored on the EBS volume"
echo ""
print_info "To start the instance again:"
print_info "  ./start-instance.sh"
echo ""
