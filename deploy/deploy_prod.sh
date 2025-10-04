
#!/bin/bash

set -e

# Navigate to the script's directory
cd "$(dirname "$0")"


DEV_TAG=$1

if [ -z "$DEV_TAG" ]; then
    echo "No tag provided. Fetching tag from the dev environment."
    DEV_TASK_DEF="course-management-dev"

    FILE_IN="${DEV_TASK_DEF}-current.json"

    echo "writing task definition to ${FILE_IN}"
    aws ecs describe-task-definition \
        --task-definition ${DEV_TASK_DEF} \
        > ${FILE_IN}
        
    DEV_TAG=$(
        jq '.taskDefinition.containerDefinitions[].environment[] | select(.name == "VERSION").value' -r ${FILE_IN}
    )

    rm -f ${FILE_IN}
fi


echo "deploying ${DEV_TAG} to prod"

# Check if running outside GitHub Actions and need confirmation
if [ -z "${GITHUB_ACTIONS}" ] && [ "${CONFIRM_DEPLOY}" != "true" ]; then
    read -p "Are you sure you want to deploy to production? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        CONFIRM_DEPLOY="true"
    fi
fi

if [ "${CONFIRM_DEPLOY}" != "true" ]; then
    echo "Exiting without deploying."
    exit 1
fi


bash deploy_dev.sh ${DEV_TAG} prod

echo "${DEV_TAG}" >> ../.prod-versions
