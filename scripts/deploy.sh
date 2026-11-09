#!/usr/bin/env bash
# Deploy to AWS: images -> ECR, Terraform apply, frontend -> S3, CloudFront invalidation. The
# on-demand worker uses the new image the next time it starts. Merges into main deploy code
# automatically (.github/workflows/deploy.yml); run
# this by hand for the first deploy and for infrastructure changes.
# Run from Git Bash in the repo root:  scripts/deploy.sh
# Extra arguments go to `terraform apply` (e.g. -auto-approve).
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-carhaul}" AWS_REGION=us-east-1
# Git Bash would otherwise rewrite arguments like "/*" into Windows paths.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

tf() { terraform -chdir=infra "$@"; }

echo "== Terraform init"
tf init -input=false >/dev/null

# The first deploy needs the image repositories before there is anything to push to them.
if ! aws ecr describe-repositories --repository-names carhaul-api carhaul-agent >/dev/null 2>&1; then
  echo "== Creating the image repositories"
  tf apply -input=false -target=aws_ecr_repository.api -target=aws_ecr_repository.agent "$@"
fi

account=$(aws sts get-caller-identity --query Account --output text)
registry="$account.dkr.ecr.$AWS_REGION.amazonaws.com"
aws ecr get-login-password | docker login --username AWS --password-stdin "$registry" >/dev/null

echo "== Building and pushing the API image"
# Lambda wants a plain single-platform image (no provenance/SBOM attestations).
docker build --platform linux/amd64 --provenance=false --sbom=false --target lambda \
  -t "$registry/carhaul-api:latest" backend
docker push "$registry/carhaul-api:latest"

echo "== Building and pushing the worker image"
docker build --platform linux/amd64 --provenance=false --sbom=false \
  -t "$registry/carhaul-agent:latest" agent
docker push "$registry/carhaul-agent:latest"

echo "== Terraform apply"
tf apply -input=false "$@"

bucket=$(tf output -raw web_bucket)
distribution=$(tf output -raw distribution_id)

echo "== Building the frontend"
(cd frontend && npm ci --no-audit --no-fund && npm run build)

echo "== Uploading the frontend"
scripts/upload_frontend.sh "$bucket" "$distribution"

echo "== Done: $(tf output -raw url)"
