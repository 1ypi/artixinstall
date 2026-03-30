"""
artixinstall.installer.packages — Kernel selection, audio server, additional
package management, optional repositories, and installation profiles.

Mirrors archinstall's package-related configuration options.
"""

from pathlib import Path

from artixinstall.utils.log import log_info
from artixinstall.utils.shell import run
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_menu, run_selection_menu, MenuItem
from artixinstall.tui.prompts import text_input, yes_no


# ── Kernel options ──

KERNELS = {
    "linux": {
        "label": "linux (latest stable, recommended)",
        "packages": ["linux", "linux-headers"],
    },
    "linux-lts": {
        "label": "linux-lts (long-term support)",
        "packages": ["linux-lts", "linux-lts-headers"],
    },
    "linux-zen": {
        "label": "linux-zen (optimized for desktop)",
        "packages": ["linux-zen", "linux-zen-headers"],
    },
    "linux-hardened": {
        "label": "linux-hardened (security-focused)",
        "packages": ["linux-hardened", "linux-hardened-headers"],
    },
}


# ── Audio server options ──

AUDIO_SERVERS = {
    "pipewire": {
        "label": "PipeWire (recommended)",
        "packages": [
            "pipewire", "pipewire-pulse", "pipewire-alsa",
            "pipewire-jack", "wireplumber",
        ],
    },
    "pulseaudio": {
        "label": "PulseAudio",
        "packages": [
            "pulseaudio", "pulseaudio-alsa",
            "pulseaudio-bluetooth",
        ],
    },
    "none": {
        "label": "None (no audio server)",
        "packages": [],
    },
}


# ── Installation profiles (archinstall-style presets) ──

PROFILES = {
    "minimal": {
        "label": "Minimal (base system only)",
        "description": "Just the base system, kernel, and bootloader. No extras.",
        "packages": [],
    },
    "desktop": {
        "label": "Desktop (choose DE/WM separately)",
        "description": "A desktop-ready system. Configure DE, audio, and drivers in their respective menus.",
        "packages": [
            "bash-completion", "man-db", "man-pages",
            "usbutils", "pciutils", "lsof",
        ],
    },
    "server": {
        "label": "Server",
        "description": "Headless server with SSH, cron, and essential tools.",
        "packages": [
            "openssh", "cronie", "htop", "tmux",
            "rsync", "curl", "wget",
            "bash-completion", "man-db", "man-pages",
            "usbutils", "pciutils", "lsof",
            "iptables-nft",
        ],
        "services": ["sshd", "cronie"],
    },
    "development": {
        "label": "Development workstation",
        "description": "Desktop system with development tools pre-installed.",
        "packages": [
            "git", "base-devel", "cmake", "ninja", "meson",
            "python", "python-pip",
            "gdb", "valgrind", "strace",
            "docker",
            "bash-completion", "man-db", "man-pages",
            "usbutils", "pciutils", "lsof",
        ],
    },
}


# ── Common useful package groups for the package selector ──

PACKAGE_GROUPS = {
    "Web Browsers": {
        "firefox": "Firefox (open-source, recommended)",
        "chromium": "Chromium (open-source Chrome)",
    },
    "Multimedia": {
        "vlc": "VLC media player",
        "mpv": "mpv (lightweight video player)",
        "gimp": "GIMP (image editor)",
        "inkscape": "Inkscape (vector graphics)",
        "audacity": "Audacity (audio editor)",
        "obs-studio": "OBS Studio (screen recording/streaming)",
    },
    "Office": {
        "libreoffice-still": "LibreOffice (stable)",
        "libreoffice-fresh": "LibreOffice (latest)",
        "thunderbird": "Thunderbird (email client)",
        "evince": "Evince (PDF viewer)",
        "okular": "Okular (KDE document viewer)",
    },
    "Development": {
        "git": "Git (version control)",
        "base-devel": "base-devel (build tools)",
        "cmake": "CMake",
        "python": "Python 3",
        "nodejs": "Node.js",
        "rustup": "Rust (via rustup)",
        "go": "Go",
        "docker": "Docker",
    },
    "System Tools": {
        "htop": "htop (process viewer)",
        "btop": "btop (resource monitor)",
        "neofetch": "neofetch (system info)",
        "tmux": "tmux (terminal multiplexer)",
        "tree": "tree (directory listing)",
        "rsync": "rsync (file synchronization)",
        "curl": "curl",
        "wget": "wget",
        "unzip": "unzip",
        "zip": "zip",
        "p7zip": "7zip",
    },
    "Networking": {
        "openssh": "OpenSSH",
        "nmap": "nmap (network scanner)",
        "wireguard-tools": "WireGuard (VPN)",
        "openvpn": "OpenVPN",
    },
    "Fonts": {
        "ttf-liberation": "Liberation fonts",
        "ttf-dejavu": "DejaVu fonts",
        "noto-fonts": "Google Noto fonts",
        "noto-fonts-cjk": "Noto CJK fonts (Chinese/Japanese/Korean)",
        "noto-fonts-emoji": "Noto Emoji",
        "ttf-firacode-nerd": "FiraCode Nerd Font",
        "ttf-jetbrains-mono-nerd": "JetBrains Mono Nerd Font",
    },
    "Gaming": {
        "steam": "Steam",
        "lutris": "Lutris (game manager)",
        "wine": "Wine (Windows compatibility)",
        "gamemode": "GameMode (performance optimizer)",
        "mangohud": "MangoHUD (FPS overlay)",
        "lib32-mesa": "32-bit Mesa (needed for many games)",
    },
}

