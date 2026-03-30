"""
artixinstall — An interactive TUI installer for Artix Linux.

Entry point: python -m artixinstall

This module contains the main application loop, the main menu with all
configuration items, and the installation orchestration logic.
It mirrors archinstall's full feature set, adapted for Artix Linux with
support for all four init systems.
"""

import curses
import os
import sys
import shutil
from pathlib import Path

from artixinstall.tui.screen import Screen, VERSION, COLOR_VALUE_SET, COLOR_VALUE_UNSET, COLOR_TITLE, COLOR_ERROR, COLOR_SEPARATOR
from artixinstall.tui.menu import run_menu, MenuItem
from artixinstall.tui.prompts import confirm_destructive, show_progress
from artixinstall.utils.log import init_log, log_info, log_error

# ── All installer modules ──
from artixinstall.installer.disk import (
    configure_disk, partition_disk, format_partitions,
    mount_partitions, unmount_all, is_efi, setup_luks_hooks,
    cleanup_install_environment,
)
from artixinstall.installer.init import (
    configure_init, get_base_packages, enable_services,
    get_all_service_packages, INIT_SYSTEMS,
)
from artixinstall.installer.base import (
    install_base_system, install_extra_packages,
    generate_fstab, copy_mirrorlist, copy_pacman_conf,
)
from artixinstall.installer.prereqs import install_live_prerequisites, check_live_environment
from artixinstall.installer.locale import (
    configure_locale, configure_timezone, configure_keymap,
    apply_locale, apply_timezone, apply_keymap,
)
from artixinstall.installer.network import (
    configure_hostname, configure_network, apply_hostname,
    get_network_packages, get_network_services,
)
from artixinstall.installer.users import (
    configure_root_password, configure_user,
    apply_root_password, apply_user,
)
from artixinstall.installer.bootloader import (
    configure_bootloader, apply_bootloader, get_bootloader_packages,
)
from artixinstall.installer.desktop import (
    configure_desktop, get_desktop_packages, get_desktop_services,
    get_desktop_label,
)
from artixinstall.installer.hardware import (
    configure_hardware, HardwareConfig, apply_laptop_power,
)
from artixinstall.installer.packages import (
    configure_kernel, configure_audio, configure_profile,
    configure_additional_packages, configure_repositories,
    get_kernel_packages, get_kernel_name, get_kernel_label,
    get_audio_packages, get_audio_label,
    get_profile_packages, get_profile_services, get_profile_label,
    apply_repositories,
)


class InstallerConfig:
    """
    Central configuration state for the installer.

    All user choices are stored here and used during installation.
    """

    def __init__(self) -> None:
        # ── Required ──
        self.disk: dict | None = None
        self.root_password: str = ""

        # ── Locale & region ──
        self.locale: str = "en_US.UTF-8"
        self.timezone: str = ""
        self.keymap: str = "us"
        self.mirrors: str = "default"
        self.hostname: str = "artix"

        # ── Users ──
        self.user: dict | None = None

        # ── System ──
        self.init_system: str = "openrc"
        self.kernel: str = "linux"
        self.bootloader: str = "grub"

        # ── Profile & desktop ──
        self.profile: str = "desktop"
        self.desktop: str = "none"
        self.audio: str = "pipewire"

        # ── Hardware ──
        self.hardware: HardwareConfig | None = None

        # ── Network ──
        self.network: str = "NetworkManager"

        # ── Packages ──
        self.additional_packages: list[str] = []
        self.repositories: dict = {"multilib": True, "universe": False}


