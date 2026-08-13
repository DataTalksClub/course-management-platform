#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: $0 --environment <prod|dev> --alarm <name> --start <ISO-8601> --end <ISO-8601>"
}

environment=""
alarm_name=""
start_time=""
end_time=""
profile="${CMP_INVESTIGATOR_PROFILE:-cmp-alert-investigator}"
region="${AWS_REGION:-eu-west-1}"
export AWS_PAGER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment)
      environment="$2"
      shift 2
      ;;
    --alarm)
      alarm_name="$2"
      shift 2
      ;;
    --start)
      start_time="$2"
      shift 2
      ;;
    --end)
      end_time="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$environment" != "prod" && "$environment" != "dev" ]]; then
  echo "--environment must be prod or dev" >&2
  exit 2
fi
if [[ -z "$alarm_name" || -z "$start_time" || -z "$end_time" ]]; then
  usage >&2
  exit 2
fi
if [[ ! "$alarm_name" =~ ^cmp-[A-Za-z0-9._-]+$ ]]; then
  echo "Alarm name must start with cmp- and contain only safe characters" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
if [[ ! -f AGENTS.md ]]; then
  echo "Run this script inside the CMP repository" >&2
  exit 2
fi

start_seconds="$(date --date="$start_time" +%s)"
end_seconds="$(date --date="$end_time" +%s)"
if (( end_seconds <= start_seconds )); then
  echo "--end must be later than --start" >&2
  exit 2
fi
start_millis="$((start_seconds * 1000))"
end_millis="$((end_seconds * 1000))"

safe_start="$(date --utc --date="@$start_seconds" +%Y%m%dT%H%M%SZ)"
output_dir=".tmp/cmp-incidents/${safe_start}-${alarm_name}"
mkdir -p "$output_dir"
chmod 700 "$output_dir"
umask 077

aws_cmd=(aws --profile "$profile" --region "$region")
"${aws_cmd[@]}" sts get-caller-identity > "$output_dir/caller-identity.json"
caller_arn="$(jq -r .Arn "$output_dir/caller-identity.json")"
case "$caller_arn" in
  arn:aws:sts::387546586013:assumed-role/cmp-alert-investigator/*) ;;
  *)
    echo "Unexpected investigator identity: $caller_arn" >&2
    exit 1
    ;;
esac

service_name="course-management-${environment}"
log_group="/ecs/${service_name}"
cluster_name="course-management-cluster"

"${aws_cmd[@]}" cloudwatch describe-alarms \
  --alarm-names "$alarm_name" \
  > "$output_dir/alarm.json"
"${aws_cmd[@]}" cloudwatch describe-alarm-history \
  --alarm-name "$alarm_name" \
  --start-date "$start_time" \
  --end-date "$end_time" \
  > "$output_dir/alarm-history.json"
"${aws_cmd[@]}" logs filter-log-events \
  --log-group-name "$log_group" \
  --start-time "$start_millis" \
  --end-time "$end_millis" \
  > "$output_dir/application-logs.json"
"${aws_cmd[@]}" ecs describe-services \
  --cluster "$cluster_name" \
  --services "$service_name" \
  > "$output_dir/ecs-service.json"
"${aws_cmd[@]}" ecs list-tasks \
  --cluster "$cluster_name" \
  --service-name "$service_name" \
  > "$output_dir/ecs-task-list.json"

mapfile -t task_arns < <(jq -r '.taskArns[]?' "$output_dir/ecs-task-list.json")
if (( ${#task_arns[@]} > 0 )); then
  "${aws_cmd[@]}" ecs describe-tasks \
    --cluster "$cluster_name" \
    --tasks "${task_arns[@]}" \
    > "$output_dir/ecs-tasks.json"
fi

"${aws_cmd[@]}" elbv2 describe-target-groups \
  --names "$service_name" \
  > "$output_dir/target-group.json"
target_group_arn="$(jq -r '.TargetGroups[0].TargetGroupArn' "$output_dir/target-group.json")"
"${aws_cmd[@]}" elbv2 describe-target-health \
  --target-group-arn "$target_group_arn" \
  > "$output_dir/target-health.json"

if [[ "$environment" == "prod" ]]; then
  base_url="https://courses.datatalks.club"
else
  base_url="https://dev.courses.datatalks.club"
fi
curl --fail --silent --show-error "$base_url/api/health/" \
  > "$output_dir/health.json"

echo "$output_dir"
