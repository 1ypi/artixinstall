"""
artixinstall.installer.locale — Locale, timezone, and keyboard layout configuration.

Handles setting the system locale, timezone, keyboard layout, and hardware
clock inside the chroot.
"""

import curses
import os
from pathlib import Path

from artixinstall.utils.shell import run, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.tui.screen import (
    Screen, COLOR_NORMAL, COLOR_SELECTED, COLOR_SEPARATOR, COLOR_TITLE,
    COLOR_VALUE_SET, COLOR_VALUE_UNSET,
)
from artixinstall.tui.menu import run_selection_menu, run_menu, MenuItem
from artixinstall.tui.prompts import text_input
from artixinstall.utils.validate import is_valid_locale


def _get_data_dir() -> Path:
    """Get the path to the data directory."""
    return Path(__file__).parent.parent / "data"


def _search_locales(screen: Screen, all_locales: list[str]) -> str | None:
    query = ""
    filtered = list(all_locales)
    selected_idx = 0
    scroll_offset = 0

    while True:
        screen.refresh_size()
        screen.clear()
        screen.draw_header()
        footer = "↑↓ Navigate  Enter Select  / Search  c Clear  C Custom  ESC Back"
        screen.draw_footer(footer)

        screen.draw_text(screen.content_y, 2, "Select Locale", COLOR_TITLE, bold=True)
        query_text = query if query else "(all locales)"
        screen.draw_text(screen.content_y + 1, 2, f"Filter: {query_text}", COLOR_VALUE_SET if query else COLOR_VALUE_UNSET)
        screen.draw_text(screen.content_y + 2, 2, f"Available: {len(all_locales)}  Showing: {len(filtered)}", COLOR_SEPARATOR)

        list_start_y = screen.content_y + 4
        visible_count = max(1, screen.content_height - 5)

        if selected_idx >= len(filtered):
            selected_idx = max(0, len(filtered) - 1)

        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + visible_count:
            scroll_offset = selected_idx - visible_count + 1

        if not filtered:
            screen.draw_text(list_start_y, 4, "No locales match the current filter.", COLOR_VALUE_UNSET)
        else:
            for draw_idx in range(visible_count):
                locale_idx = scroll_offset + draw_idx
                if locale_idx >= len(filtered):
                    break
                locale = filtered[locale_idx]
                y = list_start_y + draw_idx
                label = f"  {locale}"
                if locale_idx == selected_idx:
                    screen.draw_text(y, 1, label.ljust(screen.width - 2)[:screen.width - 2], COLOR_SELECTED)
                else:
                    screen.draw_text(y, 4, label, COLOR_NORMAL)

        screen.stdscr.refresh()
        key = screen.get_input()

        if key == curses.KEY_RESIZE:
            continue
        if key in (27, ord('q'), ord('Q')):
            return None
        if key in (curses.KEY_UP, ord('k')) and filtered:
            selected_idx = max(0, selected_idx - 1)
        elif key in (curses.KEY_DOWN, ord('j')) and filtered:
            selected_idx = min(len(filtered) - 1, selected_idx + 1)
        elif key == curses.KEY_HOME and filtered:
            selected_idx = 0
        elif key == curses.KEY_END and filtered:
            selected_idx = len(filtered) - 1
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')) and filtered:
            return filtered[selected_idx]
        elif key == ord('/'):
            result = text_input(screen, "Search locales:", default=query)
            if result is None:
                continue
            query = result.strip().lower()
            filtered = [loc for loc in all_locales if query in loc.lower()] if query else list(all_locales)
            selected_idx = 0
            scroll_offset = 0
        elif key in (ord('c'), ord('C')):
            if key == ord('C'):
                # Capital C: custom input
                custom = text_input(screen, "Enter locale (e.g. en_US.UTF-8):",
                                  default="en_US.UTF-8",
                                  validator=is_valid_locale)
                if custom is not None:
                    return custom
            else:
                # Lowercase c: clear filter
                query = ""
                filtered = list(all_locales)
                selected_idx = 0
                scroll_offset = 0


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
    locales = load_locale_list()
    return _search_locales(screen, locales)


def _get_continents() -> list[str]:
    zoneinfo = "/usr/share/zoneinfo"
    if not os.path.isdir(zoneinfo):
        return []

    excluded = {"posix", "right", "Etc", "SystemV", "US", "Brazil",
                "Canada", "Chile", "Mexico", "Cuba", "Egypt",
                "Eire", "GMT", "Greenwich", "Hongkong", "Iceland",
                "Iran", "Israel", "Jamaica", "Japan", "Kwajalein",
                "Libya", "Navajo", "Poland", "Portugal", "Singapore",
                "Turkey", "Zulu", "leap-seconds.list", "leapseconds",
                "posixrules", "tzdata.zi", "zone.tab", "zone1970.tab",
                "iso3166.tab"}

    return sorted([
        d for d in os.listdir(zoneinfo)
        if os.path.isdir(os.path.join(zoneinfo, d))
        and d not in excluded
        and not d.startswith(".")
        and not d.startswith("+")
    ])


