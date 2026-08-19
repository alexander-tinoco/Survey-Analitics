# Continuous integration

The pipeline is defined by the [`Jenkinsfile`](../Jenkinsfile) at the root of
this repository, not by configuration stored inside a Jenkins server.

That distinction is the point. Jenkins also supports *freestyle* jobs, where
the build steps are typed into a web form — and where the configuration then
lives only on that server. A pipeline defined that way cannot be reviewed in a
pull request, has no history of who changed it or why, disappears with the
machine, and cannot differ between branches. A `Jenkinsfile` is versioned
alongside the code it tests, so changing the build is a commit like any other.

## What the pipeline does

| Stage | What it runs |
| --- | --- |
| Prepare | `cp .env.example .env` — CI has no `.env`, and the example holds safe development defaults |
| Build | `docker compose build` |
| Lint | `ruff check` and `ruff format --check` |
| Test | `pytest`, which carries the 85% coverage gate from `pyproject.toml` |
| Engine coverage | `pytest tests/analytics` against a separate **100%** gate on `apps/analytics/engine/` |

Every stage runs through `docker compose`, using the same images a developer
runs locally. A green build here means the same commands pass on a
workstation — there is no separate CI environment to drift.

The engine is held to a stricter gate than the rest of the project because it
is pure and fast to test: an untested branch there produces a plausible wrong
number rather than a crash, which is the failure mode this project spends most
of its effort avoiding.

`post { always { docker compose down -v } }` tears the stack down even when a
stage fails. Without it a broken build leaves Postgres running and the next
build collides on the port.

## Running Jenkins locally

A Jenkins service is included in `docker-compose.yml` behind a `ci` profile, so
the normal development stack does not start it.

```bash
make ci-up          # http://localhost:8080
make ci-logs        # follow startup
make ci-down
```

The setup wizard is disabled, since the pipeline needs no UI configuration.

### Connecting it to this repository

1. Open <http://localhost:8080>.
2. **New Item** → name it `survey-analytics` → choose **Pipeline** → OK.
3. Under **Pipeline**, set *Definition* to **Pipeline script from SCM**.
4. *SCM* → **Git**. For the local checkout, use Repository URL `/workspace`
   (the project is mounted read-only in the container). For GitHub, use
   `https://github.com/alexander-tinoco/Survey-Analitics.git` and add
   credentials if the repository is private.
5. *Branch Specifier*: `*/main`.
6. *Script Path*: `Jenkinsfile` (the default).
7. **Save**, then **Build Now**.

For a repository with several branches, **Multibranch Pipeline** is the better
item type: it scans branches, finds the `Jenkinsfile` in each, and builds them
without another job per branch.

### Why the container mounts the Docker socket

The pipeline builds and runs this project with `docker compose`, so Jenkins
needs a Docker daemon. Rather than running Docker inside Docker, the container
is given the host's socket.

**This grants the container root-equivalent access to the host machine.** It is
a reasonable trade for a CI server you run locally and control. Do not carry
this arrangement to a shared or internet-reachable Jenkins without replacing it
with a proper agent setup.

## Status

Verified. The pipeline runs green end to end against a local Jenkins server:

```
✓ Checkout            ✓ Lint             (ruff check + format --check)
✓ Prepare environment ✓ Test             387 passed, 99.57% coverage
✓ Build               ✓ Engine coverage  219 passed, 100.00% coverage
                                          7m 21s total
```

Getting there took seven builds, and every failure was a real problem rather
than a quirk of the setup. Two of them were bugs in the application itself,
invisible to local development:

- **`/app` was not writable by the process that runs in it.** `WORKDIR`
  creates the directory as root and `COPY --chown` only changes the files
  inside it, so the unprivileged user could read its own source but write
  nothing beside it. The bind mount used in development replaced `/app`
  entirely, so the image's permissions were never exercised.
- **The development bind mount broke CI.** Jenkins talks to the host's Docker
  daemon, so a mount written as `.` resolves against the host filesystem
  rather than the path inside the Jenkins container. `/app` came up empty and
  the project was not importable. The compose file was split accordingly.

The rest were setup: no docker client in the base image, no pipeline plugins
without the setup wizard, a core too old for those plugins, local checkouts
disabled by default, and git refusing the mounted repository as having
"dubious ownership".

That last one is worth recording, because the obvious fixes do not work.
`git config --system` is not read by the process Jenkins spawns, and neither
are `GIT_CONFIG_*` environment variables set on the container. The per-user
config is what git actually reads there, so the image writes
`safe.directory` into both `/root/.gitconfig` and
`/var/jenkins_home/.gitconfig`.
