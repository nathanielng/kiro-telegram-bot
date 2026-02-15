#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/cloudfront-s3.yaml"

# --- Configuration via environment variables ---
S3_BUCKET_NAME="${DEPLOY_S3_BUCKET_NAME:?Environment variable DEPLOY_S3_BUCKET_NAME is required}"
AWS_REGION="${AWS_REGION:-us-west-2}"
STACK_NAME="${DEPLOY_STACK_NAME:-kiro-static-site}"
SOURCE_DIR="${DEPLOY_SOURCE_DIR:-.}"

echo "=== Deployment Configuration ==="
echo "S3 Bucket:    ${S3_BUCKET_NAME}"
echo "AWS Region:   ${AWS_REGION}"
echo "Stack Name:   ${STACK_NAME}"
echo "Source Dir:   ${SOURCE_DIR}"
echo "================================"

# --- Create S3 bucket if it does not exist ---
echo ""
echo "Checking if S3 bucket '${S3_BUCKET_NAME}' exists..."
if aws s3api head-bucket --bucket "${S3_BUCKET_NAME}" 2>/dev/null; then
    echo "Bucket already exists."
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
    echo "Bucket '${S3_BUCKET_NAME}' created."
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
echo "Upload complete."

# --- Deploy CloudFormation stack ---
echo ""
echo "Deploying CloudFormation stack '${STACK_NAME}'..."
aws cloudformation deploy \
    --template-file "${TEMPLATE_FILE}" \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides S3BucketName="${S3_BUCKET_NAME}" \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset

# --- Print stack outputs ---
echo ""
echo "=== Stack Outputs ==="
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output table

echo ""
echo "Deployment complete."