def _build_main_menu(config: InstallerConfig) -> list[MenuItem]:
    """Build the main menu items reflecting current configuration state."""

    # ── Disk ──
    disk_val = "not set"
    disk_set = False
    if config.disk:
        disk = config.disk["disk"]
        fs = config.disk.get("filesystem", "?")
        layout = config.disk.get("layout", "?")
        enc = " + LUKS" if config.disk.get("encrypt") else ""
        disk_val = f"{disk} ({fs}, {layout}{enc})"
        disk_set = True

    # ── Bootloader ──
    boot_label = config.bootloader.upper()

    # ── Users ──
    user_val = "not set"
    user_set = False
    if config.user:
        u = config.user["username"]
        s = " (sudo)" if config.user.get("sudo") else ""
        user_val = f"{u}{s}"
        user_set = True

    root_val = "not set"
    root_set = False
    if config.root_password:
        root_val = "set"
        root_set = True

    # ── System ──
    init_label = INIT_SYSTEMS.get(config.init_system, {}).get("label", config.init_system)
    kernel_label = get_kernel_label(config.kernel)
    audio_label = get_audio_label(config.audio)
    profile_label = get_profile_label(config.profile)
    de_label = get_desktop_label(config.desktop)

    # ── Hardware ──
    hw_val = "not configured"
    hw_set = False
    if config.hardware:
        hw_val = config.hardware.get_summary()
        hw_set = True

    # ── Others ──
    tz_val = config.timezone or "not set"
    tz_set = bool(config.timezone)

    pkg_count = len(config.additional_packages)
    pkg_val = f"{pkg_count} selected" if pkg_count else "none"
    pkg_set = pkg_count > 0

    repo_parts = []
    if config.repositories.get("multilib"):
        repo_parts.append("multilib")
    if config.repositories.get("universe"):
        repo_parts.append("universe")
    repo_val = ", ".join(repo_parts) if repo_parts else "default"

    return [
        # ── Locale & Region ──
        MenuItem("Language", "locale", config.locale, True),
        MenuItem("Timezone", "timezone", tz_val, tz_set),
        MenuItem("Keyboard layout", "keymap", config.keymap, True),
        MenuItem("Mirrors", "mirrors", config.mirrors, True),
        MenuItem("", "", is_separator=True),

        # ── Disk & Boot ──
        MenuItem("Disk configuration", "disk", disk_val, disk_set),
        MenuItem("Bootloader", "bootloader", boot_label, True),
        MenuItem("", "", is_separator=True),

        # ── System ──
        MenuItem("Hostname", "hostname", config.hostname, True),
        MenuItem("Root password", "root_password", root_val, root_set),
        MenuItem("User account", "user", user_val, user_set),
        MenuItem("", "", is_separator=True),

        # ── Profile & Software ──
        MenuItem("Profile", "profile", profile_label, True),
        MenuItem("Init system", "init_system", init_label, True),
        MenuItem("Kernel", "kernel", kernel_label, True),
        MenuItem("Desktop environment", "desktop", de_label, True),
        MenuItem("Audio", "audio", audio_label, True),
        MenuItem("Graphics & hardware", "hardware", hw_val, hw_set),
        MenuItem("Network manager", "network", config.network, True),
        MenuItem("", "", is_separator=True),

        # ── Extra ──
        MenuItem("Additional packages", "packages", pkg_val, pkg_set),
        MenuItem("Optional repositories", "repositories", repo_val, True),
        MenuItem("", "", is_separator=True),

        # ── Actions ──
        MenuItem("Install", "install"),
        MenuItem("Abort", "abort"),
    ]


def _handle_menu_choice(screen: Screen, config: InstallerConfig,
                         key: str) -> bool:
    """
    Handle a main menu selection.

    Returns True if the application should continue, False to exit.
    """
    if key == "disk":
        result = configure_disk(screen)
        if result is not None:
            config.disk = result

    elif key == "locale":
        result = configure_locale(screen)
        if result is not None:
            config.locale = result

    elif key == "timezone":
        result = configure_timezone(screen)
        if result is not None:
            config.timezone = result

    elif key == "keymap":
        result = configure_keymap(screen)
        if result is not None:
            config.keymap = result

    elif key == "mirrors":
        _configure_mirrors(screen, config)

    elif key == "hostname":
        result = configure_hostname(screen)
        if result is not None:
            config.hostname = result

    elif key == "root_password":
        result = configure_root_password(screen)
        if result is not None:
            config.root_password = result

    elif key == "user":
        result = configure_user(screen)
        if result is not None:
            config.user = result

    elif key == "profile":
        result = configure_profile(screen)
        if result is not None:
            config.profile = result

    elif key == "init_system":
        result = configure_init(screen)
        if result is not None:
            config.init_system = result

    elif key == "kernel":
        result = configure_kernel(screen)
        if result is not None:
            config.kernel = result

    elif key == "desktop":
        result = configure_desktop(screen)
        if result is not None:
            config.desktop = result

    elif key == "audio":
        result = configure_audio(screen)
        if result is not None:
            config.audio = result

    elif key == "hardware":
        result = configure_hardware(screen)
        if result is not None:
            config.hardware = result

    elif key == "network":
        result = configure_network(screen)
        if result is not None:
            config.network = result

    elif key == "bootloader":
        result = configure_bootloader(screen)
        if result is not None:
            config.bootloader = result

    elif key == "packages":
        result = configure_additional_packages(screen, config.additional_packages)
        if result is not None:
            config.additional_packages = result

    elif key == "repositories":
        result = configure_repositories(screen)
        if result is not None:
            config.repositories = result

    elif key == "install":
        return _run_installation(screen, config)

    elif key == "abort":
        if confirm_destructive(screen,
                "Are you sure you want to abort the installer?\n"
                "No changes will be made to your system."):
            return False

    return True


