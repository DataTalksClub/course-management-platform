# Deadline Reminder Scheduler IAM

The deadline reminder schedule is configured by the manual GitHub Actions
workflow `Configure Deadline Reminders`. It runs:

```bash
bash deploy/schedule_deadline_reminders.sh dev
```

The helper creates or updates:

- EventBridge Scheduler schedule:
  `course-management-dev-deadline-reminders`
- Scheduler role:
  `course-management-dev-deadline-reminders-scheduler`
- Scheduler role inline policy:
  `RunCmpDeadlineReminderTask`

## CI Deploy User Permissions

Grant these permissions to
`arn:aws:iam::<account-id>:user/course-management-ci-cd-deploy-user`, or the
role/user used by the CMP dev deploy workflow.

Replace:

- `<account-id>` with the AWS account id.
- `<region>` with the region, currently `eu-west-1`.
- `<execution-role-name>` with the ECS task execution role name.
- `<task-role-name>` with the ECS task role name, if the task definition has
  one. Remove that ARN if there is no task role.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCmpEcsServiceForScheduler",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ManageDeadlineReminderSchedule",
      "Effect": "Allow",
      "Action": [
        "scheduler:GetSchedule",
        "scheduler:CreateSchedule",
        "scheduler:UpdateSchedule"
      ],
      "Resource": "arn:aws:scheduler:<region>:<account-id>:schedule/default/course-management-dev-deadline-reminders"
    },
    {
      "Sid": "ManageDeadlineReminderSchedulerRole",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:CreateRole",
        "iam:PutRolePolicy"
      ],
      "Resource": "arn:aws:iam::<account-id>:role/course-management-dev-deadline-reminders-scheduler"
    },
    {
      "Sid": "PassSchedulerRoleToEventBridgeScheduler",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::<account-id>:role/course-management-dev-deadline-reminders-scheduler",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "scheduler.amazonaws.com"
        }
      }
    }
  ]
}
```

The workflow already has the ECS deploy permissions needed to update the
service. The scheduler workflow additionally needs the actions above because it
derives the current task definition and creates the EventBridge Scheduler
target.

## Existing Scheduler Role Option

If a human creates the Scheduler role outside CI, pass its ARN to the workflow
as `scheduler_role_arn`. In that mode, the CI user does not need
`iam:CreateRole` or `iam:PutRolePolicy`, but it still needs `iam:PassRole` for
that role and the Scheduler API actions.

Trust policy for the Scheduler role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Inline policy for the Scheduler role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RunCmpDeadlineReminderTask",
      "Effect": "Allow",
      "Action": "ecs:RunTask",
      "Resource": "arn:aws:ecs:<region>:<account-id>:task-definition/course-management-dev:*",
      "Condition": {
        "ArnEquals": {
          "ecs:cluster": "arn:aws:ecs:<region>:<account-id>:cluster/course-management-cluster"
        }
      }
    },
    {
      "Sid": "PassCmpTaskRoles",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::<account-id>:role/<execution-role-name>",
        "arn:aws:iam::<account-id>:role/<task-role-name>"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    }
  ]
}
```

After applying either option, rerun the manual GitHub Actions workflow:

```text
Configure Deadline Reminders
environment: dev
schedule_expression: rate(1 hour)
scheduler_role_arn: empty when CI can create the role, otherwise the existing role ARN
```

Success criteria:

- The workflow completes successfully.
- `aws scheduler get-schedule --region eu-west-1 --name course-management-dev-deadline-reminders`
  returns the schedule.
- The schedule target uses ECS RunTask with container command
  `python manage.py send_deadline_reminders`.
