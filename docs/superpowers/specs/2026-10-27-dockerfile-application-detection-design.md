# Dockerfile Application Detection

## Intent

Allow Arfeen Cloud to deploy repositories such as CardioVision AI that provide a production-ready root `Dockerfile` but do not have a root-level framework marker such as `package.json` or `requirements.txt`.

## Goals

- Prefer a repository's existing root `Dockerfile` over generated framework Dockerfiles.
- Determine the application container port from a numeric `EXPOSE` instruction in the final Dockerfile stage.
- Build and run the existing Dockerfile through the current deployment path.
- Preserve current detection behavior for repositories without a Dockerfile.
- Return a clear 422 error when a custom Dockerfile does not declare a usable TCP port.
- Add regression tests covering a Dockerfile-only repository and the missing-port error.

## Non-goals

- Supporting Docker Compose files inside deployed repositories.
- Accepting a manually entered container port in the UI.
- Inferring ports from arbitrary shell commands, environment variables, or application source.
- Changing the current GitHub credential or deployment pipeline behavior.

## Approaches considered

1. **Detect existing Dockerfiles and parse `EXPOSE` — selected.** This supports the repository as authored and benefits future Dockerized applications with a small backend change.
2. Add a dummy root framework marker to CardioVision. Rejected because it is repository-specific and makes detection depend on misleading metadata.
3. Add a manual container-port field to the UI and API. Rejected for now because it expands the interface and validation surface when the Dockerfile already supplies the information.

## Behavior

When `detect_framework` finds a root `Dockerfile`, it reads the file and examines the final build stage. It accepts the final numeric TCP port declared by `EXPOSE`, labels the detected framework as `Dockerfile`, and leaves the file untouched. If there is no numeric exposed port, detection stops with an actionable 422 response asking the repository owner to add `EXPOSE <port>`. Existing framework detection remains the fallback only when no root Dockerfile exists.

The fix will be developed test-first, verified with the backend test suite, frontend build, Compose validation, and the CardioVision repository shape, then pushed to `main` so the existing production pipeline deploys it.

