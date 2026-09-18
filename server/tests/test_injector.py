import sys
from unittest.mock import MagicMock

import pytest
from pynput.mouse import Button

from remotepad_server.injector import (
    InputInjector,
    WaylandNotSupportedError,
    check_platform_supported,
)


@pytest.fixture
def controller() -> MagicMock:
    return MagicMock()


@pytest.fixture
def injector(controller: MagicMock) -> InputInjector:
    return InputInjector(controller=controller)


def test_move_calls_controller(injector: InputInjector, controller: MagicMock) -> None:
    injector.move(5, -3)
    controller.move.assert_called_once_with(5, -3)


def test_press_and_release(injector: InputInjector, controller: MagicMock) -> None:
    injector.press("left")
    controller.press.assert_called_once_with(Button.left)
    injector.release("left")
    controller.release.assert_called_once_with(Button.left)


def test_click_default_count_is_one(injector: InputInjector, controller: MagicMock) -> None:
    injector.click("left")
    controller.click.assert_called_once_with(Button.left, 1)


def test_click_double(injector: InputInjector, controller: MagicMock) -> None:
    injector.click("left", count=2)
    controller.click.assert_called_once_with(Button.left, 2)


def test_right_and_middle_button_map(injector: InputInjector, controller: MagicMock) -> None:
    injector.click("right")
    injector.click("middle")
    controller.click.assert_any_call(Button.right, 1)
    controller.click.assert_any_call(Button.middle, 1)


def test_scroll_calls_controller(injector: InputInjector, controller: MagicMock) -> None:
    injector.scroll(0, -3)
    controller.scroll.assert_called_once_with(0, -3)


def test_release_all_releases_every_pressed_button(
    injector: InputInjector, controller: MagicMock
) -> None:
    injector.press("left")
    injector.press("right")
    injector.release_all()
    assert controller.release.call_count == 2
    controller.release.assert_any_call(Button.left)
    controller.release.assert_any_call(Button.right)


def test_release_all_is_noop_when_nothing_pressed(
    injector: InputInjector, controller: MagicMock
) -> None:
    injector.release_all()
    controller.release.assert_not_called()


def test_release_all_does_not_release_twice(
    injector: InputInjector, controller: MagicMock
) -> None:
    injector.press("left")
    injector.release_all()
    injector.release_all()
    assert controller.release.call_count == 1


def test_unknown_button_raises_value_error(injector: InputInjector) -> None:
    with pytest.raises(ValueError):
        injector.press("nope")


def test_wayland_session_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    with pytest.raises(WaylandNotSupportedError):
        check_platform_supported()


def test_x11_session_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    check_platform_supported()  # no debe lanzar
