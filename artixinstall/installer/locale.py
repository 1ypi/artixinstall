"""
artixinstall.installer.locale — Locale, timezone, and keyboard layout configuration.

Handles setting the system locale, timezone, keyboard layout, and hardware
clock inside the chroot.
"""

import os
from pathlib import Path

from artixinstall.utils.shell import run, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_selection_menu, run_menu, MenuItem
from artixinstall.tui.prompts import text_input
from artixinstall.utils.validate import is_valid_locale


def _get_data_dir() -> Path:
    """Get the path to the data directory."""
    return Path(__file__).parent.parent / "data"


def load_locale_list() -> list[str]:
    """Load the curated list of common locales from data/locales.txt."""
    locale_file = _get_data_dir() / "locales.txt"
    try:
        with open(locale_file, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        try:
            with open("/usr/share/i18n/SUPPORTED", "r") as f:
                log_error("locales.txt not found, extracting from supported locales file")
                lines = f.read().splitlines()
                content = []
                for line in lines:
                    content.append(line.split(" ")[0])
                return content
        except FileNotFoundError:
            log_error("locales.txt and supported locales file not found, using defaults")
            return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "es_ES.UTF-8"]


def configure_locale(screen: Screen) -> str | None:
    """
    Interactive locale selection.

    Returns the selected locale string (e.g. "en_US.UTF-8"), or None if cancelled.
    """
    locales = load_locale_list()
    locales.append("Custom (enter manually)")

    selected = run_selection_menu(screen, "Select locale", locales)
    if selected is None:
        return None

    if selected.startswith("Custom"):
        return text_input(screen, "Enter locale (e.g. en_US.UTF-8):",
                          default="en_US.UTF-8",
                          validator=is_valid_locale)
    return selected


def configure_timezone(screen: Screen) -> str | None:
    """
    Interactive timezone selection (two-level: continent → city).

    Returns a timezone string (e.g. "Europe/Berlin"), or None if cancelled.
    """
    zoneinfo = "/usr/share/zoneinfo"

    if not os.path.isdir(zoneinfo):
        # Fallback: ask for manual input
        return text_input(screen, "Enter timezone (e.g. Europe/Berlin):",
                          default="UTC")

    # List continents/regions (directories in zoneinfo, excluding special dirs)
    excluded = {"posix", "right", "Etc", "SystemV", "US", "Brazil",
                "Canada", "Chile", "Mexico", "Cuba", "Egypt",
                "Eire", "GMT", "Greenwich", "Hongkong", "Iceland",
                "Iran", "Israel", "Jamaica", "Japan", "Kwajalein",
                "Libya", "Navajo", "Poland", "Portugal", "Singapore",
                "Turkey", "Zulu", "leap-seconds.list", "leapseconds",
                "posixrules", "tzdata.zi", "zone.tab", "zone1970.tab",
                "iso3166.tab"}

    continents = sorted([
        d for d in os.listdir(zoneinfo)
        if os.path.isdir(os.path.join(zoneinfo, d))
        and d not in excluded
        and not d.startswith(".")
        and not d.startswith("+")
    ])

    if not continents:
        return text_input(screen, "Enter timezone (e.g. Europe/Berlin):",
                          default="UTC")

    # Add UTC as a direct option
    continents.insert(0, "UTC")

    selected_continent = run_selection_menu(screen, "Select region", continents)
    if selected_continent is None:
        return None

    if selected_continent == "UTC":
        return "UTC"

    # List cities in the selected region
    region_path = os.path.join(zoneinfo, selected_continent)
    cities = sorted([
        f for f in os.listdir(region_path)
        if os.path.isfile(os.path.join(region_path, f))
        or os.path.isdir(os.path.join(region_path, f))
    ])

    # Handle sub-regions (e.g. America/Indiana/Indianapolis)
    all_entries = []
    for city in cities:
        city_path = os.path.join(region_path, city)
        if os.path.isdir(city_path):
            sub_cities = sorted([
                f"{city}/{sub}" for sub in os.listdir(city_path)
                if os.path.isfile(os.path.join(city_path, sub))
            ])
            all_entries.extend(sub_cities)
        else:
            all_entries.append(city)

    if not all_entries:
        return f"{selected_continent}"

    selected_city = run_selection_menu(screen, f"Select city ({selected_continent})",
                                       all_entries)
    if selected_city is None:
        return None

    return f"{selected_continent}/{selected_city}"


