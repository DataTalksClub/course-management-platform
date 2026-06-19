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
SCHEDULER_ROLE_NAME=${SCHEDULER_ROLE_NAME:-course-management-${ENV}-deadline-reminders-scheduler}
SCHEDULER_ROLE_POLICY_NAME=${SCHEDULER_ROLE_POLICY_NAME:-RunCmpDeadlineReminderTask}

if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq is required." >&2
    exit 1
fi

ensure_scheduler_role() {
    if [ -n "${SCHEDULER_ROLE_ARN:-}" ]; then
        return
    fi

    TRUST_POLICY=$(jq -n -c '{
      Version: "2012-10-17",
      Statement: [
        {
          Effect: "Allow",
          Principal: {Service: "scheduler.amazonaws.com"},
          Action: "sts:AssumeRole"
        }
      ]
    }')

    ROLE_CREATED=0
    if ROLE_JSON=$(aws iam get-role \
        --region "${AWS_REGION}" \
        --role-name "${SCHEDULER_ROLE_NAME}" 2>/dev/null); then
        echo "Using existing scheduler role ${SCHEDULER_ROLE_NAME}"
    else
        if ! ROLE_JSON=$(aws iam create-role \
            --region "${AWS_REGION}" \
            --role-name "${SCHEDULER_ROLE_NAME}" \
            --assume-role-policy-document "${TRUST_POLICY}" 2>&1); then
            echo "Error: could not create scheduler role ${SCHEDULER_ROLE_NAME}." >&2
            echo "Pass SCHEDULER_ROLE_ARN for an existing role, or grant this AWS principal iam:CreateRole and iam:PutRolePolicy for the scheduler role." >&2
            echo "${ROLE_JSON}" >&2
            exit 1
        fi
        ROLE_CREATED=1
        echo "Created scheduler role ${SCHEDULER_ROLE_NAME}"
    fi

    SCHEDULER_ROLE_ARN=$(echo "${ROLE_JSON}" | jq -r '.Role.Arn')
    PASS_ROLE_ARNS=$(jq -n -c \
        --arg taskRoleArn "${TASK_ROLE_ARN}" \
        --arg executionRoleArn "${EXECUTION_ROLE_ARN}" \
        '[$taskRoleArn, $executionRoleArn] | map(select(. != "" and . != "null"))')
    ROLE_POLICY=$(jq -n -c \
        --arg taskDefinitionArn "${TASK_DEFINITION_ARN}" \
        --arg clusterArn "${CLUSTER_ARN}" \
        --argjson passRoleArns "${PASS_ROLE_ARNS}" \
        '{
          Version: "2012-10-17",
          Statement: (
            [
              {
                Effect: "Allow",
                Action: "ecs:RunTask",
                Resource: $taskDefinitionArn,
                Condition: {
                  ArnEquals: {
                    "ecs:cluster": $clusterArn
                  }
                }
              }
            ] +
            (
              if ($passRoleArns | length) > 0 then
                [
                  {
                    Effect: "Allow",
                    Action: "iam:PassRole",
                    Resource: $passRoleArns,
                    Condition: {
                      StringEquals: {
                        "iam:PassedToService": "ecs-tasks.amazonaws.com"
                      }
                    }
                  }
                ]
              else
                []
              end
            )
          )
        }')

    aws iam put-role-policy \
        --region "${AWS_REGION}" \
        --role-name "${SCHEDULER_ROLE_NAME}" \
        --policy-name "${SCHEDULER_ROLE_POLICY_NAME}" \
        --policy-document "${ROLE_POLICY}" \
        >/dev/null
    echo "Updated scheduler role policy ${SCHEDULER_ROLE_POLICY_NAME}"

    if [ "${ROLE_CREATED}" = "1" ]; then
        sleep 10
    fi
}

SERVICE_JSON=$(aws ecs describe-services \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER}" \
    --services "${SERVICE}")

SERVICE_STATUS=$(echo "${SERVICE_JSON}" | jq -r '.services[0].status // ""')
if [ "${SERVICE_STATUS}" != "ACTIVE" ]; then
    echo "Error: ECS service ${SERVICE} is not active in ${CLUSTER}." >&2
    exit 1
fi

CLUSTER_ARN=$(echo "${SERVICE_JSON}" | jq -r '.services[0].clusterArn')
TASK_DEFINITION_ARN=$(echo "${SERVICE_JSON}" | jq -r '.services[0].taskDefinition')
TASK_DEFINITION_JSON=$(aws ecs describe-task-definition \
    --region "${AWS_REGION}" \
    --task-definition "${TASK_DEFINITION_ARN}")
CONTAINER_NAME=$(echo "${TASK_DEFINITION_JSON}" | jq -r '.taskDefinition.containerDefinitions[0].name')
TASK_ROLE_ARN=$(echo "${TASK_DEFINITION_JSON}" | jq -r '.taskDefinition.taskRoleArn // ""')
EXECUTION_ROLE_ARN=$(echo "${TASK_DEFINITION_JSON}" | jq -r '.taskDefinition.executionRoleArn // ""')

ensure_scheduler_role

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
