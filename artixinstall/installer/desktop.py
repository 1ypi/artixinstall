"""
artixinstall.installer.desktop — Desktop environment and window manager installation.

Comprehensive selection covering full DEs (GNOME, KDE, XFCE, etc.) and
tiling/stacking WMs (Hyprland, Sway, i3, bspwm, etc.) — matching and
exceeding archinstall's desktop offering.
"""

from artixinstall.utils.log import log_info
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_selection_menu

# ── Shared package groups ──

# NOTE: Audio packages are NOT included in desktop definitions.
# They are managed centrally by packages.py's get_audio_packages()
# so the user's audio choice (pipewire / pulseaudio / none) is respected.

_XORG = ["xorg-server", "xorg-xinit", "xorg-xrandr", "xorg-xsetroot"]

_WAYLAND_BASE = ["xorg-xwayland", "xdg-desktop-portal"]

_COMMON_UTILS = [
    "xdg-utils", "xdg-user-dirs",
]

DISPLAY_MANAGERS = {
    "none": {
        "label": "TTY only (no greeter)",
        "packages": [],
        "services": [],
    },
    "gdm": {
        "label": "GDM",
        "packages": ["gdm"],
        "services": ["gdm"],
    },
    "sddm": {
        "label": "SDDM",
        "packages": ["sddm", "sddm-theme-artix"],
        "services": ["sddm"],
    },
    "lightdm-gtk": {
        "label": "LightDM + GTK Greeter",
        "packages": ["lightdm", "lightdm-gtk-greeter", "lightdm-gtk-greeter-settings"],
        "services": ["lightdm"],
    },
    "lightdm-slick": {
        "label": "LightDM + Slick Greeter",
        "packages": ["lightdm", "lightdm-slick-greeter"],
        "services": ["lightdm"],
    },
    "ly": {
        "label": "Ly",
        "packages": ["ly"],
        "services": ["ly"],
    },
}

DISPLAY_MANAGER_RECOMMENDATIONS = {
    "gnome": {
        "recommended": "gdm",
        "warnings": {
            "ly": "GNOME works best with GDM. Ly is not recommended for GNOME and may fail with Xorg sessions unless extra X11 pieces are present.",
            "lightdm-gtk": "GNOME works best with GDM. LightDM is a less-tested GNOME combination and may miss session integration.",
            "lightdm-slick": "GNOME works best with GDM. LightDM is a less-tested GNOME combination and may miss session integration.",
            "sddm": "GNOME works best with GDM. SDDM can work, but it is not the ideal GNOME greeter.",
        },
    },
    "kde": {
        "recommended": "sddm",
        "warnings": {
            "gdm": "KDE Plasma works best with SDDM. GDM is not the usual Plasma greeter and may feel less integrated.",
            "ly": "KDE Plasma works best with SDDM. Ly is a lightweight TUI greeter and is not an ideal Plasma match.",
            "lightdm-gtk": "KDE Plasma works best with SDDM. LightDM is usable, but not the recommended Plasma greeter.",
            "lightdm-slick": "KDE Plasma works best with SDDM. LightDM is usable, but not the recommended Plasma greeter.",
        },
    },
    "lxqt": {
        "recommended": "sddm",
        "warnings": {
            "gdm": "LXQt works best with SDDM. GDM is a less natural match for LXQt.",
            "ly": "LXQt works best with SDDM. Ly can work, but it is a less-tested LXQt combination.",
        },
    },
    "xfce": {
        "recommended": "lightdm-gtk",
        "warnings": {
            "gdm": "XFCE is usually paired with LightDM. GDM is a heavier and less typical choice for XFCE.",
            "sddm": "XFCE is usually paired with LightDM. SDDM can work, but it is not the usual XFCE greeter.",
        },
    },
    "cinnamon": {
        "recommended": "lightdm-gtk",
        "warnings": {
            "gdm": "Cinnamon is usually paired with LightDM. GDM is a less typical choice here.",
            "sddm": "Cinnamon is usually paired with LightDM. SDDM can work, but it is not the common Cinnamon greeter.",
        },
    },
    "mate": {
        "recommended": "lightdm-gtk",
        "warnings": {
            "gdm": "MATE is usually paired with LightDM. GDM is a less typical choice here.",
            "sddm": "MATE is usually paired with LightDM. SDDM can work, but it is not the common MATE greeter.",
        },
    },
    "budgie": {
        "recommended": "lightdm-gtk",
        "warnings": {
            "gdm": "Budgie is usually paired with LightDM. GDM is a less typical choice here.",
            "sddm": "Budgie is usually paired with LightDM. SDDM can work, but it is not the common Budgie greeter.",
        },
    },
    "deepin": {
        "recommended": "lightdm-gtk",
        "warnings": {
            "gdm": "Deepin is usually paired with LightDM. GDM is a less typical choice here.",
            "sddm": "Deepin is usually paired with LightDM. SDDM can work, but it is not the common Deepin greeter.",
        },
    },
    "enlightenment": {
        "recommended": "lightdm-gtk",
        "warnings": {
            "gdm": "Enlightenment is usually paired with LightDM or started manually. GDM is a less typical choice.",
            "sddm": "Enlightenment is usually paired with LightDM or started manually. SDDM is a less typical choice.",
        },
    },
    "hyprland": {
        "recommended": "ly",
        "warnings": {
            "gdm": "Hyprland is usually started from Ly, SDDM, or directly from TTY. GDM is not the safest default for Hyprland.",
            "lightdm-gtk": "Hyprland can work with LightDM, but Ly/SDDM/TTY are usually safer choices.",
            "lightdm-slick": "Hyprland can work with LightDM, but Ly/SDDM/TTY are usually safer choices.",
        },
    },
    "sway": {
        "recommended": "ly",
        "warnings": {
            "gdm": "Sway is usually started from Ly or directly from TTY. GDM is not the safest default for Sway.",
            "lightdm-gtk": "Sway can work with LightDM, but Ly/TTY are usually safer choices.",
            "lightdm-slick": "Sway can work with LightDM, but Ly/TTY are usually safer choices.",
        },
    },
    "mangowm": {
        "recommended": "ly",
        "warnings": {
            "gdm": "MangoWM is usually started from Ly or directly from TTY. GDM is not the safest default.",
            "lightdm-gtk": "MangoWM can work with LightDM, but Ly/TTY are usually safer choices.",
            "lightdm-slick": "MangoWM can work with LightDM, but Ly/TTY are usually safer choices.",
        },
    },
    "niri": {
        "recommended": "ly",
        "warnings": {
            "gdm": "Niri is usually started from Ly or directly from TTY. GDM is not the safest default.",
            "lightdm-gtk": "Niri can work with LightDM, but Ly/TTY are usually safer choices.",
            "lightdm-slick": "Niri can work with LightDM, but Ly/TTY are usually safer choices.",
        },
    },
}

