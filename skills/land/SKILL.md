---
name: land
description: "Deploy the current work into Docker for system testing. Use when asked to land, deploy, or bring up the change, or to see it working in the real app rather than in tests."
---

# Land

Deploy the current work into Docker for system testing. All docker knowledge lives
in a per-repo entrypoint; this skill orchestrates and guards it, and never guesses
docker commands.

This is the one path for "make the change work in the real app". When the built-in
`run` skill is reaching for a project-specific way to launch, this is it.

## Entrypoint

- Look for a per-repo entrypoint in this order: `.claude/land.sh`, then a documented
  `make land` target, then a `land` script in the repo.
- **If none is found, stop and ask** how to deploy this repo. Do not infer docker /
  compose commands from `Dockerfile` or `docker-compose.yml`.

## Tiers (from the argument)

- no argument — **sync + restart**: push current code into the container and bounce
  it. Cheap and reversible. Just do it.
- `rebuild` — **rebuild** the image, then restart. Slow but safe. Just do it.
  (Rebuild must produce compiled artifacts, not just a dev environment; chown
  outputs back to `1001:1002` if the build runs as root.)
- `reset` — **tear down** containers / volumes / other services and recreate.
  Destructive. **Before executing, print the exact kill-list** (which containers,
  volumes, and services will be destroyed) and proceed only after showing it. The
  explicit `reset` word is the intent, but reset is never blind.

Pass the tier through to the entrypoint. Report what ran and the result.