def configure_keymap(screen: Screen) -> str | None:
    """
    Interactive keyboard layout selection.

    Returns the keymap name (e.g. "us"), or None if cancelled.
    """
    # Try to get keymaps from localectl
    rc, stdout, _ = run("localectl list-keymaps")
    if rc == 0 and stdout.strip():
        keymaps = stdout.strip().splitlines()
    else:
        # Fallback: try to list from /usr/share/kbd/keymaps
        rc2, stdout2, _ = run("find /usr/share/kbd/keymaps -name '*.map.gz' -printf '%f\\n' 2>/dev/null | sed 's/.map.gz//' | sort")
        if rc2 == 0 and stdout2.strip():
            keymaps = stdout2.strip().splitlines()
        else:
            # Hardcoded fallback of common keymaps
            keymaps = [
                "us", "uk", "de", "fr", "es", "it", "pt-latin1",
                "br-abnt2", "ru", "jp106", "kr", "dvorak", "colemak",
            ]

    selected = run_selection_menu(screen, "Select keyboard layout", keymaps)
    return selected


# ── Application functions (called during installation) ──


def apply_locale(locale: str) -> tuple[bool, str]:
    """
    Apply locale settings inside the chroot.

    Steps:
    1. Write /etc/locale.gen with the selected locale uncommented
    2. Run locale-gen
    3. Write /etc/locale.conf
    """
    locale_gen_path = os.path.join(MOUNT_POINT, "etc", "locale.gen")

    # Write locale.gen
    try:
        with open(locale_gen_path, "w") as f:
            f.write(f"# Generated by artixinstall\n")
            f.write(f"{locale} UTF-8\n")
            # Always include en_US as a fallback
            if locale != "en_US.UTF-8":
                f.write(f"en_US.UTF-8 UTF-8\n")
    except OSError as e:
        return False, f"Failed to write locale.gen: {e}"

    # Run locale-gen inside chroot
    rc, _, stderr = run("locale-gen", chroot=True)
    if rc != 0:
        return False, f"locale-gen failed: {stderr}"

    # Write locale.conf
    locale_conf_path = os.path.join(MOUNT_POINT, "etc", "locale.conf")
    try:
        with open(locale_conf_path, "w") as f:
            f.write(f"LANG={locale}\n")
    except OSError as e:
        return False, f"Failed to write locale.conf: {e}"

    log_info(f"Locale set to {locale}")
    return True, ""


def apply_timezone(timezone: str) -> tuple[bool, str]:
    """
    Apply timezone settings inside the chroot.

    Steps:
    1. Symlink /etc/localtime
    2. Run hwclock --systohc
    """
    rc, _, stderr = run(
        f"ln -sf /usr/share/zoneinfo/{timezone} /etc/localtime",
        chroot=True
    )
    if rc != 0:
        return False, f"Failed to set timezone: {stderr}"

    rc, _, stderr = run("hwclock --systohc", chroot=True)
    if rc != 0:
        return False, f"hwclock failed: {stderr}"

    log_info(f"Timezone set to {timezone}")
    return True, ""


def apply_keymap(keymap: str) -> tuple[bool, str]:
    """
    Apply keyboard layout inside the chroot by writing /etc/vconsole.conf.
    """
    vconsole_path = os.path.join(MOUNT_POINT, "etc", "vconsole.conf")
    try:
        with open(vconsole_path, "w") as f:
            f.write(f"KEYMAP={keymap}\n")
    except OSError as e:
        return False, f"Failed to write vconsole.conf: {e}"

    log_info(f"Keymap set to {keymap}")
    return True, ""
