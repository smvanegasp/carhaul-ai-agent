# Lets .github/workflows/deploy.yml deploy code with short-lived credentials (OIDC), no AWS keys
# in GitHub. The role can push both images, roll Lambda and the ECS worker, upload the frontend
# and invalidate CloudFront; infrastructure changes still go through a local `terraform apply`.

locals {
  # GitHub's immutable subject ("owner@ownerId/repo@repoId"), so a deleted and re-created repo
  # with the same name can't match. Check the format with:
  #   gh api repos/smvanegasp/carhaul-ai-agent/actions/oidc/customization/sub
  github_repo = "smvanegasp@145235327/carhaul-ai-agent@1373086768"
}

# One per AWS account, and the pantry (same account) already created it: read it, don't create it.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_deploy" {
  name = "${local.name}-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          # Only workflows running on main (merges), never PRs or other branches.
          "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_deploy" {
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Logins to the private registry and (for the Lambda Web Adapter image) public ECR.
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken", "ecr-public:GetAuthorizationToken", "sts:GetServiceBearerToken",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages",
        ]
        Resource = [aws_ecr_repository.api.arn, aws_ecr_repository.agent.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"]
        Resource = aws_lambda_function.api.arn
      },
      {
        # A new deployment of the same task definition pulls the new ":latest" worker image.
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = aws_ecs_service.agent.id
      },
      {
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.web.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.web.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = "cloudfront:CreateInvalidation"
        Resource = aws_cloudfront_distribution.main.arn
      },
    ]
  })
}

output "github_deploy_role" {
  value = aws_iam_role.github_deploy.arn
}