def _configure_mirrors(screen: Screen, config: InstallerConfig) -> None:
    """Handle mirror configuration."""
    from artixinstall.tui.menu import run_selection_menu
    from artixinstall.tui.prompts import text_input

    choice = run_selection_menu(screen, "Mirror configuration", [
        "Use default mirrors",
        "Copy from live environment",
        "Enter custom mirror URL",
    ])
    if choice is None:
        return

    if choice.startswith("Use default"):
        config.mirrors = "default"
    elif choice.startswith("Copy from"):
        config.mirrors = "live"
    elif choice.startswith("Enter custom"):
        url = text_input(screen, "Enter mirror URL:",
                         default="https://mirror1.artixlinux.org/repos/$repo/os/$arch")
        if url:
            config.mirrors = url


def _validate_config(screen: Screen, config: InstallerConfig) -> bool:
    """Validate that all required fields are set for installation."""
    errors = []

    if config.disk is None:
        errors.append("• Disk configuration is required")
    if not config.root_password:
        errors.append("• Root password is required")
    if not config.timezone:
        errors.append("• Timezone is required")

    if errors:
        screen.show_error(
            "Cannot proceed with installation.\n"
            "The following items need to be configured:\n\n"
            + "\n".join(errors)
        )
        return False
    return True


def _show_summary(screen: Screen, config: InstallerConfig) -> bool:
    """
    Show a full summary of all chosen options and ask for final confirmation.

    Returns True if the user confirms, False otherwise.
    """
    disk_info = config.disk or {}
    user_info = config.user or {}
    init_label = INIT_SYSTEMS.get(config.init_system, {}).get("label", config.init_system)
    de_label = get_desktop_label(config.desktop)
    kernel_label = get_kernel_label(config.kernel)
    audio_label = get_audio_label(config.audio)
    profile_label = get_profile_label(config.profile)

    enc = " (LUKS encrypted)" if disk_info.get("encrypt") else ""
    hw_summary = config.hardware.get_summary() if config.hardware else "not configured"

    lines = [
        f"Disk:              {disk_info.get('disk', '?')} ({disk_info.get('filesystem', '?')}, {disk_info.get('layout', '?')}){enc}",
        f"Swap:              {'Yes' if disk_info.get('swap') else 'No'}",
        f"Boot mode:         {'UEFI' if disk_info.get('efi') else 'BIOS'}",
        f"Bootloader:        {config.bootloader}",
        "",
        f"Profile:           {profile_label}",
        f"Init system:       {init_label}",
        f"Kernel:            {kernel_label}",
        f"Desktop:           {de_label}",
        f"Audio:             {audio_label}",
        f"Hardware:          {hw_summary}",
        "",
        f"Locale:            {config.locale}",
        f"Timezone:          {config.timezone}",
        f"Keymap:            {config.keymap}",
        f"Hostname:          {config.hostname}",
        f"Root password:     ******",
        f"User:              {user_info.get('username', 'none')}" + (f" (sudo)" if user_info.get('sudo') else ""),
        f"Network:           {config.network}",
        f"Extra packages:    {len(config.additional_packages)}",
        f"Mirrors:           {config.mirrors}",
    ]

    screen.clear()
    screen.draw_header()
    screen.draw_text(screen.content_y, 2, "Installation Summary", COLOR_TITLE, bold=True)
    screen.draw_text(screen.content_y + 1, 2, "─" * 55, COLOR_SEPARATOR)

    for i, line in enumerate(lines):
        y = screen.content_y + 3 + i
        if y >= screen.footer_y - 2:
            break
        color = COLOR_VALUE_SET if line.strip() else COLOR_SEPARATOR
        screen.draw_text(y, 4, line, color if ":" in line else COLOR_SEPARATOR)

    screen.draw_footer("Press Enter to begin installation  ESC to go back")
    screen.stdscr.refresh()

    while True:
        key = screen.get_input()
        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return True
        if key == 27:  # ESC
            return False
        if key == curses.KEY_RESIZE:
            screen.refresh_size()


