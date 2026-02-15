#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/cloudfront-s3.yaml"
ENV_FILE="${PROJECT_DIR}/.env"

# --- Load .env file if it exists (without overriding already-set env vars) ---
if [ -f "${ENV_FILE}" ]; then
    echo "Loading configuration from ${ENV_FILE}..."
    while IFS='=' read -r key value; do
        # Skip comments and blank lines
        [[ -z "${key}" || "${key}" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        key="$(echo "${key}" | xargs)"
        value="$(echo "${value}" | xargs)"
        # Strip surrounding quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        # Only set if not already defined in the environment
        if [ -z "${!key+x}" ]; then
            export "${key}=${value}"
        fi
    done < "${ENV_FILE}"
fi

# --- Configuration via environment variables ---
S3_BUCKET_NAME="${DEPLOY_S3_BUCKET_NAME:?Environment variable DEPLOY_S3_BUCKET_NAME is required (set it or add it to .env)}"
AWS_REGION="${AWS_REGION:-us-west-2}"
STACK_NAME="${DEPLOY_STACK_NAME:-kiro-static-site}"
SOURCE_DIR="${DEPLOY_SOURCE_DIR:-.}"
CACHE_TTL="${DEPLOY_CACHE_TTL:-0}"

echo "=== Deployment Configuration ==="
echo "S3 Bucket:    ${S3_BUCKET_NAME}"
echo "AWS Region:   ${AWS_REGION}"
echo "Stack Name:   ${STACK_NAME}"
echo "Source Dir:   ${SOURCE_DIR}"
echo "Cache TTL:    ${CACHE_TTL}s"
echo "================================"

# --- Create S3 bucket if it does not exist ---
echo ""
BUCKET_CREATED=false
echo "Checking if S3 bucket '${S3_BUCKET_NAME}' exists..."
if aws s3api head-bucket --bucket "${S3_BUCKET_NAME}" 2>/dev/null; then
    echo "✅ Bucket already exists."
else
    echo "Bucket does not exist. Creating..."
    if [ "${AWS_REGION}" = "us-east-1" ]; then
        aws s3api create-bucket \
            --bucket "${S3_BUCKET_NAME}" \
            --region "${AWS_REGION}"
    else
        aws s3api create-bucket \
            --bucket "${S3_BUCKET_NAME}" \
            --region "${AWS_REGION}" \
            --create-bucket-configuration LocationConstraint="${AWS_REGION}"
    fi
    echo "✅ Bucket '${S3_BUCKET_NAME}' created."
    BUCKET_CREATED=true
fi

# --- Upload static files to S3 ---
echo ""
echo "Syncing files from '${SOURCE_DIR}' to s3://${S3_BUCKET_NAME}/..."
aws s3 sync "${SOURCE_DIR}" "s3://${S3_BUCKET_NAME}/" \
    --delete \
    --exclude ".*" \
    --exclude "*.sh" \
    --exclude "*.py" \
    --exclude "*.toml" \
    --exclude "*.txt" \
    --exclude "*.log" \
    --exclude "*.yaml" \
    --exclude "*.yml" \
    --exclude "__pycache__/*" \
    --exclude ".git/*" \
    --exclude "deployment/*"
echo "✅ Upload complete."

# --- Deploy CloudFormation stack ---
echo ""
echo "Deploying CloudFormation stack '${STACK_NAME}'..."
aws cloudformation deploy \
    --template-file "${TEMPLATE_FILE}" \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides \
        S3BucketName="${S3_BUCKET_NAME}" \
        CacheTTL="${CACHE_TTL}" \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset
echo "✅ CloudFormation stack deployed."

# --- Retrieve stack outputs ---
echo ""
echo "=== Stack Outputs ==="
DISTRIBUTION_ID="$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
    --output text)"

DISTRIBUTION_DOMAIN="$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionDomainName'].OutputValue" \
    --output text)"

echo "Distribution ID:     ${DISTRIBUTION_ID}"
echo "Distribution URL:    https://${DISTRIBUTION_DOMAIN}"

# --- Save outputs to .env file ---
echo ""
echo "Saving deployment outputs to ${ENV_FILE}..."

# Helper: update or add a key=value pair in the .env content
# Operates on the ENV_CONTENT variable
update_env_var() {
    local key="$1"
    local value="$2"
    if echo "${ENV_CONTENT}" | grep -q "^${key}="; then
        ENV_CONTENT="$(echo "${ENV_CONTENT}" | sed "s|^${key}=.*|${key}=${value}|")"
    else
        ENV_CONTENT="${ENV_CONTENT}
${key}=${value}"
    fi
}

# Start with existing .env content or empty string
if [ -f "${ENV_FILE}" ]; then
    ENV_CONTENT="$(cat "${ENV_FILE}")"
else
    ENV_CONTENT="# Deployment configuration for kiro-telegram-bot
# This file is auto-managed by deployment/deploy.sh"
fi

# Snapshot the original content for comparison
ENV_ORIGINAL="${ENV_CONTENT}"

# Always persist the S3 bucket name (especially useful when a new bucket was created)
update_env_var "DEPLOY_S3_BUCKET_NAME" "${S3_BUCKET_NAME}"

# Save CloudFront outputs
update_env_var "DEPLOY_CLOUDFRONT_DISTRIBUTION_ID" "${DISTRIBUTION_ID}"
update_env_var "DEPLOY_CLOUDFRONT_URL" "https://${DISTRIBUTION_DOMAIN}"

# Also persist the region and stack name so subsequent runs are fully self-contained
update_env_var "AWS_REGION" "${AWS_REGION}"
update_env_var "DEPLOY_STACK_NAME" "${STACK_NAME}"

# Write the file (with backup if content changed)
if [ -f "${ENV_FILE}" ] && [ "${ENV_CONTENT}" != "${ENV_ORIGINAL}" ]; then
    BACKUP_FILE="${ENV_FILE}.backup"
    cp "${ENV_FILE}" "${BACKUP_FILE}"
    echo "📋 Existing .env backed up to ${BACKUP_FILE}"
fi

echo "${ENV_CONTENT}" > "${ENV_FILE}"
echo "✅ Environment variables saved to ${ENV_FILE}"

echo ""
echo "✅ Deployment complete."
