#!/bin/bash

set -e

# Navigate to the script's directory
cd "$(dirname "$0")"


TAG=$1

DEV_TASK_DEF="course-management-dev"

FILE_IN="${DEV_TASK_DEF}-${TAG}.json"
FILE_OUT="updated_${DEV_TASK_DEF}-${TAG}.json"

# Check if tag is provided
if [ -z "$TAG" ]; then
    echo "Error: No tag provided."
    echo "Usage: ./deploy_dev.sh <tag>"
    exit 1
fi


echo "writing task definition to ${FILE_IN}"
aws ecs describe-task-definition \
    --task-definition course-management-dev \
    > ${FILE_IN}


echo "writing updated task definition to ${FILE_OUT}"
python update_task_def.py ${FILE_IN} ${TAG} ${FILE_OUT}

# Register new task definition (Assuming AWS CLI and proper permissions are set up)
aws ecs register-task-definition \
    --cli-input-json file://${FILE_OUT}

# Update ECS service (replace 'my-cluster' with your actual ECS cluster name)
aws ecs update-service \
    --cluster course-management-cluster \
    --service course-management-dev \
    --task-definition $DEV_TASK_DEF

# Clean up JSON files
# rm -f ${FILE_IN} ${FILE_OUT}

echo "Dev deployment completed successfully."
