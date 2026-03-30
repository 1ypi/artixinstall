"""
artixinstall.tui.screen — Screen and window management, color scheme, layout.

Provides the Screen class that initializes curses, defines the color palette,
and offers helper methods for drawing headers, footers, and content areas.
"""

import curses

# Application version
VERSION = "1.0.4"
HEADER_TEXT = f"Artix Install — v{VERSION}"

# Color pair IDs
COLOR_NORMAL = 1
COLOR_HEADER = 2
COLOR_SELECTED = 3
COLOR_VALUE_SET = 4
COLOR_VALUE_UNSET = 5
COLOR_ERROR = 6
COLOR_SUCCESS = 7
COLOR_SEPARATOR = 8
COLOR_DIM = 9
COLOR_PROGRESS = 10
COLOR_TITLE = 11


def init_colors() -> None:
    """Initialize the color palette for the installer TUI."""
    curses.start_color()
    curses.use_default_colors()

    # Normal text: white on black
    curses.init_pair(COLOR_NORMAL, curses.COLOR_WHITE, curses.COLOR_BLACK)
    # Header/footer: white on dark blue
    curses.init_pair(COLOR_HEADER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    # Selected item: black on cyan
    curses.init_pair(COLOR_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
    # Confirmed value: green on black
    curses.init_pair(COLOR_VALUE_SET, curses.COLOR_GREEN, curses.COLOR_BLACK)
    # Unset/warning value: yellow on black
    curses.init_pair(COLOR_VALUE_UNSET, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    # Error text: red on black
    curses.init_pair(COLOR_ERROR, curses.COLOR_RED, curses.COLOR_BLACK)
    # Success text: green on black
    curses.init_pair(COLOR_SUCCESS, curses.COLOR_GREEN, curses.COLOR_BLACK)
    # Separator line: cyan on black
    curses.init_pair(COLOR_SEPARATOR, curses.COLOR_CYAN, curses.COLOR_BLACK)
    # Dimmed text: dark (effectively gray) on black
    curses.init_pair(COLOR_DIM, curses.COLOR_WHITE, curses.COLOR_BLACK)
    # Progress indicator: cyan on black
    curses.init_pair(COLOR_PROGRESS, curses.COLOR_CYAN, curses.COLOR_BLACK)
    # Title text: bold cyan on black
    curses.init_pair(COLOR_TITLE, curses.COLOR_CYAN, curses.COLOR_BLACK)


class Screen:
    """
    Manages the main curses screen — header, footer, and content area.

    Usage:
        screen = Screen(stdscr)
        screen.draw_header()
        screen.draw_footer("↑↓ Navigate  Enter Select  Q Quit")
    """

    def __init__(self, stdscr: curses.window) -> None:
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()

        # Configure curses
        curses.curs_set(0)          # Hide cursor
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        stdscr.timeout(-1)         # Blocking input

        init_colors()

        # Define layout regions
        self.header_y = 0
        self.content_y = 2          # Content starts after header + blank line
        self.footer_y = self.height - 1
        # Usable content height (between header and footer)
        self.content_height = self.height - 4  # header(1) + blank(1) + blank(1) + footer(1)

    def refresh_size(self) -> None:
        """Re-read terminal dimensions (e.g. after resize)."""
        self.height, self.width = self.stdscr.getmaxyx()
        self.footer_y = self.height - 1
        self.content_height = self.height - 4

    def clear(self) -> None:
        """Clear the entire screen."""
        self.stdscr.clear()

    def draw_header(self, text: str | None = None) -> None:
        """Draw the header bar across the top of the screen."""
        header = text or HEADER_TEXT
        header_line = header.center(self.width)
        try:
            self.stdscr.addstr(
                self.header_y, 0, header_line[:self.width],
                curses.color_pair(COLOR_HEADER) | curses.A_BOLD
            )
        except curses.error:
            pass

    def draw_footer(self, text: str) -> None:
        """Draw the footer bar across the bottom of the screen."""
        footer_line = text.center(self.width)
        try:
            self.stdscr.addstr(
                self.footer_y, 0, footer_line[:self.width - 1],
                curses.color_pair(COLOR_HEADER)
            )
        except curses.error:
            pass

    def draw_text(self, y: int, x: int, text: str,
                  color_pair: int = COLOR_NORMAL,
                  bold: bool = False) -> None:
        """Draw text at a given position with optional styling."""
        attr = curses.color_pair(color_pair)
        if bold:
            attr |= curses.A_BOLD
        try:
            # Truncate to prevent writing past the right edge
            max_len = self.width - x - 1
            if max_len > 0:
                self.stdscr.addstr(y, x, text[:max_len], attr)
        except curses.error:
            pass

    def draw_separator(self, y: int) -> None:
        """Draw a horizontal separator line."""
        sep = "─" * (self.width - 4)
        self.draw_text(y, 2, sep, COLOR_SEPARATOR)

    def show_message(self, title: str, message: str,
                     color: int = COLOR_NORMAL) -> None:
        """
        Show a centered message box and wait for any key press.
        Useful for errors, confirmations, and informational popups.
        """
        self.clear()
        self.draw_header()

        lines = message.split("\n")
        start_y = max(self.content_y + 1, (self.height - len(lines)) // 2 - 1)

        # Title
        self.draw_text(start_y, 2, title, COLOR_TITLE, bold=True)

        # Message lines
        for i, line in enumerate(lines):
            self.draw_text(start_y + 2 + i, 4, line, color)

        self.draw_footer("Press any key to continue")
        self.stdscr.refresh()
        self.stdscr.getch()

    def show_error(self, message: str) -> None:
        """Show an error message popup."""
        self.show_message("Error", message, COLOR_ERROR)

    def show_success(self, message: str) -> None:
        """Show a success message popup."""
        self.show_message("Success", message, COLOR_SUCCESS)

    def get_input(self) -> int:
        """Get a single keypress from the user."""
        try:
            return self.stdscr.getch()
        except curses.error:
            return -1
