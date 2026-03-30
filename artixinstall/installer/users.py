"""
artixinstall.installer.users — Root password setup and user account creation.

Handles setting the root password and creating user accounts with optional
sudo/wheel group membership.
"""

from artixinstall.utils.shell import run
from artixinstall.utils.log import log_info, log_error
from artixinstall.utils.validate import is_valid_username, is_valid_password, sanitize_shell_arg
from artixinstall.tui.screen import Screen
from artixinstall.tui.prompts import password_input_confirmed, text_input, yes_no


def configure_root_password(screen: Screen) -> str | None:
    """
    Prompt for the root password (twice for confirmation).

    Returns the password string, or None if cancelled.
    Note: The password is returned in memory only and never logged.
    """
    return password_input_confirmed(
        screen,
        prompt="Enter root password",
        confirm_prompt="Confirm root password",
    )


def configure_user(screen: Screen) -> dict | None:
    """
    Interactive user account configuration.

    Returns a dict with keys:
        username: str
        password: str
        sudo: bool

    Or None if cancelled.
    """
    # Ask for username
    username = text_input(
        screen,
        "Enter username (lowercase, alphanumeric/underscore):",
        validator=is_valid_username,
    )
    if username is None:
        return None

    # Ask for password
    password = password_input_confirmed(
        screen,
        prompt=f"Enter password for '{username}'",
        confirm_prompt=f"Confirm password for '{username}'",
    )
    if password is None:
        return None

    # Ask about sudo access
    sudo = yes_no(screen, f"Grant '{username}' sudo (wheel) access?", default=True)
    if sudo is None:
        return None

    return {
        "username": username,
        "password": password,
        "sudo": sudo,
    }


def apply_root_password(password: str) -> tuple[bool, str]:
    """
    Set the root password inside the chroot.

    Uses chpasswd via stdin to avoid the password appearing in process lists.
    """
    safe_pw = sanitize_shell_arg(password)

    rc, _, stderr = run(
        f'echo "root:{safe_pw}" | chpasswd',
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set root password: {stderr}"

    log_info("Root password set")
    return True, ""


def apply_user(user_config: dict) -> tuple[bool, str]:
    """
    Create a user account inside the chroot.

    Steps:
    1. Create user with useradd
    2. Set password with chpasswd
    3. If sudo, uncomment %wheel in /etc/sudoers
    """
    username = sanitize_shell_arg(user_config["username"])
    password = sanitize_shell_arg(user_config["password"])
    sudo = user_config["sudo"]

    # Create user with home directory and bash shell
    groups = "wheel" if sudo else "users"
    rc, _, stderr = run(
        f"useradd -m -G {groups} -s /bin/bash {username}",
        chroot=True,
    )
    if rc != 0:
        # User might already exist — try to continue
        if "already exists" not in stderr:
            return False, f"Failed to create user: {stderr}"
        log_info(f"User {username} already exists, continuing")

    # Set password
    rc, _, stderr = run(
        f'echo "{username}:{password}" | chpasswd',
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set user password: {stderr}"

    # Enable sudo for wheel group
    if sudo:
        rc, _, stderr = run(
            "sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers",
            chroot=True,
        )
        if rc != 0:
            # Try alternate format
            rc, _, stderr = run(
                "sed -i 's/^# %wheel ALL=(ALL) ALL/%wheel ALL=(ALL) ALL/' /etc/sudoers",
                chroot=True,
            )
            if rc != 0:
                log_error(f"Failed to enable sudo for wheel: {stderr}")
                # Non-fatal — continue

    run(
        f"mkdir -p /home/{username}/Desktop /home/{username}/Documents /home/{username}/Downloads "
        f"/home/{username}/Music /home/{username}/Pictures /home/{username}/Public "
        f"/home/{username}/Templates /home/{username}/Videos",
        chroot=True,
    )
    run(
        f"chown -R {username}:{username} /home/{username}",
        chroot=True,
    )

    if run("command -v xdg-user-dirs-update", chroot=True)[0] == 0:
        rc, _, stderr = run(
            f"su - {username} -c 'xdg-user-dirs-update'",
            chroot=True,
        )
        if rc != 0:
            log_error(f"Failed to initialize XDG user dirs: {stderr}")

    log_info(f"User '{username}' created (sudo={sudo})")
    return True, ""
