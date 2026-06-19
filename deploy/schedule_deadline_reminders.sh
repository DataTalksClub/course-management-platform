#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

ENV=${1:-dev}
SCHEDULE_NAME=${SCHEDULE_NAME:-course-management-${ENV}-deadline-reminders}
SCHEDULE_EXPRESSION=${SCHEDULE_EXPRESSION:-rate(1 hour)}
AWS_REGION=${AWS_REGION:-eu-west-1}
CLUSTER=${CLUSTER:-course-management-cluster}
SERVICE=${SERVICE:-course-management-${ENV}}
TASK_COUNT=${TASK_COUNT:-1}

if [ -z "${SCHEDULER_ROLE_ARN:-}" ]; then
    echo "Error: SCHEDULER_ROLE_ARN is required." >&2
    echo "It must allow scheduler.amazonaws.com to run the CMP ECS task." >&2
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq is required." >&2
    exit 1
fi

SERVICE_JSON=$(aws ecs describe-services \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER}" \
    --services "${SERVICE}")

SERVICE_STATUS=$(echo "${SERVICE_JSON}" | jq -r '.services[0].status // ""')
if [ "${SERVICE_STATUS}" != "ACTIVE" ]; then
    echo "Error: ECS service ${SERVICE} is not active in ${CLUSTER}." >&2
    exit 1
fi

CLUSTER_ARN=$(aws ecs describe-clusters \
    --region "${AWS_REGION}" \
    --clusters "${CLUSTER}" \
    | jq -r '.clusters[0].clusterArn')
TASK_DEFINITION_ARN=$(echo "${SERVICE_JSON}" | jq -r '.services[0].taskDefinition')
CONTAINER_NAME=$(aws ecs describe-task-definition \
    --region "${AWS_REGION}" \
    --task-definition "${TASK_DEFINITION_ARN}" \
    | jq -r '.taskDefinition.containerDefinitions[0].name')

NETWORK_CONFIGURATION=$(echo "${SERVICE_JSON}" | jq -c '
  .services[0].networkConfiguration
')
INPUT=$(jq -n -c --arg container "${CONTAINER_NAME}" '{
  containerOverrides: [
    {
      name: $container,
      command: ["python", "manage.py", "send_deadline_reminders"]
    }
  ]
}')
TARGET=$(jq -n -c \
    --arg clusterArn "${CLUSTER_ARN}" \
    --arg roleArn "${SCHEDULER_ROLE_ARN}" \
    --arg taskDefinitionArn "${TASK_DEFINITION_ARN}" \
    --argjson networkConfiguration "${NETWORK_CONFIGURATION}" \
    --arg input "${INPUT}" \
    --argjson taskCount "${TASK_COUNT}" \
    '{
      Arn: $clusterArn,
      RoleArn: $roleArn,
      EcsParameters: {
        TaskDefinitionArn: $taskDefinitionArn,
        LaunchType: "FARGATE",
        TaskCount: $taskCount,
        NetworkConfiguration: $networkConfiguration
      },
      Input: $input
    }')

COMMON_ARGS=(
    --region "${AWS_REGION}"
    --name "${SCHEDULE_NAME}"
    --schedule-expression "${SCHEDULE_EXPRESSION}"
    --flexible-time-window Mode=OFF
    --target "${TARGET}"
)

if aws scheduler get-schedule \
    --region "${AWS_REGION}" \
    --name "${SCHEDULE_NAME}" \
    >/dev/null 2>&1; then
    aws scheduler update-schedule "${COMMON_ARGS[@]}" >/dev/null
    echo "Updated schedule ${SCHEDULE_NAME}: ${SCHEDULE_EXPRESSION}"
else
    aws scheduler create-schedule "${COMMON_ARGS[@]}" >/dev/null
    echo "Created schedule ${SCHEDULE_NAME}: ${SCHEDULE_EXPRESSION}"
fi
