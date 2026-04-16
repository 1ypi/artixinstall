"""
artixinstall.installer.hardware — Hardware detection and driver installation.

Detects GPUs (Intel/AMD/NVIDIA), WiFi/Bluetooth chipsets, CPU vendor
(for microcode), and laptop-specific hardware, then provides appropriate
package lists and configuration.
"""

import os

from artixinstall.utils.shell import run, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_menu, run_selection_menu, MenuItem
from artixinstall.tui.prompts import yes_no


# ── GPU driver options ──

GPU_DRIVERS = {
    "auto": {
        "label": "Auto-detect (recommended)",
        "packages": [],  # Filled dynamically
    },
    "nvidia-proprietary": {
        "label": "NVIDIA (proprietary)",
        "packages": [
            "nvidia", "nvidia-utils", "nvidia-settings",
            "lib32-nvidia-utils",
            "libva-nvidia-driver",
        ],
    },
    "nvidia-open": {
        "label": "NVIDIA (open kernel modules, Turing+)",
        "packages": [
            "nvidia-open", "nvidia-utils", "nvidia-settings",
            "lib32-nvidia-utils",
        ],
    },
    "nvidia-nouveau": {
        "label": "NVIDIA (nouveau, open-source)",
        "packages": [
            "xf86-video-nouveau", "mesa", "lib32-mesa",
        ],
    },
    "amd": {
        "label": "AMD (AMDGPU, open-source)",
        "packages": [
            "xf86-video-amdgpu", "mesa", "lib32-mesa",
            "vulkan-radeon", "lib32-vulkan-radeon",
        ],
    },
    "intel": {
        "label": "Intel (integrated)",
        "packages": [
            "mesa", "lib32-mesa",
            "vulkan-intel", "lib32-vulkan-intel",
            "intel-media-driver", "libva-intel-driver",
        ],
    },
    "vmware": {
        "label": "VMware / VirtualBox (virtual machine)",
        "packages": [
            "mesa",
            "virtualbox-guest-utils",
        ],
    },
    "none": {
        "label": "None (skip GPU drivers)",
        "packages": [],
    },
}


def detect_gpu() -> list[str]:
    """
    Detect GPU vendor(s) by checking lspci output.

    Returns a list of detected vendor keys: "nvidia", "amd", "intel", "vmware".
    """
    rc, stdout, _ = run("lspci -nn 2>/dev/null")
    if rc != 0:
        return []

    output = stdout.lower()
    detected = []

    if "nvidia" in output:
        detected.append("nvidia")
    if "amd" in output or "radeon" in output or "advanced micro devices" in output:
        detected.append("amd")
    if "intel" in output and ("vga" in output or "display" in output or "graphics" in output):
        detected.append("intel")
    if "vmware" in output or "virtualbox" in output or "qemu" in output:
        detected.append("vmware")

    return detected


def detect_cpu_vendor() -> str:
    """Detect CPU vendor for microcode selection. Returns 'intel', 'amd', or 'unknown'."""
    rc, stdout, _ = run("grep -m1 'vendor_id' /proc/cpuinfo 2>/dev/null")
    if rc != 0:
        return "unknown"

    if "GenuineIntel" in stdout:
        return "intel"
    elif "AuthenticAMD" in stdout:
        return "amd"
    return "unknown"


def get_microcode_package() -> str | None:
    """Return the correct microcode package for the detected CPU, or None."""
    vendor = detect_cpu_vendor()
    if vendor == "intel":
        return "intel-ucode"
    elif vendor == "amd":
        return "amd-ucode"
    return None


def _first_available_package(candidates: list[str]) -> str | None:
    """Return the first package available in the currently configured repos."""
    for pkg in candidates:
        rc, _, _ = run(["pacman", "-Si", pkg])
        if rc == 0:
            return pkg
    return None


def detect_wifi() -> bool:
    """Check if any WiFi adapters are present."""
    rc, stdout, _ = run("ip link show 2>/dev/null")
    if rc == 0:
        # Check for wlan/wlp interfaces
        for line in stdout.splitlines():
            if "wlan" in line or "wlp" in line:
                return True

    # Also check rfkill
    rc, stdout, _ = run("rfkill list wifi 2>/dev/null")
    if rc == 0 and stdout.strip():
        return True

    # Check lspci for wireless
    rc, stdout, _ = run("lspci 2>/dev/null | grep -i 'wireless\\|wi-fi\\|wlan\\|wifi'")
    if rc == 0 and stdout.strip():
        return True

    return False


