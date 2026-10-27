# Live deployment jobs and logs

User authorized planning, implementation, Git push and production deployment without further approval.

## Design

Deploy submits a durable job and immediately opens a progress dialog. SQLite stores job metadata and ordered timestamped logs; a single background worker serializes builds and prevents duplicate active jobs for an application. Browser disconnects do not cancel builds. On backend restart, unfinished jobs become interrupted with an explicit explanation. Credentials stay in memory and log messages are redacted before persistence. Logs are bounded to 8 MiB per job and fetched in cursor-based pages.

GitHub, ZIP and redeploy flows use the same queue. Git progress, Docker build output, framework detection, container startup and initial health status appear in a focused console. Applications and Deployments both list jobs, including running and failed attempts, and let the administrator reopen the console. The console supports reconnecting, follow-scroll, copying and downloading logs. Existing application controls and history remain available.

## Execution

1. Implement/test persistent job lifecycle, duplicate prevention, redaction, log cursors and restart recovery.
2. Add authenticated submission/status/download endpoints, stream Git and Docker output into the active job, and report startup failures.
3. Build accessible, responsive progress dialog and recent-jobs list; switch all deployment forms to immediate job submission.
4. Verify backend tests, frontend production build and deployment regression suite; review the change.
5. Commit, merge to main and push. Wait for the actual production workflow; verify live code/config, authenticated job routes and a controlled successful/failed job. Keep the user's existing application data/secrets intact.

## Limits

Jobs persist across browser navigation; a process restart interrupts builds rather than replaying secret-bearing payloads. This ships live output and initial container verification, not an interactive shell or build cancellation. No credentials are stored in the new job/log tables.