def _run_installation(screen: Screen, config: InstallerConfig) -> bool:
    """
    Orchestrate the full installation process.

    Returns True to keep the main menu running, False to exit.
    """
    # Validate required fields
    if not _validate_config(screen, config):
        return True  # Stay in main menu

    # Show summary and get confirmation
    if not _show_summary(screen, config):
        return True  # Go back to main menu

    # ══════════════════════════════════════
    # Collect all packages
    # ══════════════════════════════════════
    extra_packages = []

    # Bootloader packages
    efi = config.disk.get("efi", is_efi()) if config.disk else is_efi()
    extra_packages.extend(get_bootloader_packages(config.bootloader, efi))

    # Audio packages
    extra_packages.extend(get_audio_packages(config.audio))

    # Network packages
    extra_packages.extend(get_network_packages(config.network))

    # Network service init-specific packages
    net_services = get_network_services(config.network)
    extra_packages.extend(get_all_service_packages(net_services, config.init_system))

    # Desktop packages
    extra_packages.extend(get_desktop_packages(config.desktop))

    # Desktop service init-specific packages
    de_services = get_desktop_services(config.desktop)
    extra_packages.extend(get_all_service_packages(de_services, config.init_system))

    # Profile packages
    extra_packages.extend(get_profile_packages(config.profile))

    # Hardware packages
    if config.hardware:
        extra_packages.extend(config.hardware.get_all_packages())

    # User-selected additional packages
    extra_packages.extend(config.additional_packages)

    # Kernel packages (headers etc.)
    kernel_pkgs = get_kernel_packages(config.kernel)
    extra_packages.extend(kernel_pkgs)

    # Build the list of services to enable
    services_to_enable = list(net_services) + list(de_services)

    # Add hardware services
    if config.hardware:
        services_to_enable.extend(config.hardware.get_services())

    # Add profile services
    profile_services = get_profile_services(config.profile)
    services_to_enable.extend(profile_services)

    # Custom mirror setup
    if config.mirrors not in ("default", "live") and config.disk:
        _write_custom_mirrors(config)

    # ══════════════════════════════════════
    # Build installation steps
    # ══════════════════════════════════════
    steps = []

    steps.append({
        "label": "Installing live environment packages",
        "func": lambda: install_live_prerequisites(config.disk),
    })

    steps.append({
        "label": "Checking live environment",
        "func": lambda: check_live_environment(config.disk),
    })

    steps.append({
        "label": "Cleaning previous install state",
        "func": lambda: cleanup_install_environment(config.disk),
    })

    # Partitioning (auto only)
    if config.disk and config.disk.get("layout") == "auto":
        steps.append({
            "label": "Partitioning disk",
            "func": lambda: partition_disk(config.disk),
        })

    steps.append({
        "label": "Formatting filesystems",
        "func": lambda: format_partitions(config.disk),
    })

    steps.append({
        "label": "Mounting partitions",
        "func": lambda: mount_partitions(config.disk),
    })

    # Copy mirrors before basestrap
    steps.append({
        "label": "Setting up mirrors",
        "func": lambda: copy_mirrorlist(),
    })

    # Base system installation (the big one)
    steps.append({
        "label": "Installing base system",
        "func": lambda pkgs=extra_packages: install_base_system(
            config.init_system, pkgs, config.kernel, live_output=True
        ),
        "live_output": True,
    })

    steps.append({
        "label": "Generating fstab",
        "func": lambda: generate_fstab(),
    })

    # Configure repositories in target
    steps.append({
        "label": "Configuring repositories",
        "func": lambda: apply_repositories(config.repositories),
    })

    # LUKS hooks (if encryption is enabled)
    if config.disk and config.disk.get("encrypt"):
        steps.append({
            "label": "Configuring encryption hooks",
            "func": lambda: setup_luks_hooks(config.disk),
        })

    steps.append({
        "label": "Setting timezone",
        "func": lambda: apply_timezone(config.timezone),
    })

    steps.append({
        "label": "Setting locale",
        "func": lambda: apply_locale(config.locale),
    })

    steps.append({
        "label": "Setting keyboard layout",
        "func": lambda: apply_keymap(config.keymap),
    })

    steps.append({
        "label": "Setting hostname",
        "func": lambda: apply_hostname(config.hostname),
    })

    steps.append({
        "label": "Setting root password",
        "func": lambda: apply_root_password(config.root_password),
    })

    if config.user:
        steps.append({
            "label": f"Creating user '{config.user['username']}'",
            "func": lambda: apply_user(config.user),
        })

    steps.append({
        "label": "Installing bootloader",
        "func": lambda: apply_bootloader(
            config.bootloader, config.disk, config.kernel
        ),
    })

    if services_to_enable:
        steps.append({
            "label": "Enabling services",
            "func": lambda svcs=list(set(services_to_enable)): enable_services(
                svcs, config.init_system
            ),
        })

    # Laptop power management
    if config.hardware and config.hardware.install_laptop_power:
        steps.append({
            "label": "Configuring power management",
            "func": lambda: apply_laptop_power(config.init_system),
        })

    steps.append({
        "label": "Finalizing installation",
        "func": lambda: _finalize(config),
    })

    # ══════════════════════════════════════
    # Run the installation
    # ══════════════════════════════════════
    success = show_progress(screen, steps)

    if success:
        screen.show_success(
            "Installation complete!\n\n"
            "You may now reboot into your new Artix Linux system.\n\n"
            "  1. Exit the installer\n"
            "  2. Run: umount -R /mnt\n"
            "  3. Run: reboot\n\n"
            "Enjoy your new system!"
        )
        return False  # Exit the installer
    else:
        screen.show_error(
            "Installation encountered errors.\n"
            "Check /tmp/artixinstall.log for details.\n\n"
            "You can retry from the main menu."
        )
        return True  # Stay in main menu