def detect_bluetooth() -> bool:
    """Check if any Bluetooth adapters are present."""
    rc, stdout, _ = run("rfkill list bluetooth 2>/dev/null")
    if rc == 0 and stdout.strip():
        return True

    rc, stdout, _ = run("lspci 2>/dev/null | grep -i bluetooth")
    if rc == 0 and stdout.strip():
        return True

    rc, stdout, _ = run("lsusb 2>/dev/null | grep -i bluetooth")
    if rc == 0 and stdout.strip():
        return True

    return False


def detect_touchpad() -> bool:
    """Check if a touchpad is present (laptop detection)."""
    rc, stdout, _ = run("grep -ril 'touchpad\\|synaptics\\|trackpad' /sys/class/input/*/name 2>/dev/null")
    if rc == 0 and stdout.strip():
        return True

    # Check libinput devices
    rc, stdout, _ = run("find /sys/class/input -name 'name' -exec grep -li 'touchpad' {} \\; 2>/dev/null")
    if rc == 0 and stdout.strip():
        return True

    return False


def is_laptop() -> bool:
    """Heuristic to detect if the system is a laptop."""
    # Check for battery
    if os.path.isdir("/sys/class/power_supply"):
        rc, stdout, _ = run("ls /sys/class/power_supply/ 2>/dev/null")
        if rc == 0:
            for line in stdout.splitlines():
                if line.startswith("BAT"):
                    return True

    # Check chassis type
    chassis_path = "/sys/class/dmi/id/chassis_type"
    if os.path.isfile(chassis_path):
        try:
            with open(chassis_path) as f:
                chassis = f.read().strip()
            # Chassis types: 9=Laptop, 10=Notebook, 14=Sub-Notebook, 31=Convertible, 32=Detachable
            if chassis in ("9", "10", "14", "31", "32"):
                return True
        except OSError:
            pass

    # Fallback: touchpad presence
    return detect_touchpad()


class HardwareConfig:
    """Stores all hardware-related configuration choices."""

    def __init__(self) -> None:
        self.gpu_driver: str = "auto"
        self.install_wifi: bool = False
        self.install_bluetooth: bool = False
        self.install_laptop_power: bool = False
        self.install_printing: bool = False
        self.install_microcode: bool = True

    def get_summary(self) -> str:
        """Return a human-readable summary of hardware config."""
        parts = []
        gpu_info = GPU_DRIVERS.get(self.gpu_driver, {}).get("label", self.gpu_driver)
        parts.append(f"GPU: {gpu_info}")
        if self.install_wifi:
            parts.append("WiFi")
        if self.install_bluetooth:
            parts.append("Bluetooth")
        if self.install_laptop_power:
            parts.append("Laptop power")
        if self.install_printing:
            parts.append("Printing")
        return ", ".join(parts) if parts else "not configured"

    def get_all_packages(self) -> list[str]:
        """Collect all hardware-related packages."""
        packages = []

        # GPU
        if self.gpu_driver == "auto":
            packages.extend(_auto_gpu_packages())
        elif self.gpu_driver == "vmware":
            packages.extend(GPU_DRIVERS["vmware"]["packages"])
            vmware_driver = _first_available_package([
                "xf86-video-vmware",
                "xlibre-xf86-video-vmware",
            ])
            if vmware_driver:
                packages.append(vmware_driver)
        else:
            info = GPU_DRIVERS.get(self.gpu_driver, {})
            packages.extend(info.get("packages", []))

        # CPU microcode
        if self.install_microcode:
            ucode = get_microcode_package()
            if ucode:
                packages.append(ucode)

        # WiFi
        if self.install_wifi:
            packages.extend([
                "iw", "wireless-regdb",
                "linux-firmware",
            ])

        # Bluetooth
        if self.install_bluetooth:
            packages.extend([
                "bluez", "bluez-utils",
            ])

        # Laptop power management
        if self.install_laptop_power:
            packages.extend([
                "acpi", "acpid", "tlp",
                "brightnessctl",
                "xf86-input-libinput",
            ])

        # Printing
        if self.install_printing:
            packages.extend([
                "cups", "cups-pdf",
                "ghostscript", "gsfonts",
                "gutenprint", "foomatic-db", "foomatic-db-gutenprint-ppds",
                "system-config-printer",
            ])

        return packages

    def get_services(self) -> list[str]:
        """Get services to enable for hardware."""
        services = []

        if self.install_bluetooth:
            services.append("bluetoothd")

        if self.install_printing:
            services.append("cups")

        return services


