
#!/bin/bash

set -e

# Navigate to the script's directory
cd "$(dirname "$0")"

DEV_TASK_DEF="course-management-dev"
PROD_TASK_DEF="course-management-prod"

echo "Deploying ${DEV_TASK_DEF} to prod environment"

FILE_IN="${DEV_TASK_DEF}-current.json"

echo "writing task definition to ${FILE_IN}"
aws ecs describe-task-definition \
    --task-definition ${DEV_TASK_DEF} \
    > ${FILE_IN}

DEV_TAG=$(
    jq '.taskDefinition.containerDefinitions[].environment[] | select(.name == "VERSION").value' -r ${FILE_IN}
)

echo "deploying ${DEV_TAG} to prod"

read -p "Are you sure you want to deploy to production? (y/N) " -n 1 -r
echo

# Check if the user's response is 'y' or 'Y'
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Okay, deploying..."
else
    # The user did not confirm, exit the script
    echo "Deployment cancelled."
    exit 1
fi

rm ${FILE_IN}

bash deploy_dev.sh ${DEV_TAG} prod