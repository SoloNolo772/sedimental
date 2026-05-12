#!/bin/bash
# =============================================================================
# Sedimental EC2 GPU Instance - Status Script (Bash)
# =============================================================================
# This script reports the current status of the Sedimental EC2 GPU instance,
# including instance state, health check status, EBS volume attachment, and
# estimated costs for the current billing period.
#
# Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
#
# Usage:
#   ./status-instance.sh
#   ./status-instance.sh /path/to/config.env
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - config.env file with INSTANCE_ID, REGION, and AWS_PROFILE
#   - jq installed for JSON parsing
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Color Definitions
# -----------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-$SCRIPT_DIR/config.env}"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${CYAN}--------------------------------------------${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}--------------------------------------------${NC}"
}

print_status_line() {
    local label="$1"
    local value="$2"
    local color="${3:-$WHITE}"
    printf "  %-20s : ${color}%s${NC}\n" "$label" "$value"
}

get_state_color() {
    case "$1" in
        running)    echo "$GREEN" ;;
        stopped)    echo "$YELLOW" ;;
        pending)    echo "$CYAN" ;;
        stopping)   echo "$CYAN" ;;
        terminated) echo "$RED" ;;
        *)          echo "$WHITE" ;;
    esac
}

get_health_color() {
    case "$1" in
        healthy)     echo "$GREEN" ;;
        unhealthy)   echo "$RED" ;;
        unreachable) echo "$YELLOW" ;;
        *)           echo "$WHITE" ;;
    esac
}

get_attachment_color() {
    case "$1" in
        attached) echo "$GREEN" ;;
        detached) echo "$YELLOW" ;;
        *)        echo "$WHITE" ;;
    esac
}

# -----------------------------------------------------------------------------
# Configuration Loading
# -----------------------------------------------------------------------------

load_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo ""
        echo -e "${RED}ERROR: Configuration file not found: $CONFIG_FILE${NC}"
        echo ""
        echo -e "${YELLOW}To fix this:${NC}"
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
    
    # Source the config file (handles KEY=value format)
    # Use a subshell to avoid polluting the environment with comments
    while IFS='=' read -r key value; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        # Export the variable
        export "$key=$value"
    done < "$CONFIG_FILE"
}

validate_config() {
    local missing=()
    
    [[ -z "$AWS_PROFILE" ]] && missing+=("AWS_PROFILE")
    [[ -z "$INSTANCE_ID" ]] && missing+=("INSTANCE_ID")
    [[ -z "$REGION" ]] && missing+=("REGION")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo ""
        echo -e "${RED}ERROR: Missing required configuration values:${NC}"
        for key in "${missing[@]}"; do
            echo -e "${RED}  - $key${NC}"
        done
        echo ""
        echo -e "${YELLOW}Please update your config.env file with values from CloudFormation outputs.${NC}"
        echo ""
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# AWS CLI Functions
# -----------------------------------------------------------------------------

get_instance_details() {
    local result
    result=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output json 2>&1)
    
    if [[ $? -ne 0 ]]; then
        echo ""
        echo -e "${RED}ERROR: Failed to get instance details${NC}"
        echo -e "${RED}Details: $result${NC}"
        echo ""
        echo -e "${YELLOW}Troubleshooting:${NC}"
        echo "  1. Verify AWS CLI is installed: aws --version"
        echo "  2. Verify AWS profile exists: aws configure list --profile $AWS_PROFILE"
        echo "  3. Verify instance ID is correct: $INSTANCE_ID"
        echo "  4. Verify region is correct: $REGION"
        echo ""
        exit 1
    fi
    
    echo "$result"
}

get_volume_details() {
    aws ec2 describe-volumes \
        --filters "Name=attachment.instance-id,Values=$INSTANCE_ID" \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output json 2>/dev/null || echo '{"Volumes":[]}'
}

get_public_url() {
    if [[ -n "$DOMAIN_NAME" ]]; then
        echo "https://$DOMAIN_NAME"
    elif [[ -n "$ELASTIC_IP" ]]; then
        echo "https://$ELASTIC_IP"
    else
        echo ""
    fi
}

check_health() {
    local url="$1"
    
    if [[ -z "$url" ]]; then
        echo "unknown|No URL configured"
        return
    fi
    
    local health_url="$url/health"
    local response
    local http_code
    
    # Use curl with timeout and ignore certificate errors (self-signed certs)
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -k --connect-timeout 10 --max-time 15 "$health_url" 2>/dev/null || echo "000")
    
    if [[ "$http_code" == "200" ]]; then
        echo "healthy|Application is responding"
    elif [[ "$http_code" == "000" ]]; then
        echo "unreachable|Health endpoint not responding"
    else
        echo "unhealthy|Unexpected status code: $http_code"
    fi
}

