#!/usr/bin/env bash
# Deploy to AWS: images -> ECR, Terraform apply, frontend -> S3, CloudFront invalidation. The
# running worker is stopped, so the next call starts one with the new image. Merges into main deploy code
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

# A worker that's already running keeps the old image until it exits (10 idle minutes, and
# every call resets that): call ed6205aaca08 (2026-11-11), two minutes after a deploy, still ran
# the previous code. Stop it, so the next call wakes a worker with the new image. A call in
# progress right now would be cut off.
echo "== Stopping the running worker (the next call starts one with the new image)"
cluster=$(tf output -raw agent_cluster)
for task in $(aws ecs list-tasks --cluster "$cluster" --family carhaul-agent \
  --desired-status RUNNING --query 'taskArns[]' --output text); do
  aws ecs stop-task --cluster "$cluster" --task "$task" \
    --reason "deploy: new image" --query 'task.taskArn' --output text
done

echo "== Done: $(tf output -raw url)"
