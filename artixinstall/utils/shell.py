"""
artixinstall.utils.shell — Safe subprocess wrapper with logging.

Provides a single `run()` function that executes shell commands, optionally
inside a chroot, captures all output, logs everything, and never raises
exceptions — always returning a result tuple so callers can handle errors.
"""

import shlex
import shutil
import subprocess
from typing import Union

from artixinstall.utils.log import log_cmd, log_output, log_error

# The mount point used for the target system
MOUNT_POINT = "/mnt"


def run(
    cmd: Union[str, list],
    chroot: bool = False,
    input_text: str | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """
    Execute a shell command and return (returncode, stdout, stderr).

    Parameters
    ----------
    cmd : str or list
        The command to execute. If a string, it is run through the shell.
        If a list, it is passed directly to subprocess.
    chroot : bool
        If True, the command is wrapped to run inside artix-chroot /mnt.
    input_text : str or None
        Optional text to pipe to the command's stdin.
    timeout : int or None
        Optional timeout in seconds.

    Returns
    -------
    tuple[int, str, str]
        (return_code, stdout, stderr). Never raises — errors are returned
        as non-zero return codes with stderr populated.
    """
    use_shell = isinstance(cmd, str) or chroot
    if isinstance(cmd, list):
        cmd_value = [str(c) for c in cmd]
        log_cmd(" ".join(shlex.quote(c) for c in cmd_value))
    else:
        cmd_value = cmd
        log_cmd(cmd)

    if chroot:
        if isinstance(cmd, list):
            inner_cmd = " ".join(shlex.quote(str(c)) for c in cmd)
        else:
            inner_cmd = cmd
        cmd_value = ["artix-chroot", MOUNT_POINT, "/bin/bash", "-c", inner_cmd]
        use_shell = False
        log_cmd(" ".join(shlex.quote(c) for c in cmd_value))

    try:
        result = subprocess.run(
            cmd_value,
            shell=use_shell,
            capture_output=True,
            text=True,
            input=input_text,
            timeout=timeout,
        )
        log_output(result.stdout, result.stderr)
        return (result.returncode, result.stdout, result.stderr)

    except subprocess.TimeoutExpired:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(shlex.quote(str(c)) for c in cmd)
        msg = f"Command timed out after {timeout}s: {cmd_str}"
        log_error(msg)
        return (124, "", msg)

    except Exception as e:
        msg = f"Failed to execute command: {e}"
        log_error(msg)
        return (1, "", msg)


def run_live(cmd: str) -> int:
    """
    Execute a command that needs direct terminal access (e.g. cfdisk).

    This does NOT capture output — the command takes over the terminal.
    Returns the exit code.
    """
    log_cmd(f"(live) {cmd}")
    try:
        result = subprocess.run(cmd, shell=True)
        return result.returncode
    except Exception as e:
        log_error(f"Live command failed: {e}")
        return 1


def command_exists(command: str) -> bool:
    """Return True if a command is available in PATH."""
    return shutil.which(command) is not None
