"""Write Genmedia cron failures to server logs and alert the internal ops inbox."""

import os
import subprocess
import sys

ALERT_TIMEOUT_SECONDS = 30
SYSLOG_TIMEOUT_SECONDS = 5
DEFAULT_ALERT_COMMAND = "/home/alexey/.local/bin/principal-alert.sh"


def report_failure(job, error):
    """Log an error and invoke the host's internal alert hook.

    The alert hook writes a local alert log before attempting delivery, so a
    mail transport failure still leaves evidence on the server.
    """
    message = f"{job} failed: {error}"
    print(f"ERROR: {message}", file=sys.stderr)

    try:
        subprocess.run(
            ["/usr/bin/logger", "-p", "user.err", "-t", "genmedia-cron", message],
            check=False,
            timeout=SYSLOG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: could not write Genmedia failure to syslog: {exc}", file=sys.stderr)

    command = DEFAULT_ALERT_COMMAND
    alert_env = os.environ.copy()
    alert_env["PING_ALERT_MESSAGE"] = message
    alert_env["PRINCIPAL_ALERT_TO"] = "dev@dtcdev.click"
    try:
        subprocess.run(
            [command],
            check=True,
            capture_output=True,
            text=True,
            timeout=ALERT_TIMEOUT_SECONDS,
            env=alert_env,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: Genmedia ops alert delivery failed: {exc}", file=sys.stderr)
