resource "aws_iam_user" "deploy_ci_cd_user" {
  name = "course-management-ci-cd-deploy-user"
}

resource "aws_iam_access_key" "ci_cd_user_key" {
  user = aws_iam_user.deploy_ci_cd_user.name
}

resource "aws_iam_user_policy" "ci_cd_user_policy" {
  name = "ci-cd-user-policy"
  user = aws_iam_user.deploy_ci_cd_user.name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = "ecr:GetAuthorizationToken",
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "ecr:GetLoginPassword",
          "ecr:BatchCheckLayerAvailability",
          "ecr:CompleteLayerUpload",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart"
        ],
        Resource = aws_ecr_repository.course_management_ecr_repo.arn
      },
      {
        Effect = "Allow",
        Action = [
          "ecs:DescribeTaskDefinition",
          "ecs:RegisterTaskDefinition",
          "ecs:ListTaskDefinitions",
          "ecs:DeregisterTaskDefinition",
          "ecs:DescribeServices"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = "ecs:UpdateService",
        Resource = [
          "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:service/${aws_ecs_cluster.course_management_cluster.name}/${aws_ecs_service.course_management_service_dev.name}",
          "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:service/${aws_ecs_cluster.course_management_cluster.name}/${aws_ecs_service.course_management_service_prod.name}",
        ]
      },
      {
        Effect = "Allow",
        Action = "iam:PassRole",
        Resource = aws_iam_role.ecs_execution_role.arn
      }
    ]
  })
}

output "ci_cd_user_access_key_id" {
  value = aws_iam_access_key.ci_cd_user_key.id
}

output "ci_cd_user_secret_access_key" {
  value = aws_iam_access_key.ci_cd_user_key.secret
  sensitive = true
}
