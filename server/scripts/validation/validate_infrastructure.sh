#!/usr/bin/env bash
# Infrastructure Validation Script
# Validates entire home server infrastructure after deployment
# Version: 1.0.0

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="${DOMAIN:-example.com}"
CORE_VM_IP="${CORE_VM_IP:-192.168.1.100}"
AI_VM_IP="${AI_VM_IP:-192.168.1.101}"

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNED=0

# Functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_test() {
    echo -e "${YELLOW}[TEST]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}  ✓ PASS:${NC} $1"
    ((TESTS_PASSED++))
}

print_fail() {
    echo -e "${RED}  ✗ FAIL:${NC} $1"
    ((TESTS_FAILED++))
}

print_warn() {
    echo -e "${YELLOW}  ⚠ WARN:${NC} $1"
    ((TESTS_WARNED++))
}

print_info() {
    echo -e "${BLUE}  ℹ INFO:${NC} $1"
}

# Check command exists
check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Main validation
main() {
    print_header "🏠 Home Server Infrastructure Validation"
    
    echo "Domain: ${DOMAIN}"
    echo "Core Services VM: ${CORE_VM_IP}"
    echo "AI Desktop VM: ${AI_VM_IP}"
    echo ""
    
    # 1. Check prerequisites
    print_header "1️⃣  Prerequisites Check"
    
    print_test "Checking required commands..."
    for cmd in curl dig docker ssh; do
        if check_command "$cmd"; then
            print_pass "$cmd is installed"
        else
            print_fail "$cmd is not installed"
        fi
    done
    
    # 2. Network connectivity
    print_header "2️⃣  Network Connectivity"
    
    print_test "Pinging Core Services VM..."
    if ping -c 3 "${CORE_VM_IP}" &> /dev/null; then
        print_pass "Core Services VM is reachable"
    else
        print_fail "Cannot reach Core Services VM at ${CORE_VM_IP}"
    fi
    
    print_test "Pinging AI Desktop VM..."
    if ping -c 3 "${AI_VM_IP}" &> /dev/null; then
        print_pass "AI Desktop VM is reachable"
    else
        print_warn "Cannot reach AI Desktop VM at ${AI_VM_IP} (optional)"
    fi
    
    # 3. DNS resolution
    print_header "3️⃣  DNS Resolution"
    
    print_test "Resolving ${DOMAIN}..."
    if dig +short "${DOMAIN}" | grep -q .; then
        RESOLVED_IP=$(dig +short "${DOMAIN}" | head -1)
        print_pass "Domain resolves to ${RESOLVED_IP}"
        
        # Check if it's Cloudflare
        if echo "${RESOLVED_IP}" | grep -qE "^(104\.1[6-9]|104\.2[0-9]|104\.3[0-1]|172\.6[4-7])\."; then
            print_pass "Domain is behind Cloudflare (as expected)"
        else
            print_warn "Domain does not appear to be behind Cloudflare"
        fi
    else
        print_fail "Domain does not resolve"
    fi
    
    # 4. Docker services
    print_header "4️⃣  Docker Services"
    
    print_test "Checking Docker on Core Services VM..."
    if ssh -o ConnectTimeout=5 "root@${CORE_VM_IP}" "docker ps --format '{{.Names}}\t{{.Status}}'" &> /dev/null; then
        print_pass "Docker is running on Core Services VM"
        
        # Get container statuses
        CONTAINERS=$(ssh "root@${CORE_VM_IP}" "docker ps --format '{{.Names}}\t{{.Status}}'")
        
        # Check critical containers
        for container in traefik cloudflared authelia portainer; do
            if echo "${CONTAINERS}" | grep -q "^${container}"; then
                STATUS=$(echo "${CONTAINERS}" | grep "^${container}" | awk '{print $2}')
                if echo "${STATUS}" | grep -q "Up"; then
                    print_pass "${container} is running"
                else
                    print_fail "${container} is not healthy: ${STATUS}"
                fi
            else
                print_fail "${container} container not found"
            fi
        done
    else
        print_fail "Cannot connect to Docker on Core Services VM"
    fi
    
    # 5. Web services
    print_header "5️⃣  Web Services Accessibility"
    
    # Test critical services
    SERVICES=(
        "https://traefik.${DOMAIN}:Traefik Dashboard"
        "https://portainer.${DOMAIN}:Portainer"
        "https://auth.${DOMAIN}:Authelia"
    )
    
    for service_url in "${SERVICES[@]}"; do
        URL=$(echo "${service_url}" | cut -d: -f1-2)
        NAME=$(echo "${service_url}" | cut -d: -f3)
        
        print_test "Checking ${NAME}..."
        HTTP_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" --max-time 10 "${URL}" || echo "000")
        
        if [[ "${HTTP_CODE}" == "200" || "${HTTP_CODE}" == "302" || "${HTTP_CODE}" == "401" ]]; then
            print_pass "${NAME} is accessible (HTTP ${HTTP_CODE})"
        else
            print_fail "${NAME} returned HTTP ${HTTP_CODE}"
        fi
    done
    
    # 6. SSL certificates
    print_header "6️⃣  SSL/TLS Certificates"
    
    print_test "Checking SSL certificate for ${DOMAIN}..."
    CERT_INFO=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}:443" 2>/dev/null | openssl x509 -noout -dates 2>/dev/null || echo "")
    
    if [[ -n "${CERT_INFO}" ]]; then
        print_pass "SSL certificate is valid"
        
        EXPIRY=$(echo "${CERT_INFO}" | grep "notAfter" | cut -d= -f2)
        print_info "Certificate expires: ${EXPIRY}"
        
        # Check if cert is from Let's Encrypt
        ISSUER=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}:443" 2>/dev/null | openssl x509 -noout -issuer | grep -o "Let's Encrypt" || echo "")
        if [[ -n "${ISSUER}" ]]; then
            print_pass "Certificate is from Let's Encrypt"
        else
            print_warn "Certificate is not from Let's Encrypt"
        fi
    else
        print_fail "Cannot retrieve SSL certificate"
    fi
    
    # 7. NFS mounts
    print_header "7️⃣  NFS Mounts"
    
    print_test "Checking NFS mounts on Core Services VM..."
    NFS_MOUNTS=$(ssh "root@${CORE_VM_IP}" "mount | grep nfs" || echo "")
    
    if [[ -n "${NFS_MOUNTS}" ]]; then
        print_pass "NFS mounts are active"
        print_info "${NFS_MOUNTS}"
        
        # Test write permissions
        TEST_FILE="/mnt/pve_data_zfs/test_write_$(date +%s)"
        if ssh "root@${CORE_VM_IP}" "touch ${TEST_FILE} && rm ${TEST_FILE}" &> /dev/null; then
            print_pass "NFS mount is writable"
        else
            print_fail "NFS mount is not writable (permission issue)"
        fi
    else
        print_fail "No NFS mounts found"
    fi
    
    # 8. Backup validation
    print_header "8️⃣  Backup System"
    
    print_test "Checking rclone configuration..."
    if ssh "root@${CORE_VM_IP}" "command -v rclone" &> /dev/null; then
        print_pass "rclone is installed"
        
        if ssh "root@${CORE_VM_IP}" "rclone listremotes | grep -q gcs_backup_crypt" 2> /dev/null; then
            print_pass "Encrypted GCS remote is configured"
            
            # Test connection
            print_test "Testing GCS connection..."
            if ssh "root@${CORE_VM_IP}" "timeout 10 rclone lsd gcs_backup_crypt: --max-depth 1" &> /dev/null; then
                print_pass "Can connect to GCS backup bucket"
            else
                print_fail "Cannot connect to GCS backup bucket"
            fi
        else
            print_fail "GCS remote not configured"
        fi
    else
        print_fail "rclone is not installed"
    fi
    
    # 9. Optional: AI services
    print_header "9️⃣  AI Services (Optional)"
    
    if ping -c 1 "${AI_VM_IP}" &> /dev/null; then
        print_test "Checking Ollama service..."
        OLLAMA_STATUS=$(curl -s "http://${AI_VM_IP}:11434/api/tags" || echo "")
        
        if [[ -n "${OLLAMA_STATUS}" ]]; then
            print_pass "Ollama is running"
            
            MODEL_COUNT=$(echo "${OLLAMA_STATUS}" | jq -r '.models | length' 2>/dev/null || echo "0")
            print_info "Models installed: ${MODEL_COUNT}"
        else
            print_warn "Ollama is not responding"
        fi
    else
        print_info "AI VM not reachable (skipping AI services check)"
    fi
    
    # 10. Summary
    print_header "📊 Validation Summary"
    
    echo ""
    echo -e "${GREEN}✓ Tests Passed: ${TESTS_PASSED}${NC}"
    echo -e "${YELLOW}⚠ Tests Warned: ${TESTS_WARNED}${NC}"
    echo -e "${RED}✗ Tests Failed: ${TESTS_FAILED}${NC}"
    echo ""
    
    TOTAL_TESTS=$((TESTS_PASSED + TESTS_WARNED + TESTS_FAILED))
    SUCCESS_RATE=$(( TESTS_PASSED * 100 / TOTAL_TESTS ))
    
    echo "Success Rate: ${SUCCESS_RATE}%"
    echo ""
    
    if [[ ${TESTS_FAILED} -eq 0 ]]; then
        echo -e "${GREEN}🎉 All critical tests passed! Infrastructure is healthy.${NC}"
        exit 0
    elif [[ ${TESTS_FAILED} -le 3 ]]; then
        echo -e "${YELLOW}⚠️  Some tests failed. Please review and fix issues.${NC}"
        exit 1
    else
        echo -e "${RED}❌ Multiple critical failures detected. Infrastructure needs attention.${NC}"
        exit 2
    fi
}

# Run main function
main "$@"