def _finalize(config: InstallerConfig) -> tuple[bool, str]:
    """Final cleanup and configuration steps."""
    from artixinstall.utils.shell import run

    # Copy pacman.conf
    copy_pacman_conf()

    # Enable parallel downloads in pacman.conf
    pacman_conf = "/mnt/etc/pacman.conf"
    if os.path.isfile(pacman_conf):
        try:
            with open(pacman_conf, "r") as f:
                content = f.read()
            content = content.replace(
                "#ParallelDownloads = 5",
                "ParallelDownloads = 5",
            )
            # Enable Color
            content = content.replace(
                "#Color",
                "Color",
            )
            with open(pacman_conf, "w") as f:
                f.write(content)
        except OSError:
            pass

    log_info("Installation finalized")
    return True, ""


def _write_custom_mirrors(config: InstallerConfig) -> None:
    """Write custom mirror configuration before basestrap."""
    if config.mirrors in ("default", "live"):
        return

    mirror_path = "/etc/pacman.d/mirrorlist"
    try:
        with open(mirror_path, "w") as f:
            f.write(f"# Custom mirror set by artixinstall\n")
            f.write(f"Server = {config.mirrors}\n")
        log_info(f"Custom mirror written: {config.mirrors}")
    except OSError as e:
        log_error(f"Failed to write custom mirror: {e}")


def _main_loop(stdscr: curses.window) -> None:
    """
    Main application loop — draws the main menu and dispatches selections.
    """
    screen = Screen(stdscr)
    config = InstallerConfig()

    while True:
        items = _build_main_menu(config)
        selected = run_menu(
            screen,
            "Artix Linux Installation",
            items,
            footer="↑↓ Navigate  Enter Configure  Install when ready",
            allow_escape=False,  # Main menu never exits on ESC
        )

        if selected is None:
            continue  # ESC pressed on main menu — ignore

        should_continue = _handle_menu_choice(screen, config, selected.key)
        if not should_continue:
            break


def main() -> None:
    """Entry point for the artixinstall application."""
    # Check for root privileges
    if os.geteuid() != 0:
        print("\033[1;31m╔══════════════════════════════════════════════════════════╗\033[0m")
        print("\033[1;31m║  artixinstall must be run as root.                       ║\033[0m")
        print("\033[1;31m║  Please run: sudo python -m artixinstall                 ║\033[0m")
        print("\033[1;31m╚══════════════════════════════════════════════════════════╝\033[0m")
        sys.exit(1)

    # Check terminal size
    try:
        cols, lines = os.get_terminal_size()
        if cols < 60 or lines < 20:
            print(f"Terminal too small ({cols}x{lines}). Minimum: 60x20.")
            sys.exit(1)
    except OSError:
        pass  # Can't check — proceed anyway

    # Initialize logging
    init_log()
    log_info(f"artixinstall v{VERSION} starting")

    # Run the curses application
    try:
        curses.wrapper(_main_loop)
    except KeyboardInterrupt:
        print("\nInstallation aborted by user.")
        sys.exit(130)
    except Exception as e:
        # Last-resort error handler — should never be reached
        log_error(f"Fatal error: {e}")
        import traceback
        log_error(traceback.format_exc())
        print(f"\n\033[1;31mFatal error:\033[0m {e}")
        print(f"Check /tmp/artixinstall.log for details.")
        sys.exit(1)

    print("Thank you for using artixinstall!")


if __name__ == "__main__":
    main()