def _auto_gpu_packages() -> list[str]:
    """Detect GPU and return appropriate driver packages."""
    detected = detect_gpu()
    packages = []

    if "vmware" in detected:
        packages.extend(GPU_DRIVERS["vmware"]["packages"])
        vmware_driver = _first_available_package([
            "xf86-video-vmware",
            "xlibre-xf86-video-vmware",
        ])
        if vmware_driver:
            packages.append(vmware_driver)
    else:
        if "nvidia" in detected:
            # Default to proprietary for auto
            packages.extend(GPU_DRIVERS["nvidia-proprietary"]["packages"])
        if "amd" in detected:
            packages.extend(GPU_DRIVERS["amd"]["packages"])
        if "intel" in detected:
            packages.extend(GPU_DRIVERS["intel"]["packages"])

    if not packages:
        # Fallback: just mesa
        packages.extend(["mesa", "lib32-mesa"])

    return packages


def configure_hardware(screen: Screen) -> HardwareConfig | None:
    """
    Interactive hardware configuration.

    Auto-detects hardware and lets the user confirm/modify choices.
    Returns a HardwareConfig, or None if cancelled.
    """
    config = HardwareConfig()

    # ── GPU driver selection ──
    detected_gpus = detect_gpu()
    gpu_hint = ", ".join(detected_gpus) if detected_gpus else "none detected"

    options = [f"{info['label']}" for info in GPU_DRIVERS.values()]
    keys = list(GPU_DRIVERS.keys())

    # Pre-select based on detection
    gpu_choice = run_selection_menu(
        screen,
        f"Select graphics driver (detected: {gpu_hint})",
        options,
    )
    if gpu_choice is None:
        return None

    idx = options.index(gpu_choice)
    config.gpu_driver = keys[idx]

    # ── WiFi ──
    has_wifi = detect_wifi()
    wifi_q = "WiFi hardware detected. Install WiFi support?" if has_wifi else "Install WiFi support? (no WiFi detected)"
    result = yes_no(screen, wifi_q, default=has_wifi)
    if result is None:
        return None
    config.install_wifi = result

    # ── Bluetooth ──
    has_bt = detect_bluetooth()
    bt_q = "Bluetooth hardware detected. Install Bluetooth support?" if has_bt else "Install Bluetooth support? (no Bluetooth detected)"
    result = yes_no(screen, bt_q, default=has_bt)
    if result is None:
        return None
    config.install_bluetooth = result

    # ── Laptop power management ──
    laptop = is_laptop()
    laptop_q = "Laptop detected. Install power management (TLP, ACPI)?" if laptop else "Install laptop power management? (desktop detected)"
    result = yes_no(screen, laptop_q, default=laptop)
    if result is None:
        return None
    config.install_laptop_power = result

    # ── Printing ──
    result = yes_no(screen, "Install printing support (CUPS)?", default=False)
    if result is None:
        return None
    config.install_printing = result

    # ── Microcode ──
    cpu_vendor = detect_cpu_vendor()
    if cpu_vendor in ("intel", "amd"):
        result = yes_no(screen, f"Install {cpu_vendor.upper()} CPU microcode updates? (recommended)", default=True)
        if result is None:
            return None
        config.install_microcode = result
    else:
        config.install_microcode = False

    return config




def apply_laptop_power(init_system: str) -> tuple[bool, str]:
    """Enable laptop power management services inside the chroot."""
    service_packages = {
        "openrc": ["tlp-openrc", "acpid-openrc"],
        "runit": ["tlp-runit", "acpid-runit"],
        "s6": ["tlp-s6", "acpid-s6"],
        "dinit": ["tlp-dinit", "acpid-dinit"],
    }
    enable_cmds = {
        "openrc": [
            ("tlp", "rc-update add tlp default"),
            ("acpid", "rc-update add acpid default"),
        ],
        "runit": [
            ("tlp", "ln -s /etc/runit/sv/tlp /etc/runit/runsvdir/default/"),
            ("acpid", "ln -s /etc/runit/sv/acpid /etc/runit/runsvdir/default/"),
        ],
        "s6": [
            ("tlp", "s6-rc-bundle-update add default tlp"),
            ("acpid", "s6-rc-bundle-update add default acpid"),
        ],
        "dinit": [
            ("tlp", "dinitctl enable tlp"),
            ("acpid", "dinitctl enable acpid"),
        ],
    }

    pkgs = service_packages.get(init_system, [])
    if pkgs:
        rc, _, stderr = run(
            ["pacman", "-S", "--noconfirm", "--needed", *pkgs],
            chroot=True,
            timeout=1800,
        )
        if rc != 0:
            log_error(f"Failed to install laptop power service packages: {stderr}")

    for service_name, cmd in enable_cmds.get(init_system, []):
        rc, _, stderr = run(cmd, chroot=True)
        if rc != 0:
            log_error(f"Failed to enable {service_name}: {stderr}")

    log_info(f"Laptop power management configured ({init_system})")
    return True, ""
