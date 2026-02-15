#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/cloudfront-s3.yaml"
ENV_FILE="${PROJECT_DIR}/.env"

# --- Parse flags ---
AUTO_APPROVE=false
for arg in "$@"; do
    case "${arg}" in
        -y|--yes)
            AUTO_APPROVE=true
            ;;
        -h|--help)
            echo "Usage: $(basename "$0") [OPTIONS]"
            echo ""
            echo "Deploy static files to S3 and set up a CloudFront distribution."
            echo ""
            echo "Options:"
            echo "  -y, --yes   Auto-approve all confirmation prompts"
            echo "  -h, --help  Show this help message"
            echo ""
            echo "Configuration (via environment variables or .env file):"
            echo "  DEPLOY_S3_BUCKET_NAME   (required) S3 bucket name"
            echo "  AWS_REGION              (optional) AWS region (default: us-west-2)"
            echo "  DEPLOY_STACK_NAME       (optional) CloudFormation stack name (default: kiro-static-site)"
            echo "  DEPLOY_SOURCE_DIR       (optional) Source directory for static files (default: .)"
            echo "  DEPLOY_CACHE_TTL        (optional) Cache TTL in seconds (default: 0)"
            exit 0
            ;;
        *)
            echo "Error: Unknown option '${arg}'"
            echo "Run '$(basename "$0") --help' for usage information."
            exit 1
            ;;
    esac
done

# --- Helper functions ---

