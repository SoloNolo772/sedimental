#!/bin/bash
# =============================================================================
# Sedimental EC2 GPU Instance - Start Script (Bash)
# =============================================================================
# This script starts the Sedimental EC2 GPU instance and waits for it to become
# accessible. It uploads configuration files to S3 before starting the instance
# to ensure the latest docker-compose.prod.yml and Caddyfile are used.
#
# Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
#
# Usage:
#   ./start-instance.sh
#   ./start-instance.sh /path/to/config.env
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - config.env file with INSTANCE_ID, REGION, CONFIG_BUCKET, and AWS_PROFILE
#   - deploy/docker/docker-compose.prod.yml and Caddyfile exist
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
    
    # Source the config file (it's already in shell variable format)
    # But we need to handle it safely - read line by line
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
    [[ -z "$CONFIG_BUCKET" ]] && missing+=("CONFIG_BUCKET")
    
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

get_public_url() {
    if [[ -n "$DOMAIN_NAME" ]]; then
        echo "https://$DOMAIN_NAME"
    elif [[ -n "$ELASTIC_IP" ]]; then
        echo "https://$ELASTIC_IP"
    else
        # Try to get Elastic IP from AWS
        local ip
        ip=$(aws ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --region "$REGION" \
            --profile "$AWS_PROFILE" \
            --query 'Reservations[0].Instances[0].PublicIpAddress' \
            --output text 2>/dev/null)
        
        if [[ $? -eq 0 && -n "$ip" && "$ip" != "None" ]]; then
            echo "https://$ip"
        else
            echo "https://<elastic-ip>"
        fi
    fi
}

# -----------------------------------------------------------------------------
# S3 Upload Functions
# -----------------------------------------------------------------------------

