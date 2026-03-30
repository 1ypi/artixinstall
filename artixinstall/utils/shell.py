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

from artixinstall.utils.log import log_cmd, log_output, log_error, log_info, log_live_output

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


def run_live_result(
    cmd: Union[str, list],
    chroot: bool = False,
    input_text: str | None = None,
    timeout: int | None = None,
) -> tuple[int, str]:
    """
    Execute a command with direct terminal access and return (rc, error_message).

    Used for commands like `basestrap` where seeing live output is more useful
    than capturing it in the curses UI.
    """
    if isinstance(cmd, list):
        cmd_value = [str(c) for c in cmd]
        log_cmd("(live) " + " ".join(shlex.quote(c) for c in cmd_value))
    else:
        cmd_value = cmd
        log_cmd(f"(live) {cmd}")

    if chroot:
        if isinstance(cmd, list):
            inner_cmd = " ".join(shlex.quote(str(c)) for c in cmd)
        else:
            inner_cmd = cmd
        cmd_value = ["artix-chroot", MOUNT_POINT, "/bin/bash", "-c", inner_cmd]
        log_cmd("(live) " + " ".join(shlex.quote(c) for c in cmd_value))

    try:
        process = subprocess.Popen(
            cmd_value,
            shell=isinstance(cmd_value, str),
            text=True,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )

        if input_text is not None and process.stdin is not None:
            process.stdin.write(input_text)
            process.stdin.close()

        output_tail: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_live_output(line)
            output_tail.append(line.rstrip())
            if len(output_tail) > 20:
                output_tail.pop(0)

        result_rc = process.wait(timeout=timeout)
        if result_rc != 0:
            msg = "\n".join(output_tail).strip() or f"Command exited with status {result_rc}"
            log_error(msg)
            return result_rc, msg
        log_info("Live command completed successfully")
        return result_rc, ""
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
        msg = f"Live command timed out after {timeout}s"
        log_error(msg)
        return 124, msg
    except Exception as e:
        msg = f"Failed to execute live command: {e}"
        log_error(msg)
        return 1, msg


def command_exists(command: str) -> bool:
    """Return True if a command is available in PATH."""
    return shutil.which(command) is not None
