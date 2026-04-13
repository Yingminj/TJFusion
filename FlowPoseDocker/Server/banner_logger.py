#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import platform
from typing import List, Optional

try:
    import torch
except Exception:
    torch = None

try:
    import cv2
except Exception:
    cv2 = None


def _supports_color() -> bool:
    return sys.stdout.isatty()


if _supports_color():
    CYAN = "\033[1;36m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    MAGENTA = "\033[1;35m"
    BLUE = "\033[1;34m"
    RESET = "\033[0m"
else:
    CYAN = ""
    GREEN = ""
    YELLOW = ""
    RED = ""
    MAGENTA = ""
    BLUE = ""
    RESET = ""


def color_text(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def log_info(msg: str) -> None:
    print(f"{GREEN}[INFO]{RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def log_error(msg: str) -> None:
    print(f"{RED}[ERROR]{RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET} {msg}")


def log_step(msg: str) -> None:
    print(f"{BLUE}[STEP]{RESET} {msg}")


def print_separator(width: int = 92, color: str = CYAN) -> None:
    print(f"{color}{'=' * width}{RESET}")


def print_banner(
    title: str,
    version: str,
    ascii_lines: Optional[List[str]] = None,
    width: int = 92,
    title_indent: int = 28,
    version_indent: int = 32,
) -> None:
    print_separator(width=width, color=CYAN)

    if ascii_lines:
        for row in ascii_lines:
            print(f"{CYAN}{row}{RESET}")

    print(f"{YELLOW}{' ' * title_indent}{title}{RESET}")
    print(f"{MAGENTA}{' ' * version_indent}Version: {version}{RESET}")
    print_separator(width=width, color=CYAN)


def print_runtime_info(
    python: bool = True,
    pytorch: bool = True,
    opencv: bool = True,
    cuda: bool = True,
) -> None:
    if python:
        log_info(f"Python version: {platform.python_version()}")

    if pytorch:
        if torch is not None:
            log_info(f"PyTorch version: {torch.__version__}")
        else:
            log_warn("PyTorch not available")

    if opencv:
        if cv2 is not None:
            log_info(f"OpenCV version: {cv2.__version__}")
        else:
            log_warn("OpenCV not available")

    if cuda:
        if torch is None:
            log_warn("CUDA status unknown because PyTorch is unavailable")
        else:
            available = torch.cuda.is_available()
            log_info(f"CUDA available: {available}")
            if available:
                try:
                    log_info(f"CUDA device count: {torch.cuda.device_count()}")
                    log_info(f"CUDA device[0]: {torch.cuda.get_device_name(0)}")
                except Exception as e:
                    log_warn(f"Failed to query CUDA device info: {e}")


FLOWPOSE_SERVER_BANNER = [
    r"  ______ _                       _____                       ",
    r" |  ____| |                     / ____|                      ",
    r" | |__  | | _____      ___ __  | (___   ___ _ ____   _____ _ __ ",
    r" |  __| | |/ _ \ \ /\ / / '_ \  \___ \ / _ \ '__\ \ / / _ \ '__|",
    r" | |    | | (_) \ V  V /| |_) | ____) |  __/ |   \ V /  __/ |   ",
    r" |_|    |_|\___/ \_/\_/ | .__/ |_____/ \___|_|    \_/ \___|_|   ",
    r"                        | |                                      ",
    r"                        |_|                                      ",
]

def print_flowpose_banner(version: str) -> None:
    print_banner(
        title="FLOWPOSE ZMQ SERVER",
        version=version,
        ascii_lines=FLOWPOSE_SERVER_BANNER,
        width=92,
        title_indent=28,
        version_indent=32,
    )