upload_config_files() {
    local bucket="$1"
    local region="$2"
    local profile="$3"
    
    # Find the deploy/docker directory relative to the scripts directory
    local docker_dir="$(dirname "$SCRIPT_DIR")/docker"
    
    if [[ ! -d "$docker_dir" ]]; then
        echo ""
        print_error "ERROR: Docker configuration directory not found: $docker_dir"
        echo ""
        print_warning "Expected files:"
        echo "  - deploy/docker/docker-compose.prod.yml"
        echo "  - deploy/docker/Caddyfile"
        echo ""
        exit 1
    fi
    
    local compose_file="$docker_dir/docker-compose.prod.yml"
    local caddy_file="$docker_dir/Caddyfile"
    
    # Validate required files exist
    local missing_files=()
    [[ ! -f "$compose_file" ]] && missing_files+=("docker-compose.prod.yml")
    [[ ! -f "$caddy_file" ]] && missing_files+=("Caddyfile")
    
    if [[ ${#missing_files[@]} -gt 0 ]]; then
        echo ""
        print_error "ERROR: Missing configuration files in deploy/docker/:"
        for file in "${missing_files[@]}"; do
            print_error "  - $file"
        done
        echo ""
        exit 1
    fi
    
    print_info "Uploading configuration files to S3..."
    echo "  Bucket: $bucket"
    
    # Upload docker-compose.prod.yml
    echo "  Uploading docker-compose.prod.yml..."
    local result
    result=$(aws s3 cp "$compose_file" "s3://$bucket/docker-compose.prod.yml" \
        --region "$region" \
        --profile "$profile" 2>&1)
    
    if [[ $? -ne 0 ]]; then
        echo ""
        print_error "ERROR: Failed to upload docker-compose.prod.yml to S3"
        print_error "Details: $result"
        echo ""
        print_warning "Troubleshooting:"
        echo "  1. Verify the S3 bucket exists: $bucket"
        echo "  2. Verify your AWS profile has s3:PutObject permission"
        echo "  3. Check if the bucket name matches CloudFormation output 'ConfigBucketName'"
        echo ""
        exit 1
    fi
    
    # Upload Caddyfile
    echo "  Uploading Caddyfile..."
    result=$(aws s3 cp "$caddy_file" "s3://$bucket/Caddyfile" \
        --region "$region" \
        --profile "$profile" 2>&1)
    
    if [[ $? -ne 0 ]]; then
        echo ""
        print_error "ERROR: Failed to upload Caddyfile to S3"
        print_error "Details: $result"
        echo ""
        exit 1
    fi
    
    print_success "  Configuration files uploaded successfully"
    echo ""
}

# -----------------------------------------------------------------------------
# Instance Management Functions
# -----------------------------------------------------------------------------

start_instance() {
    local instance_id="$1"
    local region="$2"
    local profile="$3"
    
    print_info "Starting instance $instance_id..."
    
    local result
    result=$(aws ec2 start-instances \
        --instance-ids "$instance_id" \
        --region "$region" \
        --profile "$profile" 2>&1)
    
    if [[ $? -ne 0 ]]; then
        echo ""
        print_error "ERROR: Failed to start instance"
        print_error "Details: $result"
        echo ""
        print_warning "Troubleshooting:"
        echo "  1. Check AWS Console for instance status and any errors"
        echo "  2. Verify your AWS profile has ec2:StartInstances permission"
        echo "  3. Check if the instance is in a state that allows starting"
        echo "  4. Verify service quotas allow GPU instance launch in $region"
        echo ""
        exit 1
    fi
}

wait_for_running_state() {
    local instance_id="$1"
    local region="$2"
    local profile="$3"
    local timeout_seconds="$4"
    
    print_info "Waiting for instance to reach 'running' state..."
    
    local start_time=$(date +%s)
    local last_state=""
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [[ $elapsed -gt $timeout_seconds ]]; then
            echo ""
            print_error "ERROR: Instance failed to start within $timeout_seconds seconds"
            echo ""
            print_warning "Troubleshooting:"
            echo "  1. Check AWS Console for instance status and any errors"
            echo "  2. Review CloudWatch logs for user data script errors"
            echo "  3. Try stopping and starting the instance manually"
            echo "  4. Check if there are capacity issues in the region"
            echo ""
            exit 1
        fi
        
        local state
        state=$(get_instance_state "$instance_id" "$region" "$profile")
        
        if [[ "$state" != "$last_state" ]]; then
            echo "  Instance state: $state (elapsed: ${elapsed}s)"
            last_state="$state"
        fi
        
        if [[ "$state" == "running" ]]; then
            print_success "  Instance is now running"
            return
        fi
        
        sleep 5
    done
}

wait_for_health_check() {
    local url="$1"
    local timeout_seconds="$2"
    local interval_seconds="$3"
    
    local health_url="$url/health"
    print_info "Waiting for application health check..."
    echo "  Health endpoint: $health_url"
    
    local start_time=$(date +%s)
    local attempts=0
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        ((attempts++))
        
        if [[ $elapsed -gt $timeout_seconds ]]; then
            echo ""
            print_error "ERROR: Health check failed after $timeout_seconds seconds ($attempts attempts)"
            echo ""
            print_warning "The instance is running but the application is not responding."
            echo ""
            print_warning "Troubleshooting:"
            echo "  1. SSH to instance and check Docker status:"
            echo "     ssh -i ~/.ssh/sedimental-key.pem ubuntu@<elastic-ip>"
            echo "     docker compose -f /data/docker-compose.prod.yml ps"
            echo ""
            echo "  2. View application logs:"
            echo "     docker compose -f /data/docker-compose.prod.yml logs"
            echo ""
            echo "  3. Check user data script logs:"
            echo "     sudo cat /var/log/user-data.log"
            echo ""
            echo "  4. Verify GPU is detected:"
            echo "     nvidia-smi"
            echo ""
            exit 1
        fi
        
        # Use curl with -k to skip certificate verification (for self-signed certs in IP-only mode)
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" -k --connect-timeout 10 "$health_url" 2>/dev/null || echo "000")
        
        if [[ "$http_code" == "200" ]]; then
            print_success "  Health check passed (attempt $attempts, elapsed: ${elapsed}s)"
            return
        fi
        
        # Print progress every 3 attempts
        if [[ $((attempts % 3)) -eq 0 ]]; then
            echo "  Waiting... (attempt $attempts, elapsed: ${elapsed}s)"
        fi
        
        sleep "$interval_seconds"
    done
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

echo ""
print_info "============================================"
print_info "  Sedimental EC2 GPU Instance - Start"
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
echo "  Config Bucket: $CONFIG_BUCKET"
echo ""

# Get timeout values (with defaults)
START_TIMEOUT="${START_TIMEOUT:-300}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-180}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-10}"

# Check current instance state
print_info "Checking current instance state..."
current_state=$(get_instance_state "$INSTANCE_ID" "$REGION" "$AWS_PROFILE")

echo "  Current state: $current_state"
echo ""

# Handle already running instance
if [[ "$current_state" == "running" ]]; then
    public_url=$(get_public_url)
    
    print_success "Instance is already running!"
    echo ""
    print_success "============================================"
    print_success "  Application URL: $public_url"
    print_success "  Health Check: $public_url/health"
    print_success "============================================"
    echo ""
    print_warning "To update configuration files, stop the instance first,"
    print_warning "then start it again to pull the latest configs from S3."
    echo ""
    exit 0
fi

# Check if instance is in a startable state
if [[ "$current_state" != "stopped" && "$current_state" != "stopping" ]]; then
    print_warning "WARNING: Instance is in '$current_state' state."
    print_warning "Instance must be 'stopped' to start. Current state may require waiting."
    echo ""
    
    if [[ "$current_state" == "pending" ]]; then
        print_info "Instance is already starting. Waiting for it to become running..."
    elif [[ "$current_state" == "stopping" ]]; then
        print_warning "Instance is stopping. Please wait for it to stop, then try again."
        exit 1
    else
        print_error "Unexpected state. Please check AWS Console."
        exit 1
    fi
fi

# Upload configuration files to S3 (before starting instance)
upload_config_files "$CONFIG_BUCKET" "$REGION" "$AWS_PROFILE"

# Start the instance (if stopped)
if [[ "$current_state" == "stopped" ]]; then
    start_instance "$INSTANCE_ID" "$REGION" "$AWS_PROFILE"
fi

# Wait for running state
wait_for_running_state "$INSTANCE_ID" "$REGION" "$AWS_PROFILE" "$START_TIMEOUT"

# Get public URL for health check
public_url=$(get_public_url)

# Wait for health check
wait_for_health_check "$public_url" "$HEALTH_CHECK_TIMEOUT" "$HEALTH_CHECK_INTERVAL"

# Success!
echo ""
print_success "============================================"
print_success "  Instance Started Successfully!"
print_success "============================================"
echo ""
print_success "  Application URL: $public_url"
print_success "  Health Check: $public_url/health"
echo ""

if [[ -z "$DOMAIN_NAME" ]]; then
    print_warning "NOTE: Using IP-only mode with self-signed certificate."
    print_warning "Your browser will show a security warning - this is expected."
    print_warning "To use a custom domain with valid certificate, configure"
    print_warning "DOMAIN_NAME in config.env and update DNS to point to the Elastic IP."
    echo ""
fi

print_info "To stop the instance and save costs when not in use:"
print_info "  ./stop-instance.sh"
echo ""
