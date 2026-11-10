# Retired AWS deployment path

Before the Coolify cutover, GitHub Actions built tagged images, pushed them to
Amazon ECR, updated ECS task definitions, and asked ECS to replace the dev or
production service. The production workflow also recorded deployed tags in
`.prod-versions`. The Makefile exposed ECR publish and deploy targets, and the
`tunnel-dev.sh` / `tunnel-prod.sh` scripts opened SSH tunnels to the former RDS
databases.

Those workflows, scripts, task-definition helper, and repository AWS deploy
credentials have been removed. The live path is the `Deploy CMP Coolify
(Contabo)` workflow: it builds to GHCR, deploys the private release service,
and the shared release follower promotes healthy images to the public rolling
application. This file records history only; the old AWS path is not a
supported recovery or deployment option.