_LIVE_PACMAN_BACKUPS = {
    "/etc/pacman.conf": Path("/tmp/artixinstall-pacman.conf.bak"),
    "/etc/pacman.d/mirrorlist": Path("/tmp/artixinstall-mirrorlist.bak"),
}


def configure_kernel(screen: Screen) -> str | None:
    """
    Interactive kernel selection.

    Returns the kernel key (e.g. "linux", "linux-lts"), or None if cancelled.
    """
    options = [info["label"] for info in KERNELS.values()]
    keys = list(KERNELS.keys())

    selected = run_selection_menu(screen, "Select Linux kernel", options)
    if selected is None:
        return None

    idx = options.index(selected)
    return keys[idx]


def configure_audio(screen: Screen) -> str | None:
    """
    Interactive audio server selection.

    Returns the audio key (e.g. "pipewire"), or None if cancelled.
    """
    options = [info["label"] for info in AUDIO_SERVERS.values()]
    keys = list(AUDIO_SERVERS.keys())

    selected = run_selection_menu(screen, "Select audio server", options)
    if selected is None:
        return None

    idx = options.index(selected)
    return keys[idx]


def configure_profile(screen: Screen) -> str | None:
    """
    Interactive profile (preset) selection.

    Returns the profile key, or None if cancelled.
    """
    options = []
    keys = list(PROFILES.keys())

    for key, info in PROFILES.items():
        options.append(f"{info['label']}")

    selected = run_selection_menu(screen, "Select installation profile", options)
    if selected is None:
        return None

    idx = options.index(selected)
    return keys[idx]


def configure_additional_packages(screen: Screen,
                                   current: list[str]) -> list[str] | None:
    """
    Interactive package selector.

    Shows grouped package categories, lets user toggle packages, and
    supports free-text entry for custom packages.

    Returns the updated package list, or None if cancelled.
    """
    selected_packages = set(current)

    while True:
        # Build menu
        items = []

        # Show current count
        items.append(MenuItem(
            f"Selected packages: {len(selected_packages)}",
            key="__info__",
            is_separator=True,
        ))

        # Option to type custom packages
        items.append(MenuItem("Enter custom packages...", key="__custom__"))
        items.append(MenuItem("Clear all selections", key="__clear__"))
        items.append(MenuItem("Done", key="__done__"))

        items.append(MenuItem("", is_separator=True))

        # Package groups
        for group_name, packages in PACKAGE_GROUPS.items():
            # Count selected in this group
            count = sum(1 for p in packages if p in selected_packages)
            items.append(MenuItem(
                f"── {group_name} ({count}/{len(packages)}) ──",
                is_separator=True,
            ))

            for pkg_name, pkg_desc in packages.items():
                marker = "✓" if pkg_name in selected_packages else "○"
                items.append(MenuItem(
                    f"  {marker} {pkg_desc}",
                    key=pkg_name,
                    value=pkg_name,
                    is_set=(pkg_name in selected_packages),
                ))

        result = run_menu(screen, "Additional Packages", items,
                          footer="Enter Toggle  D Done  ESC Cancel")
        if result is None:
            return None

        if result.key == "__done__":
            return sorted(selected_packages)

        elif result.key == "__custom__":
            custom = text_input(
                screen,
                "Enter package names (space-separated):",
                default=" ".join(sorted(selected_packages)),
            )
            if custom is not None:
                # Parse and add
                for pkg in custom.split():
                    pkg = pkg.strip()
                    if pkg:
                        selected_packages.add(pkg)

        elif result.key == "__clear__":
            selected_packages.clear()

        elif result.key.startswith("__"):
            continue

        else:
            # Toggle package
            pkg = result.key
            if pkg in selected_packages:
                selected_packages.discard(pkg)
            else:
                selected_packages.add(pkg)