# -----------------------------------------------------------------------------
# Cost Estimation Functions
# -----------------------------------------------------------------------------

get_hourly_rate() {
    local instance_type="$1"
    
    # Approximate hourly costs (us-west-2 pricing, may vary by region)
    case "$instance_type" in
        g4dn.xlarge)  echo "0.526" ;;
        g4dn.2xlarge) echo "0.752" ;;
        g5.xlarge)    echo "1.006" ;;
        g5.2xlarge)   echo "1.212" ;;
        *)            echo "0.526" ;;  # Default to g4dn.xlarge
    esac
}

calculate_running_hours() {
    local launch_time="$1"
    
    if [[ -z "$launch_time" ]]; then
        echo "0"
        return
    fi
    
    local launch_epoch
    local now_epoch
    local diff_seconds
    local diff_hours
    
    # Convert launch time to epoch (handle ISO 8601 format)
    launch_epoch=$(date -d "$launch_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${launch_time%%.*}" +%s 2>/dev/null || echo "0")
    now_epoch=$(date +%s)
    
    if [[ "$launch_epoch" == "0" ]]; then
        echo "0"
        return
    fi
    
    diff_seconds=$((now_epoch - launch_epoch))
    diff_hours=$(( (diff_seconds + 3599) / 3600 ))  # Round up
    
    echo "$diff_hours"
}

