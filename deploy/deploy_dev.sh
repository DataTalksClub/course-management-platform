#!/bin/bash

set -e

# Navigate to the script's directory
cd "$(dirname "$0")"

TAG=$1
ENV=$2

# Check if tag is provided
if [ -z "$TAG" ]; then
    echo "Error: No tag provided."
    echo "Usage: ./deploy_dev.sh <tag> <env>"
    exit 1
fi

if [ -z "$ENV" ]; then
    ENV="dev"
fi

DEV_TASK_DEF="course-management-${ENV}"
echo "Deploying ${DEV_TASK_DEF}-${TAG} to ${ENV} environment"

# Preflight (2026-10-22): the AWS ECS dev path is retired in favor of Coolify
# (.github/workflows/deploy-coolify.yml) after the course-management-dev ELB
# target group was deleted (GHA 39807898139 / 39806180567). Fail fast here with
# a clear message instead of failing late at `update-service` with a cryptic
# InvalidParameterException.
# NOTE: deploy_prod.sh reuses this script with ENV=prod, so this stays a hard
# error (exit 1): a missing service/TG must fail loudly, never soft-pass.
if ! SERVICE_DESC=$(aws ecs describe-services \
    --cluster course-management-cluster \
    --services "course-management-${ENV}" 2>&1); then
    echo "Error: ECS service course-management-${ENV} not found in cluster course-management-cluster." >&2
    echo "The AWS ECS path is retired; live staging CD is Deploy CMP Coolify (Contabo)." >&2
    echo "aws error was: ${SERVICE_DESC}" >&2
    exit 1
fi
if [ "$(echo "${SERVICE_DESC}" | jq -r '.failures | length')" != "0" ]; then
    echo "Error: ECS service course-management-${ENV} lookup failed: $(echo "${SERVICE_DESC}" | jq -c '.failures')" >&2
    echo "The AWS ECS path is retired; live staging CD is Deploy CMP Coolify (Contabo)." >&2
    exit 1
fi
TG_ARNS=$(echo "${SERVICE_DESC}" | jq -r '.services[0].loadBalancers[].targetGroupArn // empty')
for TG in ${TG_ARNS}; do
    if ! aws elbv2 describe-target-groups --target-group-arns "${TG}" > /dev/null 2>&1; then
        echo "Error: target group ${TG} attached to service course-management-${ENV} does not exist." >&2
        echo "The ELB target group was deleted (ELB cut / Coolify migration); the AWS ECS path is retired." >&2
        echo "Live staging CD is Deploy CMP Coolify (Contabo). Do not recreate the ALB/TG unless AWS ECS staging is explicitly required." >&2
        exit 1
    fi
done

FILE_IN="${DEV_TASK_DEF}-${TAG}.json"
FILE_OUT="updated_${DEV_TASK_DEF}-${TAG}.json"


echo "writing task definition to ${FILE_IN}"
aws ecs describe-task-definition \
    --task-definition ${DEV_TASK_DEF} \
    > ${FILE_IN}


echo "writing updated task definition to ${FILE_OUT}"
python update_task_def.py ${FILE_IN} ${TAG} ${FILE_OUT}

# Register new task definition (Assuming AWS CLI and proper permissions are set up)
aws ecs register-task-definition \
    --cli-input-json file://${FILE_OUT} \
    > /dev/null

# Update ECS service (replace 'my-cluster' with your actual ECS cluster name)
aws ecs update-service \
    --cluster course-management-cluster \
    --service course-management-${ENV} \
    --task-definition $DEV_TASK_DEF \
    > /dev/null

# Clean up JSON files
rm -f ${FILE_IN} ${FILE_OUT}

echo "${ENV} deployment completed successfully."