def configure_repositories(screen: Screen) -> dict | None:
    """
    Configure optional package repositories.

    Returns a dict of repository toggles, or None if cancelled.
    """
    repos = {
        "lib32": False,
        "universe": False,
    }

    result = yes_no(screen,
                    "Enable lib32 repository?\n"
                    "(Required for 32-bit applications, Steam, Wine, etc.)",
                    default=True)
    if result is None:
        return None
    repos["lib32"] = result

    result = yes_no(screen,
                    "Enable universe repository?\n"
                    "(Community-maintained Artix packages)",
                    default=False)
    if result is None:
        return None
    repos["universe"] = result

    return repos


def get_kernel_packages(kernel: str) -> list[str]:
    """Get the package list for a kernel choice."""
    info = KERNELS.get(kernel, KERNELS["linux"])
    return list(info.get("packages", []))


def get_kernel_name(kernel: str) -> str:
    """Get the base kernel package name (used for vmlinuz/initramfs paths)."""
    return kernel


def get_audio_packages(audio: str) -> list[str]:
    """Get the package list for an audio server choice."""
    info = AUDIO_SERVERS.get(audio, AUDIO_SERVERS["pipewire"])
    return list(info.get("packages", []))


def get_audio_label(audio: str) -> str:
    """Get the display label for an audio server."""
    info = AUDIO_SERVERS.get(audio, {})
    return info.get("label", audio)


def get_kernel_label(kernel: str) -> str:
    """Get the display label for a kernel."""
    info = KERNELS.get(kernel, {})
    return info.get("label", kernel)


def get_profile_packages(profile: str) -> list[str]:
    """Get the package list for a profile."""
    info = PROFILES.get(profile, {})
    return list(info.get("packages", []))


def get_profile_services(profile: str) -> list[str]:
    """Get services to enable for a profile."""
    info = PROFILES.get(profile, {})
    return list(info.get("services", []))


def get_profile_label(profile: str) -> str:
    """Get the display label for a profile."""
    info = PROFILES.get(profile, {})
    return info.get("label", profile)


def backup_live_package_config() -> tuple[bool, str]:
    """Save the original live pacman configuration for safe retries."""
    import shutil

    try:
        for src, backup in _LIVE_PACMAN_BACKUPS.items():
            src_path = Path(src)
            if src_path.is_file() and not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, backup)
        return True, ""
    except OSError as e:
        return False, f"Failed to back up live package configuration: {e}"


def restore_live_package_config() -> tuple[bool, str]:
    """Restore pacman.conf and mirrorlist to their original live-ISO state."""
    import shutil

    try:
        for dst, backup in _LIVE_PACMAN_BACKUPS.items():
            if backup.is_file():
                shutil.copy2(backup, dst)
        return True, ""
    except OSError as e:
        return False, f"Failed to restore live package configuration: {e}"


def _apply_repositories_to_path(pacman_conf: str, repos: dict) -> tuple[bool, str]:
    """Enable optional repositories in the given pacman.conf path."""
    import os
    import re

    if not os.path.isfile(pacman_conf):
        return True, ""

    try:
        with open(pacman_conf, "r") as f:
            content = f.read()

        if repos.get("lib32"):
            original = content
            lib32_block = re.compile(
                r"(?ms)^[ \t]*#?\s*\[lib32\][ \t]*\n(?:[ \t]*#.*\n)*[ \t]*#?\s*Include\s*=\s*/etc/pacman\.d/mirrorlist[ \t]*"
            )

            if lib32_block.search(content):
                content = lib32_block.sub(
                    "[lib32]\nInclude = /etc/pacman.d/mirrorlist",
                    content,
                    count=1,
                )
            else:
                content += "\n[lib32]\nInclude = /etc/pacman.d/mirrorlist\n"

            if content == original:
                log_info(f"lib32 repository already appeared enabled in {pacman_conf}")

        if repos.get("universe") and "[universe]" not in content:
            content += "\n[universe]\nServer = https://universe.artixlinux.org/$arch\n"

        with open(pacman_conf, "w") as f:
            f.write(content)

        log_info(f"Repositories configured in {pacman_conf}: {repos}")
        return True, ""

    except OSError as e:
        return False, f"Failed to configure repositories: {e}"


def configure_live_repositories(repos: dict) -> tuple[bool, str]:
    """Enable optional repositories in the live environment before basestrap."""
    success, message = _apply_repositories_to_path("/etc/pacman.conf", repos)
    if not success:
        return success, message

    rc, _, stderr = run(["pacman", "-Sy"], timeout=600)
    if rc != 0:
        return False, f"Failed to refresh package databases after enabling repositories: {stderr}"

    return True, ""


def apply_repositories(repos: dict) -> tuple[bool, str]:
    """
    Enable optional repositories in /mnt/etc/pacman.conf.
    """
    return _apply_repositories_to_path("/mnt/etc/pacman.conf", repos)
