"""Demo manual del InputInjector: mueve el mouse en un cuadrado y hace un clic.

Correr en la PC real (no en CI): python -m scripts.demo_injector
Mueve el mouse de verdad — soltar el mouse y no tocar el teclado mientras corre.
"""

import time

from remotepad_server.injector import InputInjector


def main() -> None:
    injector = InputInjector()
    print("Moviendo en cuadrado en 2 segundos...")
    time.sleep(2)

    steps = [(120, 0), (0, 120), (-120, 0), (0, -120)]
    for dx, dy in steps:
        injector.move(dx, dy)
        time.sleep(0.4)

    injector.click("left")
    print("Listo: cuadrado completado + 1 clic izquierdo.")


if __name__ == "__main__":
    main()