def _get_cities(continent: str) -> list[str]:
    region_path = os.path.join("/usr/share/zoneinfo", continent)
    entries = []
    for entry in sorted(os.listdir(region_path)):
        entry_path = os.path.join(region_path, entry)
        if os.path.isdir(entry_path):
            for sub in sorted(os.listdir(entry_path)):
                if os.path.isfile(os.path.join(entry_path, sub)):
                    entries.append(f"{entry}/{sub}")
        elif os.path.isfile(entry_path):
            entries.append(entry)
    return entries


def _search_cities(screen: Screen, continent: str, all_cities: list[str]) -> str | None:
    query = ""
    filtered = list(all_cities)
    selected_idx = 0
    scroll_offset = 0
    searching = False

    while True:
        screen.refresh_size()
        screen.clear()
        screen.draw_header()
        if searching:
            screen.draw_footer("Type to filter  ↑↓ Navigate  Enter Accept  ESC Cancel search")
        else:
            screen.draw_footer("↑↓ Navigate  Enter Select  / Search  c Clear  ESC Back")

        screen.draw_text(screen.content_y, 2, f"Select city ({continent})", COLOR_TITLE, bold=True)

        if searching:
            query_display = f"Search: {query}▏"
        else:
            query_display = f"Filter: {query}" if query else "Filter: (all cities)"
        screen.draw_text(screen.content_y + 1, 2, query_display,
                         COLOR_VALUE_SET if query else COLOR_VALUE_UNSET)
        screen.draw_text(screen.content_y + 2, 2,
                         f"Available: {len(all_cities)}  Showing: {len(filtered)}",
                         COLOR_SEPARATOR)

        list_start_y = screen.content_y + 4
        visible_count = max(1, screen.content_height - 5)

        if selected_idx >= len(filtered):
            selected_idx = max(0, len(filtered) - 1)
        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + visible_count:
            scroll_offset = selected_idx - visible_count + 1

        if not filtered:
            screen.draw_text(list_start_y, 4, "No cities match the current filter.",
                             COLOR_VALUE_UNSET)
        else:
            for draw_idx in range(visible_count):
                city_idx = scroll_offset + draw_idx
                if city_idx >= len(filtered):
                    break
                city = filtered[city_idx]
                y = list_start_y + draw_idx
                label = f"  {city}"
                if city_idx == selected_idx:
                    screen.draw_text(y, 1,
                                     label.ljust(screen.width - 2)[:screen.width - 2],
                                     COLOR_SELECTED)
                else:
                    screen.draw_text(y, 4, label, COLOR_NORMAL)

        screen.stdscr.refresh()
        key = screen.get_input()

        if key == curses.KEY_RESIZE:
            continue

        if searching:
            if key == 27:
                searching = False
                curses.curs_set(0)
                continue
            elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
                searching = False
                curses.curs_set(0)
                if filtered:
                    return filtered[selected_idx]
                continue
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if query:
                    query = query[:-1]
                    filtered = ([c for c in all_cities if query.lower() in c.lower()]
                                if query else list(all_cities))
                    selected_idx = 0
                    scroll_offset = 0
            elif key in (curses.KEY_UP, ord('k')) and filtered:
                selected_idx = max(0, selected_idx - 1)
            elif key in (curses.KEY_DOWN, ord('j')) and filtered:
                selected_idx = min(len(filtered) - 1, selected_idx + 1)
            elif 32 <= key <= 126:
                query += chr(key)
                filtered = [c for c in all_cities if query.lower() in c.lower()]
                selected_idx = 0
                scroll_offset = 0
            continue

        if key in (27, ord('q'), ord('Q')):
            return None
        elif key in (curses.KEY_UP, ord('k')) and filtered:
            selected_idx = max(0, selected_idx - 1)
        elif key in (curses.KEY_DOWN, ord('j')) and filtered:
            selected_idx = min(len(filtered) - 1, selected_idx + 1)
        elif key == curses.KEY_HOME and filtered:
            selected_idx = 0
        elif key == curses.KEY_END and filtered:
            selected_idx = len(filtered) - 1
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')) and filtered:
            return filtered[selected_idx]
        elif key == ord('/'):
            searching = True
            curses.curs_set(1)
        elif key == ord('c'):
            query = ""
            filtered = list(all_cities)
            selected_idx = 0
            scroll_offset = 0


def configure_timezone(screen: Screen) -> str | None:
    zoneinfo = "/usr/share/zoneinfo"

    if not os.path.isdir(zoneinfo):
        return text_input(screen, "Enter timezone (e.g. Europe/Berlin):",
                          default="UTC")

    continents = _get_continents()
    if not continents:
        return text_input(screen, "Enter timezone (e.g. Europe/Berlin):",
                          default="UTC")

    options = ["UTC", "Set manual timezone (Continent/Region)"] + continents
    while True:
        selected = run_selection_menu(screen, "Select region", options)
        if selected is None:
            return None

        if selected == "UTC":
            return "UTC"

        if selected == "Set manual timezone (Continent/Region)":
            custom = text_input(screen, "Enter timezone (e.g. Europe/Berlin):",
                                default="Europe/Berlin")
            if custom is not None:
                return custom
            continue

        cities = _get_cities(selected)
        if not cities:
            return selected

        city = _search_cities(screen, selected, cities)
        if city is None:
            continue
        return f"{selected}/{city}"


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
