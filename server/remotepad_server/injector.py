"""Wrapper sobre pynput.mouse.Controller — inyección de eventos de mouse (F-23, F-24)."""

from __future__ import annotations

import logging
import os
import sys

from pynput.mouse import Button, Controller

logger = logging.getLogger(__name__)

_BUTTON_MAP: dict[str, Button] = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}


class WaylandNotSupportedError(RuntimeError):
    """pynput no puede inyectar eventos en una sesión Wayland (solo X11 en v1)."""


def check_platform_supported() -> None:
    if sys.platform.startswith("linux"):
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session_type == "wayland":
            raise WaylandNotSupportedError(
                "Sesión Wayland detectada ($XDG_SESSION_TYPE=wayland). "
                "RemotePad v1 solo soporta X11 en Linux — pynput no puede "
                "inyectar eventos de mouse en Wayland. Iniciá sesión en X11/Xorg."
            )


def _resolve_button(button: str) -> Button:
    try:
        return _BUTTON_MAP[button]
    except KeyError as exc:
        raise ValueError(f"botón desconocido: {button!r}") from exc


class InputInjector:
    """Inyecta movimiento/clics/scroll reales en la PC vía pynput."""

    def __init__(self, controller: Controller | None = None) -> None:
        check_platform_supported()
        self._controller = controller if controller is not None else Controller()
        self._pressed: set[Button] = set()

    def move(self, dx: int, dy: int) -> None:
        self._controller.move(dx, dy)

    def press(self, button: str) -> None:
        btn = _resolve_button(button)
        self._controller.press(btn)
        self._pressed.add(btn)

    def release(self, button: str) -> None:
        btn = _resolve_button(button)
        self._controller.release(btn)
        self._pressed.discard(btn)

    def click(self, button: str, count: int = 1) -> None:
        self._controller.click(_resolve_button(button), count)

    def scroll(self, dx: int, dy: int) -> None:
        self._controller.scroll(dx, dy)

    def release_all(self) -> None:
        """Suelta cualquier botón que haya quedado presionado (fin de sesión / drag colgado)."""
        for btn in list(self._pressed):
            self._controller.release(btn)
        self._pressed.clear()