# Prompt the user for confirmation. Skips if AUTO_APPROVE is true.
# Usage: confirm "Do you want to proceed?"
confirm() {
    local message="$1"
    if [ "${AUTO_APPROVE}" = true ]; then
        return 0
    fi
    echo ""
    read -r -p "${message} [y/N] " response
    case "${response}" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Print a user-friendly error message and exit.
# Usage: fail "What went wrong" "Suggestion to fix it"
fail() {
    local message="$1"
    local hint="${2:-}"
    echo ""
    echo "❌ Error: ${message}"
    if [ -n "${hint}" ]; then
        echo "   Hint: ${hint}"
    fi
    exit 1
}

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
if [ -z "${DEPLOY_S3_BUCKET_NAME:-}" ]; then
    fail "DEPLOY_S3_BUCKET_NAME is not set." \
         "Set it as an environment variable or add it to ${ENV_FILE}. Example: DEPLOY_S3_BUCKET_NAME=my-bucket ./deployment/deploy.sh"
fi
S3_BUCKET_NAME="${DEPLOY_S3_BUCKET_NAME}"
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
    if ! confirm "S3 bucket '${S3_BUCKET_NAME}' does not exist. Create it in '${AWS_REGION}'?"; then
        echo "Aborted. No bucket was created."
        exit 0
    fi
    echo "Creating bucket '${S3_BUCKET_NAME}' in ${AWS_REGION}..."
    if [ "${AWS_REGION}" = "us-east-1" ]; then
        if ! aws s3api create-bucket \
                --bucket "${S3_BUCKET_NAME}" \
                --region "${AWS_REGION}" 2>/tmp/deploy-err.txt; then
            err_msg="$(cat /tmp/deploy-err.txt)"
            if echo "${err_msg}" | grep -q "BucketAlreadyExists"; then
                fail "The bucket name '${S3_BUCKET_NAME}' is already taken globally by another AWS account." \
                     "S3 bucket names are globally unique. Choose a different name (e.g. add a random suffix)."
            elif echo "${err_msg}" | grep -q "AccessDenied\|InvalidAccessKeyId\|SignatureDoesNotMatch"; then
                fail "AWS credentials are invalid or lack permission to create S3 buckets." \
                     "Check your AWS credentials with 'aws sts get-caller-identity' and ensure the IAM policy allows s3:CreateBucket."
            else
                fail "Failed to create S3 bucket: ${err_msg}" \
                     "Check that your AWS credentials are configured and the bucket name is valid (lowercase, 3-63 characters, no underscores)."
            fi
        fi
    else
        if ! aws s3api create-bucket \
                --bucket "${S3_BUCKET_NAME}" \
                --region "${AWS_REGION}" \
                --create-bucket-configuration LocationConstraint="${AWS_REGION}" 2>/tmp/deploy-err.txt; then
            err_msg="$(cat /tmp/deploy-err.txt)"
            if echo "${err_msg}" | grep -q "BucketAlreadyExists"; then
                fail "The bucket name '${S3_BUCKET_NAME}' is already taken globally by another AWS account." \
                     "S3 bucket names are globally unique. Choose a different name (e.g. add a random suffix)."
            elif echo "${err_msg}" | grep -q "IllegalLocationConstraintException"; then
                fail "The region '${AWS_REGION}' is not valid for bucket creation." \
                     "Check your AWS_REGION value. Valid examples: us-east-1, us-west-2, eu-west-1."
            elif echo "${err_msg}" | grep -q "AccessDenied\|InvalidAccessKeyId\|SignatureDoesNotMatch"; then
                fail "AWS credentials are invalid or lack permission to create S3 buckets." \
                     "Check your AWS credentials with 'aws sts get-caller-identity' and ensure the IAM policy allows s3:CreateBucket."
            else
                fail "Failed to create S3 bucket: ${err_msg}" \
                     "Check that your AWS credentials are configured and the bucket name is valid (lowercase, 3-63 characters, no underscores)."
            fi
        fi
    fi
    echo "✅ Bucket '${S3_BUCKET_NAME}' created."
    BUCKET_CREATED=true
fi

# --- Upload static files to S3 ---
echo ""
echo "Syncing files from '${SOURCE_DIR}' to s3://${S3_BUCKET_NAME}/..."
if ! aws s3 sync "${SOURCE_DIR}" "s3://${S3_BUCKET_NAME}/" \
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
    --exclude "deployment/*" 2>/tmp/deploy-err.txt; then
    err_msg="$(cat /tmp/deploy-err.txt)"
    fail "Failed to sync files to S3: ${err_msg}" \
         "Ensure the source directory '${SOURCE_DIR}' exists and your IAM policy allows s3:PutObject on the bucket."
fi
echo "✅ Upload complete."

# --- Deploy CloudFormation stack ---
echo ""
if ! confirm "Deploy CloudFormation stack '${STACK_NAME}' (CloudFront distribution + S3 bucket policy) in '${AWS_REGION}'?"; then
    echo "Aborted. CloudFormation stack was not deployed."
    exit 0
fi
echo "Deploying CloudFormation stack '${STACK_NAME}'..."
if ! aws cloudformation deploy \
    --template-file "${TEMPLATE_FILE}" \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides \
        S3BucketName="${S3_BUCKET_NAME}" \
        CacheTTL="${CACHE_TTL}" \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset 2>/tmp/deploy-err.txt; then
    err_msg="$(cat /tmp/deploy-err.txt)"
    if echo "${err_msg}" | grep -q "ValidationError"; then
        fail "CloudFormation template validation failed: ${err_msg}" \
             "Check deployment/cloudfront-s3.yaml for syntax errors. Run: aws cloudformation validate-template --template-body file://${TEMPLATE_FILE}"
    elif echo "${err_msg}" | grep -q "ROLLBACK"; then
        fail "CloudFormation stack deployment failed and rolled back: ${err_msg}" \
             "Check the stack events for details: aws cloudformation describe-stack-events --stack-name ${STACK_NAME} --region ${AWS_REGION}"
    elif echo "${err_msg}" | grep -q "AccessDenied\|InsufficientCapabilities"; then
        fail "Insufficient permissions to deploy the CloudFormation stack: ${err_msg}" \
             "Ensure your IAM policy allows cloudformation:CreateStack, cloudformation:UpdateStack, cloudfront:*, and s3:*."
    else
        fail "CloudFormation deployment failed: ${err_msg}" \
             "Check stack events for details: aws cloudformation describe-stack-events --stack-name ${STACK_NAME} --region ${AWS_REGION}"
    fi
fi
echo "✅ CloudFormation stack deployed."

# --- Retrieve stack outputs ---
echo ""
echo "=== Stack Outputs ==="
if ! STACK_OUTPUT="$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --output json 2>/tmp/deploy-err.txt)"; then
    err_msg="$(cat /tmp/deploy-err.txt)"
    fail "Failed to retrieve stack outputs: ${err_msg}" \
         "The stack may still be deploying. Check status: aws cloudformation describe-stacks --stack-name ${STACK_NAME} --region ${AWS_REGION}"
fi

DISTRIBUTION_ID="$(echo "${STACK_OUTPUT}" | grep -o '"OutputKey": "DistributionId"[^}]*"OutputValue": "[^"]*"' | grep -o '"OutputValue": "[^"]*"' | cut -d'"' -f4)"
DISTRIBUTION_DOMAIN="$(echo "${STACK_OUTPUT}" | grep -o '"OutputKey": "DistributionDomainName"[^}]*"OutputValue": "[^"]*"' | grep -o '"OutputValue": "[^"]*"' | cut -d'"' -f4)"

if [ -z "${DISTRIBUTION_ID}" ] || [ -z "${DISTRIBUTION_DOMAIN}" ]; then
    fail "Stack outputs are missing (DistributionId or DistributionDomainName not found)." \
         "The stack may not have completed successfully. Check: aws cloudformation describe-stacks --stack-name ${STACK_NAME} --region ${AWS_REGION}"
fi

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