format_uptime() {
    local launch_time="$1"
    
    if [[ -z "$launch_time" ]]; then
        echo "N/A"
        return
    fi
    
    local launch_epoch
    local now_epoch
    local diff_seconds
    
    launch_epoch=$(date -d "$launch_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${launch_time%%.*}" +%s 2>/dev/null || echo "0")
    now_epoch=$(date +%s)
    
    if [[ "$launch_epoch" == "0" ]]; then
        echo "N/A"
        return
    fi
    
    diff_seconds=$((now_epoch - launch_epoch))
    
    local days=$((diff_seconds / 86400))
    local hours=$(( (diff_seconds % 86400) / 3600 ))
    local minutes=$(( (diff_seconds % 3600) / 60 ))
    
    echo "${days}d ${hours}h ${minutes}m"
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Sedimental EC2 GPU Instance - Status${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Check for jq
if ! command -v jq &> /dev/null; then
    echo -e "${RED}ERROR: jq is required but not installed.${NC}"
    echo "Please install jq:"
    echo "  - Ubuntu/Debian: sudo apt-get install jq"
    echo "  - macOS: brew install jq"
    echo "  - Amazon Linux: sudo yum install jq"
    exit 1
fi

# Load and validate configuration
echo -e "${GRAY}Loading configuration...${NC}"
load_config
validate_config

# Export AWS_PROFILE for any child processes
export AWS_PROFILE

# Get instance details
echo -e "${GRAY}Fetching instance details...${NC}"
INSTANCE_DATA=$(get_instance_details)

# Parse instance information
INSTANCE_STATE=$(echo "$INSTANCE_DATA" | jq -r '.Reservations[0].Instances[0].State.Name')
INSTANCE_TYPE=$(echo "$INSTANCE_DATA" | jq -r '.Reservations[0].Instances[0].InstanceType')
PUBLIC_IP=$(echo "$INSTANCE_DATA" | jq -r '.Reservations[0].Instances[0].PublicIpAddress // empty')
LAUNCH_TIME=$(echo "$INSTANCE_DATA" | jq -r '.Reservations[0].Instances[0].LaunchTime // empty')

# Get volume details
VOLUME_DATA=$(get_volume_details)

# -----------------------------------------------------------------------------
# Display Instance Status
# -----------------------------------------------------------------------------

print_header "Instance Status"
print_status_line "Instance ID" "$INSTANCE_ID"
print_status_line "Instance Type" "$INSTANCE_TYPE"
print_status_line "Region" "$REGION"
print_status_line "State" "$(echo "$INSTANCE_STATE" | tr '[:lower:]' '[:upper:]')" "$(get_state_color "$INSTANCE_STATE")"

if [[ -n "$LAUNCH_TIME" && "$INSTANCE_STATE" == "running" ]]; then
    UPTIME=$(format_uptime "$LAUNCH_TIME")
    print_status_line "Uptime" "$UPTIME"
    # Format launch time for display
    LAUNCH_DISPLAY=$(date -d "$LAUNCH_TIME" "+%Y-%m-%d %H:%M:%S UTC" 2>/dev/null || echo "$LAUNCH_TIME")
    print_status_line "Launch Time" "$LAUNCH_DISPLAY"
fi

# -----------------------------------------------------------------------------
# Display Network Status
# -----------------------------------------------------------------------------

print_header "Network Status"

if [[ -n "$PUBLIC_IP" ]]; then
    print_status_line "Public IP" "$PUBLIC_IP" "$GREEN"
elif [[ -n "$ELASTIC_IP" ]]; then
    print_status_line "Elastic IP" "$ELASTIC_IP (configured)" "$YELLOW"
else
    print_status_line "Public IP" "Not assigned" "$YELLOW"
fi

if [[ -n "$DOMAIN_NAME" ]]; then
    print_status_line "Domain" "$DOMAIN_NAME" "$GREEN"
fi

PUBLIC_URL=$(get_public_url)
if [[ -n "$PUBLIC_URL" ]]; then
    print_status_line "Application URL" "$PUBLIC_URL"
fi

# -----------------------------------------------------------------------------
# Display Health Status (if running)
# -----------------------------------------------------------------------------

if [[ "$INSTANCE_STATE" == "running" ]]; then
    print_header "Application Health"
    
    if [[ -n "$PUBLIC_URL" ]]; then
        echo -e "  ${GRAY}Checking health endpoint...${NC}"
        HEALTH_RESULT=$(check_health "$PUBLIC_URL")
        HEALTH_STATUS=$(echo "$HEALTH_RESULT" | cut -d'|' -f1)
        HEALTH_MESSAGE=$(echo "$HEALTH_RESULT" | cut -d'|' -f2)
        
        print_status_line "Health Status" "$(echo "$HEALTH_STATUS" | tr '[:lower:]' '[:upper:]')" "$(get_health_color "$HEALTH_STATUS")"
        print_status_line "Health Endpoint" "$PUBLIC_URL/health"
        
        if [[ "$HEALTH_STATUS" == "healthy" ]]; then
            print_status_line "Message" "$HEALTH_MESSAGE" "$GREEN"
        elif [[ "$HEALTH_STATUS" == "unreachable" ]]; then
            echo ""
            echo -e "  ${YELLOW}The application is not responding. This could mean:${NC}"
            echo -e "  ${YELLOW}  - Docker services are still starting up${NC}"
            echo -e "  ${YELLOW}  - The application crashed${NC}"
            echo -e "  ${YELLOW}  - Network/firewall issues${NC}"
            echo ""
            echo -e "  ${CYAN}Troubleshooting:${NC}"
            echo "    1. SSH to instance and check Docker status:"
            echo "       ssh -i ~/.ssh/sedimental-key.pem ubuntu@${PUBLIC_IP:-$ELASTIC_IP}"
            echo "       docker compose -f /data/docker-compose.prod.yml ps"
            echo ""
            echo "    2. View application logs:"
            echo "       docker compose -f /data/docker-compose.prod.yml logs"
        fi
    else
        print_status_line "Health Status" "UNKNOWN" "$YELLOW"
        echo -e "  ${YELLOW}No URL configured - cannot check health endpoint${NC}"
    fi
fi

# -----------------------------------------------------------------------------
# Display EBS Volume Status
# -----------------------------------------------------------------------------

print_header "EBS Volume Status"

VOLUME_COUNT=$(echo "$VOLUME_DATA" | jq '.Volumes | length')

if [[ "$VOLUME_COUNT" -gt 0 ]]; then
    TOTAL_SIZE=0
    
    for i in $(seq 0 $((VOLUME_COUNT - 1))); do
        VOLUME_ID=$(echo "$VOLUME_DATA" | jq -r ".Volumes[$i].VolumeId")
        VOLUME_SIZE=$(echo "$VOLUME_DATA" | jq -r ".Volumes[$i].Size")
        VOLUME_STATE=$(echo "$VOLUME_DATA" | jq -r ".Volumes[$i].State")
        ATTACHMENT_STATE=$(echo "$VOLUME_DATA" | jq -r ".Volumes[$i].Attachments[0].State // \"detached\"")
        DEVICE_NAME=$(echo "$VOLUME_DATA" | jq -r ".Volumes[$i].Attachments[0].Device // \"N/A\"")
        
        TOTAL_SIZE=$((TOTAL_SIZE + VOLUME_SIZE))
        
        print_status_line "Volume ID" "$VOLUME_ID"
        print_status_line "Size" "$VOLUME_SIZE GB"
        print_status_line "Volume State" "$VOLUME_STATE"
        print_status_line "Attachment" "$ATTACHMENT_STATE" "$(get_attachment_color "$ATTACHMENT_STATE")"
        print_status_line "Device" "$DEVICE_NAME"
        
        if [[ "$VOLUME_COUNT" -gt 1 && $i -lt $((VOLUME_COUNT - 1)) ]]; then
            echo ""
        fi
    done
else
    echo -e "  ${YELLOW}No EBS volumes found attached to this instance${NC}"
    echo -e "  ${YELLOW}This may indicate a configuration issue${NC}"
    TOTAL_SIZE=50  # Default assumption
fi

# -----------------------------------------------------------------------------
# Display Cost Estimation
# -----------------------------------------------------------------------------

print_header "Cost Estimation (Current Billing Period)"

HOURLY_RATE=$(get_hourly_rate "$INSTANCE_TYPE")
EBS_MONTHLY_RATE=$(echo "scale=2; 0.08 * $TOTAL_SIZE" | bc)
EIP_HOURLY_RATE="0.005"

echo ""
echo -e "  ${GRAY}Pricing (approximate, us-west-2):${NC}"
print_status_line "Instance Rate" "\$$HOURLY_RATE/hour ($INSTANCE_TYPE)"
print_status_line "EBS Storage" "\$$EBS_MONTHLY_RATE/month ($TOTAL_SIZE GB)"

COMPUTE_COST="0"
RUNNING_HOURS="0"

if [[ "$INSTANCE_STATE" == "running" && -n "$LAUNCH_TIME" ]]; then
    RUNNING_HOURS=$(calculate_running_hours "$LAUNCH_TIME")
    COMPUTE_COST=$(echo "scale=2; $RUNNING_HOURS * $HOURLY_RATE" | bc)
    
    echo ""
    echo -e "  ${GRAY}Current Session:${NC}"
    print_status_line "Running Time" "$RUNNING_HOURS hours"
    print_status_line "Compute Cost" "\$$COMPUTE_COST" "$CYAN"
fi

# Calculate billing period costs
DAY_OF_MONTH=$(date +%d | sed 's/^0//')
DAYS_IN_MONTH=$(date -d "$(date +%Y-%m-01) +1 month -1 day" +%d 2>/dev/null || date -v1d -v+1m -v-1d +%d 2>/dev/null || echo "30")
EBS_COST_THIS_MONTH=$(echo "scale=2; ($DAY_OF_MONTH / $DAYS_IN_MONTH) * 0.08 * $TOTAL_SIZE" | bc)

EIP_COST_ESTIMATE="0"
if [[ "$INSTANCE_STATE" != "running" ]]; then
    EIP_COST_ESTIMATE=$(echo "scale=2; $EIP_HOURLY_RATE * 24 * $DAY_OF_MONTH" | bc)
fi

echo ""
echo -e "  ${GRAY}This Billing Period (estimated):${NC}"
print_status_line "EBS Storage" "\$$EBS_COST_THIS_MONTH"

if [[ "$INSTANCE_STATE" != "running" && $(echo "$EIP_COST_ESTIMATE > 0" | bc -l) -eq 1 ]]; then
    print_status_line "Elastic IP" "\$$EIP_COST_ESTIMATE (charged when instance stopped)" "$YELLOW"
fi

TOTAL_ESTIMATE=$(echo "scale=2; $COMPUTE_COST + $EBS_COST_THIS_MONTH + $EIP_COST_ESTIMATE" | bc)
print_status_line "Total Estimate" "\$$TOTAL_ESTIMATE" "$CYAN"

echo ""
echo -e "  ${GRAY}Note: Actual costs may vary. Check AWS Cost Explorer for accurate billing.${NC}"

# -----------------------------------------------------------------------------
# Display Quick Actions
# -----------------------------------------------------------------------------

print_header "Quick Actions"

case "$INSTANCE_STATE" in
    running)
        echo -e "  ${CYAN}To stop the instance and save costs:${NC}"
        echo "    ./stop-instance.sh"
        echo ""
        if [[ -n "$PUBLIC_URL" ]]; then
            echo -e "  ${CYAN}To access the application:${NC}"
            echo "    $PUBLIC_URL"
        fi
        ;;
    stopped)
        echo -e "  ${CYAN}To start the instance:${NC}"
        echo "    ./start-instance.sh"
        ;;
    pending)
        echo -e "  ${YELLOW}Instance is starting up. Please wait...${NC}"
        echo "  Run this script again in a few minutes to check status."
        ;;
    stopping)
        echo -e "  ${YELLOW}Instance is shutting down. Please wait...${NC}"
        echo "  Run this script again in a few minutes to check status."
        ;;
esac

echo ""
echo -e "${CYAN}============================================${NC}"
echo ""
