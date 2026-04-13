from __future__ import annotations

import os
import sys

RESET = "\033[0m"
COLOR_CODES = {
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}

MARVIN_ROBOT_SYSTEM_BANNER = [
    r"===============================================================",
    r" __  __    _    ____  __     _____ _   _                       ",
    r"|  \/  |  / \  |  _ \ \ \   / /_ _| \ | |                      ",
    r"| |\/| | / _ \ | |_) | \ \ / / | ||  \| |                      ",
    r"| |  | |/ ___ \|  _ <   \ V /  | || |\  |                      ",
    r"|_|  |_/_/   \_\_| \_\   \_/  |___|_| \_|                      ",
    r"                                                               ",
    r" ____       _           _      ____            _               ",
    r"|  _ \ ___ | |__   ___ | |_   / ___| _   _ ___| |_ ___ _ __    ",
    r"| |_) / _ \| '_ \ / _ \| __|  \___ \| | | / __| __/ _ \ '_ \   ",
    r"|  _ < (_) | |_) | (_) | |_    ___) | |_| \__ \ ||  __/ | | |  ",
    r"|_| \_\___/|_.__/ \___/ \__|  |____/ \__, |___/\__\___|_| |_|  ",
    r"                                      |___/                    ",
    r"===============================================================",
]


def supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR") not in {None, "", "0"}:
        return True
    if os.getenv("CLICOLOR_FORCE") not in {None, "", "0"}:
        return True
    return sys.stdout.isatty() and os.getenv("TERM", "").lower() != "dumb"


def colorize(
    text: str,
    *,
    color: str | None = None,
    bold: bool = False,
    dim: bool = False,
) -> str:
    if not supports_color():
        return text

    prefixes: list[str] = []
    if bold:
        prefixes.append(COLOR_CODES["bold"])
    if dim:
        prefixes.append(COLOR_CODES["dim"])
    if color:
        prefixes.append(COLOR_CODES[color])
    return f"{''.join(prefixes)}{text}{RESET}"


def print_banner() -> None:
    colors = [
        "cyan",
        "cyan",
        "blue",
        "magenta",
        "blue",
        "magenta",
        "white",
        "cyan",
        "blue",
        "magenta",
        "blue",
        "magenta",
        "white",
        "cyan",
    ]
    for line, color in zip(MARVIN_ROBOT_SYSTEM_BANNER, colors, strict=False):
        print(colorize(line, color=color, bold=True))


def print_status(tag: str, message: str, *, color: str = "cyan") -> None:
    label = colorize(f"[{tag}]", color=color, bold=True)
    print(f"{label} {message}")


def print_success(message: str) -> None:
    print_status("OK", message, color="green")


def print_warning(message: str) -> None:
    print_status("WARN", message, color="yellow")


def print_error(message: str) -> None:
    print_status("ERROR", message, color="red")
