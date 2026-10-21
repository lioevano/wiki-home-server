#!/usr/bin/env bash
# NFS Permissions Diagnostic Script
# Diagnoses and fixes common NFS permission issues
# Version: 1.0.0

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration (override with environment variables)
PROXMOX_HOST="${PROXMOX_HOST:-192.168.1.50}"
VM_IP="${VM_IP:-192.168.1.100}"
NFS_MOUNT_PATH="${NFS_MOUNT_PATH:-/mnt/pve_data_zfs}"
EXPECTED_PUID="${EXPECTED_PUID:-1000}"
EXPECTED_PGID="${EXPECTED_PGID:-1000}"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  NFS Permissions Diagnostic Tool      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo -e "${YELLOW}⚠️  Running as root. This is recommended for fixes.${NC}\n"
    CAN_FIX=true
else
    echo -e "${YELLOW}⚠️  Not running as root. Will only diagnose issues.${NC}"
    echo -e "${YELLOW}   Run with sudo to apply fixes.${NC}\n"
    CAN_FIX=false
fi

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}━━━ $1 ━━━${NC}\n"
}

# Function to print results
print_ok() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
print_info() { echo -e "${BLUE}ℹ${NC} $1"; }

# 1. Check NFS mount status
print_section "1. NFS Mount Status"

if mount | grep -q "${NFS_MOUNT_PATH}"; then
    print_ok "NFS is mounted at ${NFS_MOUNT_PATH}"
    
    # Get mount details
    MOUNT_INFO=$(mount | grep "${NFS_MOUNT_PATH}")
    echo "${MOUNT_INFO}"
    
    # Check for important mount options
    if echo "${MOUNT_INFO}" | grep -q "rw"; then
        print_ok "Mount is read-write"
    else
        print_error "Mount is read-only!"
    fi
    
    if echo "${MOUNT_INFO}" | grep -q "hard"; then
        print_ok "Using 'hard' mount option (recommended)"
    else
        print_warn "Not using 'hard' mount option"
    fi
    
else
    print_error "NFS is NOT mounted at ${NFS_MOUNT_PATH}"
    echo ""
    print_info "To mount NFS:"
    echo "  sudo mount -t nfs ${PROXMOX_HOST}:/data ${NFS_MOUNT_PATH}"
    exit 1
fi

# 2. Check NFS server exports
print_section "2. NFS Server Exports (on Proxmox Host)"

print_info "Checking /etc/exports on ${PROXMOX_HOST}..."

if ssh -o ConnectTimeout=5 "root@${PROXMOX_HOST}" "cat /etc/exports" 2>/dev/null; then
    EXPORTS=$(ssh "root@${PROXMOX_HOST}" "cat /etc/exports")
    echo "${EXPORTS}"
    
    # Check for all_squash
    if echo "${EXPORTS}" | grep -q "all_squash"; then
        print_warn "Using 'all_squash' - all users mapped to single UID/GID"
        
        SQUASH_UID=$(echo "${EXPORTS}" | grep -oP 'anonuid=\K[0-9]+' || echo "unknown")
        SQUASH_GID=$(echo "${EXPORTS}" | grep -oP 'anongid=\K[0-9]+' || echo "unknown")
        
        echo "  Mapped to UID: ${SQUASH_UID}"
        echo "  Mapped to GID: ${SQUASH_GID}"
        
        if [[ "${SQUASH_UID}" == "${EXPECTED_PUID}" ]] && [[ "${SQUASH_GID}" == "${EXPECTED_PGID}" ]]; then
            print_ok "Squash UID/GID matches expected Docker PUID/PGID"
        else
            print_error "Squash UID/GID does NOT match expected ${EXPECTED_PUID}:${EXPECTED_PGID}"
        fi
    elif echo "${EXPORTS}" | grep -q "no_root_squash"; then
        print_warn "Using 'no_root_squash' - root on client = root on server"
    else
        print_ok "Using standard root_squash (default)"
    fi
else
    print_error "Cannot connect to Proxmox host to check exports"
fi

# 3. Check directory ownership and permissions
print_section "3. Directory Ownership & Permissions"

if [[ -d "${NFS_MOUNT_PATH}" ]]; then
    MOUNT_OWNER=$(stat -c "%U:%G (%u:%g)" "${NFS_MOUNT_PATH}")
    MOUNT_PERMS=$(stat -c "%a" "${NFS_MOUNT_PATH}")
    
    echo "Owner: ${MOUNT_OWNER}"
    echo "Permissions: ${MOUNT_PERMS}"
    
    # Check common subdirectories
    for subdir in docker-volumes media photos files notes; do
        FULL_PATH="${NFS_MOUNT_PATH}/${subdir}"
        if [[ -d "${FULL_PATH}" ]]; then
            OWNER=$(stat -c "%U:%G (%u:%g)" "${FULL_PATH}")
            PERMS=$(stat -c "%a" "${FULL_PATH}")
            
            echo ""
            echo "  ${subdir}/"
            echo "    Owner: ${OWNER}"
            echo "    Permissions: ${PERMS}"
            
            # Check if writable
            if [[ -w "${FULL_PATH}" ]]; then
                print_ok "  ${subdir} is writable"
            else
                print_error "  ${subdir} is NOT writable"
            fi
        fi
    done