# ── Desktop environment definitions ──
# Each entry includes:
#   label:            display name in the menu
#   category:         "de" (desktop environment) or "wm" (window manager) or "none"
#   packages:         list of packages to install
#   display_manager:  DM to use (or None for TTY-launched WMs)
#   services:         services to enable (looked up in services.json)
#   extra_services:   additional services that don't need init-specific mapping (just names)

DESKTOP_ENVIRONMENTS = {
    # ── No desktop ──
    "none": {
        "label": "None (command-line only)",
        "category": "none",
        "packages": [],
        "display_manager": None,
        "services": [],
    },

    # ══════════════════════════════════════
    # ── Full Desktop Environments ──
    # ══════════════════════════════════════

    "gnome": {
        "label": "GNOME",
        "category": "de",
        "packages": [
            "gnome", "gnome-extra",
            "xdg-desktop-portal-gnome",
            *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": "gdm",
        "services": [],
    },

    "kde": {
        "label": "KDE Plasma",
        "category": "de",
        "packages": [
            "plasma-meta", "kde-applications-meta",
            "xdg-desktop-portal-kde",
            "phonon-qt6-vlc",
            *_XORG, *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": "sddm",
        "services": [],
    },

    "xfce": {
        "label": "XFCE",
        "category": "de",
        "packages": [
            "xfce4", "xfce4-goodies",
            "gvfs", "thunar-archive-plugin", "file-roller",
            "pavucontrol", "network-manager-applet",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "lightdm-gtk",
        "services": [],
    },

    "cinnamon": {
        "label": "Cinnamon",
        "category": "de",
        "packages": [
            "cinnamon", "nemo-fileroller", "gnome-terminal",
            "gnome-keyring",
            "blueberry",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "lightdm-gtk",
        "services": [],
    },

    "mate": {
        "label": "MATE",
        "category": "de",
        "packages": [
            "mate", "mate-extra",
            "network-manager-applet",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "lightdm-gtk",
        "services": [],
    },

    "budgie": {
        "label": "Budgie",
        "category": "de",
        "packages": [
            "budgie-desktop", "budgie-extras",
            "gnome-terminal", "nemo",
            "gnome-keyring",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "lightdm-gtk",
        "services": [],
    },

    "lxqt": {
        "label": "LXQt",
        "category": "de",
        "packages": [
            "lxqt", "breeze-icons", "oxygen-icons",
            "xscreensaver",
            "network-manager-applet",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "sddm",
        "services": [],
    },

    "deepin": {
        "label": "Deepin",
        "category": "de",
        "packages": [
            "deepin", "deepin-extra", "deepin-kwin",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "lightdm-gtk",
        "services": [],
    },

    "enlightenment": {
        "label": "Enlightenment",
        "category": "de",
        "packages": [
            "enlightenment", "terminology",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": "lightdm-gtk",
        "services": [],
    },

    # ══════════════════════════════════════
    # ── Tiling / Stacking Window Managers ──
    # ══════════════════════════════════════

    "hyprland": {
        "label": "Hyprland (Wayland compositor)",
        "category": "wm",
        "packages": [
            "hyprland", "hyprpaper", "hypridle", "hyprlock",
            "waybar", "wofi", "dunst",
            "foot", "thunar", "grim", "slurp", "wl-clipboard",
            "polkit-gnome", "xdg-desktop-portal-hyprland",
            "qt5-wayland", "qt6-wayland", "brightnessctl",
            *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": None,  # Started from TTY
        "services": [],
    },

    "sway": {
        "label": "Sway (Wayland tiling – i3 compatible)",
        "category": "wm",
        "packages": [
            "sway", "swayidle", "swaylock", "swaybg",
            "waybar", "wofi", "dunst",
            "foot", "thunar", "grim", "slurp", "wl-clipboard",
            "polkit-gnome", "xdg-desktop-portal-wlr",
            "brightnessctl",
            *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "i3": {
        "label": "i3-wm (X11 tiling)",
        "category": "wm",
        "packages": [
            "i3-wm", "i3status", "i3lock", "i3blocks",
            "dmenu", "rofi", "dunst",
            "alacritty", "thunar", "feh", "picom",
            "lxappearance", "arandr",
            "network-manager-applet", "pavucontrol",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "bspwm": {
        "label": "bspwm (X11 tiling)",
        "category": "wm",
        "packages": [
            "bspwm", "sxhkd",
            "polybar", "rofi", "dunst",
            "alacritty", "thunar", "feh", "picom",
            "lxappearance",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "dwm": {
        "label": "dwm (X11 dynamic – suckless)",
        "category": "wm",
        "packages": [
            "dwm", "dmenu", "st",
            "dunst", "feh", "picom",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "qtile": {
        "label": "Qtile (X11/Wayland tiling – Python)",
        "category": "wm",
        "packages": [
            "qtile", "python-psutil", "python-iwlib",
            "rofi", "dunst",
            "alacritty", "thunar", "feh", "picom",
            *_XORG, *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "openbox": {
        "label": "Openbox (X11 stacking)",
        "category": "wm",
        "packages": [
            "openbox", "obconf",
            "tint2", "rofi", "dunst",
            "alacritty", "thunar", "feh", "picom",
            "lxappearance",
            "network-manager-applet", "volumeicon",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "awesome": {
        "label": "awesome (X11 dynamic tiling)",
        "category": "wm",
        "packages": [
            "awesome", "vicious",
            "rofi", "dunst",
            "alacritty", "thunar", "feh", "picom",
            "lxappearance", "network-manager-applet",
            *_XORG, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "river": {
        "label": "River (Wayland dynamic tiling)",
        "category": "wm",
        "packages": [
            "river",
            "waybar", "wofi", "dunst",
            "foot", "thunar", "grim", "slurp", "wl-clipboard",
            "polkit-gnome", "xdg-desktop-portal-wlr",
            *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "mangowm": {
        "label": "MangoWM (Wayland compositor – dwl-based)",
        "category": "wm",
        "packages": [
            # MangoWM is AUR-only (mangowm-git). The installer will
            # note this and skip validation if the package is missing.
            "waybar", "wofi", "dunst",
            "foot", "thunar", "grim", "slurp", "wl-clipboard",
            "polkit-gnome", "xdg-desktop-portal-wlr",
            *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },

    "niri": {
        "label": "Niri (Wayland scrollable tiling)",
        "category": "wm",
        "packages": [
            "niri",
            "waybar", "fuzzel", "dunst",
            "foot", "thunar", "grim", "slurp", "wl-clipboard",
            "polkit-gnome", "xdg-desktop-portal-gnome",
            *_WAYLAND_BASE, *_COMMON_UTILS,
        ],
        "display_manager": None,
        "services": [],
    },
}


def configure_desktop(screen: Screen) -> str | None:
    """
    Interactive desktop environment selection.

    Groups DEs and WMs separately for clarity.
    Returns the DE key (e.g. "hyprland"), or None if cancelled.
    """
    # Build categorized display
    de_options = []
    wm_options = []
    none_options = []

    for key, info in DESKTOP_ENVIRONMENTS.items():
        entry = (key, info["label"])
        if info["category"] == "none":
            none_options.append(entry)
        elif info["category"] == "de":
            de_options.append(entry)
        elif info["category"] == "wm":
            wm_options.append(entry)

    # Build flat display list with section headers
    display_labels = []
    key_map = []

    for key, label in none_options:
        display_labels.append(label)
        key_map.append(key)

    display_labels.append("── Desktop Environments ──")
    key_map.append(None)

    for key, label in de_options:
        display_labels.append(f"  {label}")
        key_map.append(key)

    display_labels.append("── Window Managers ──")
    key_map.append(None)

    for key, label in wm_options:
        display_labels.append(f"  {label}")
        key_map.append(key)

    from artixinstall.tui.menu import run_menu, MenuItem
    items = []
    for i, label in enumerate(display_labels):
        k = key_map[i]
        if k is None:
            items.append(MenuItem(label, is_separator=True))
        else:
            items.append(MenuItem(label, key=k))

    result = run_menu(screen, "Select desktop environment / window manager", items,
                      footer="↑↓ Navigate  Enter Select  ESC Back")
    if result is None:
        return None
    return result.key


def configure_display_manager(screen: Screen, desktop: str) -> str | None:
    """Choose a display manager / greeter for any graphical environment."""
    info = DESKTOP_ENVIRONMENTS.get(desktop, {})
    if info.get("category") == "none":
        return "none"

    desktop_rules = DISPLAY_MANAGER_RECOMMENDATIONS.get(desktop, {})
    default_dm = desktop_rules.get("recommended", info.get("display_manager"))
    recommended = {
        "gdm": ["gdm", "sddm", "ly", "lightdm-gtk", "lightdm-slick", "none"],
        "sddm": ["sddm", "ly", "lightdm-gtk", "lightdm-slick", "gdm", "none"],
        "lightdm": ["lightdm-gtk", "lightdm-slick", "ly", "sddm", "gdm", "none"],
        "ly": ["ly", "sddm", "lightdm-gtk", "lightdm-slick", "gdm", "none"],
    }.get(default_dm, ["lightdm-gtk", "ly", "sddm", "gdm", "lightdm-slick", "none"])

    options = [
        (
            f"{DISPLAY_MANAGERS[key]['label']} (recommended)"
            if key == default_dm else DISPLAY_MANAGERS[key]["label"]
        )
        for key in recommended
        if key in DISPLAY_MANAGERS
    ]

    choice = run_selection_menu(
        screen,
        f"Select greeter / login manager for {info.get('label', desktop)}",
        options,
    )
    if choice is None:
        return None

    for key in recommended:
        display_label = DISPLAY_MANAGERS.get(key, {}).get("label")
        if choice in {display_label, f"{display_label} (recommended)"}:
            return key
    return "none"


def get_desktop_packages(desktop: str, display_manager: str = "none") -> list[str]:
    """Get the package list for a desktop environment."""
    info = DESKTOP_ENVIRONMENTS.get(desktop, {})
    packages = list(info.get("packages", []))
    dm_packages = DISPLAY_MANAGERS.get(display_manager, {}).get("packages", [])
    packages.extend(dm_packages)
    return packages


def get_desktop_services(desktop: str, display_manager: str = "none") -> list[str]:
    """Get the services that need to be enabled for the desktop install."""
    info = DESKTOP_ENVIRONMENTS.get(desktop, {})
    services = list(info.get("services", []))
    dm_services = DISPLAY_MANAGERS.get(display_manager, {}).get("services", [])
    services.extend(dm_services)
    return services


def get_desktop_label(desktop: str, display_manager: str = "none") -> str:
    """Get the display label for a desktop environment."""
    info = DESKTOP_ENVIRONMENTS.get(desktop, {})
    label = info.get("label", desktop)
    dm_label = DISPLAY_MANAGERS.get(display_manager, {}).get("label")
    if info.get("category") != "none" and display_manager != "none" and dm_label:
        return f"{label} + {dm_label}"
    return label


def get_display_manager_label(display_manager: str) -> str:
    """Get the display label for a configured greeter / login manager."""
    info = DISPLAY_MANAGERS.get(display_manager, {})
    return info.get("label", display_manager)


def get_desktop_category(desktop: str) -> str:
    """Get the category (de/wm/none) for a desktop."""
    info = DESKTOP_ENVIRONMENTS.get(desktop, {})
    return info.get("category", "none")


def get_display_manager_warning(desktop: str, display_manager: str) -> str:
    """Return a warning string for non-ideal desktop/greeter combinations."""
    rules = DISPLAY_MANAGER_RECOMMENDATIONS.get(desktop, {})
    warnings = rules.get("warnings", {})
    return warnings.get(display_manager, "")