else
    print_error "${NFS_MOUNT_PATH} does not exist!"
fi

# 4. Test write permissions
print_section "4. Write Permission Test"

TEST_FILE="${NFS_MOUNT_PATH}/.nfs_test_$(date +%s)"

echo "Attempting to create test file: ${TEST_FILE}"

if touch "${TEST_FILE}" 2>/dev/null; then
    print_ok "Successfully created test file"
    
    # Check owner of created file
    FILE_OWNER=$(stat -c "%U:%G (%u:%g)" "${TEST_FILE}")
    echo "Created file owner: ${FILE_OWNER}"
    
    # Cleanup
    rm "${TEST_FILE}"
    print_ok "Test file removed"
else
    print_error "FAILED to create test file (permission denied)"
    
    if [[ "${CAN_FIX}" == true ]]; then
        echo ""
        print_warn "Attempting to fix permissions..."
        
        # Try to change ownership
        if chown "${EXPECTED_PUID}:${EXPECTED_PGID}" "${NFS_MOUNT_PATH}" 2>/dev/null; then
            print_ok "Changed ownership to ${EXPECTED_PUID}:${EXPECTED_PGID}"
        else
            print_error "Cannot change ownership (may need to fix on NFS server)"
        fi
    fi
fi

# 5. Check Docker user
print_section "5. Docker User Configuration"

if id docker &>/dev/null; then
    DOCKER_UID=$(id -u docker)
    DOCKER_GID=$(id -g docker)
    
    echo "Docker user UID: ${DOCKER_UID}"
    echo "Docker user GID: ${DOCKER_GID}"
    
    if [[ "${DOCKER_UID}" == "${EXPECTED_PUID}" ]] && [[ "${DOCKER_GID}" == "${EXPECTED_PGID}" ]]; then
        print_ok "Docker user UID/GID matches expected values"
    else
        print_warn "Docker user UID/GID differs from expected ${EXPECTED_PUID}:${EXPECTED_PGID}"
    fi
else
    print_warn "Docker user does not exist on this system"
fi

# 6. Check for common issues with specific services
print_section "6. Service-Specific Checks"

# Check Ollama (if AI VM) — roda em container (stack ai), com modelos em docker-volumes/ollama/models
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ollama; then
    OLLAMA_MODELS_DIR="${NFS_MOUNT_PATH}/docker-volumes/ollama/models"
    if [[ -d "${OLLAMA_MODELS_DIR}" ]]; then
        DIR_UID=$(stat -c "%u" "${OLLAMA_MODELS_DIR}")
        echo "Ollama container running; models directory owner UID: ${DIR_UID}"
        if [[ "${DIR_UID}" == "${EXPECTED_PUID}" ]]; then
            print_ok "Ollama models directory owned by PUID ${EXPECTED_PUID}"
        else
            print_warn "Ollama models directory owner (${DIR_UID}) differs from PUID ${EXPECTED_PUID}"
            if [[ "${CAN_FIX}" == true ]]; then
                chown -R "${EXPECTED_PUID}:${EXPECTED_PGID}" "${OLLAMA_MODELS_DIR}"
                print_ok "Permissions updated"
            fi
        fi
    else
        print_warn "Ollama models directory not found: ${OLLAMA_MODELS_DIR} (run setup-ai-volumes.yml)"
    fi
fi

# 7. Recommendations
print_section "7. Recommendations"

echo ""
print_info "Common fixes for NFS permission issues:"
echo ""

echo "Option 1: Match UIDs/GIDs across systems"
echo "  - Ensure docker user has same UID/GID on all VMs"
echo "  - Use consistent PUID/PGID in docker-compose files"
echo ""

echo "Option 2: Use all_squash with matching UIDs"
echo "  - On Proxmox host, edit /etc/exports:"
echo "    /data *(rw,sync,no_subtree_check,all_squash,anonuid=${EXPECTED_PUID},anongid=${EXPECTED_PGID})"
echo "  - Then: exportfs -ra"
echo ""

echo "Option 3: Use no_root_squash (less secure)"
echo "  - On Proxmox host, edit /etc/exports:"
echo "    /data *(rw,sync,no_subtree_check,no_root_squash)"
echo "  - Then: exportfs -ra"
echo ""

echo "Option 4: Permissive permissions (quick fix, not recommended)"
echo "  - chmod -R 0777 ${NFS_MOUNT_PATH}"
echo ""

# 8. Generate fix script
if [[ "${CAN_FIX}" == true ]]; then
    print_section "8. Quick Fix"
    
    echo ""
    read -p "Attempt automated fix? (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Applying fixes..."
        
        # Fix directory ownership
        find "${NFS_MOUNT_PATH}" -type d -exec chmod 0775 {} \; 2>/dev/null || true
        chown -R "${EXPECTED_PUID}:${EXPECTED_PGID}" "${NFS_MOUNT_PATH}" 2>/dev/null || true
        
        print_ok "Fixes applied. Please test your services."
    fi
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Diagnostic complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
