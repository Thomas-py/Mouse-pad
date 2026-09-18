import XCTest
@testable import RemotePad

/// Tests del GestureEngine con secuencias de touches sintéticas y timestamps
/// controlados (no hay `Timer`/sleeps reales — ver comentario en
/// GestureEngine.swift sobre por qué está diseñado como una máquina
/// impulsada externamente). No se pudieron correr en esta sesión (sin
/// Swift/Xcode disponibles) — quedan listos para cuando exista build real
/// (S-05). Ver docs/04-STORIES.md S-11.
final class GestureEngineTests: XCTestCase {
    private final class TouchToken {}

    private func makeTouchID() -> GestureTouchID {
        GestureTouchID(ObjectIdentifier(TouchToken()))
    }

    private func makeEngine() -> (GestureEngine, RecordingSink) {
        let engine = GestureEngine()
        let sink = RecordingSink()
        engine.onIntent = { sink.intents.append($0) }
        return (engine, sink)
    }

    private final class RecordingSink {
        var intents: [GestureIntent] = []
    }

    // MARK: - Tap simple (F-05)

    func test_singleTap_emitsClickImmediately() {
        let (engine, sink) = makeEngine()
        let touch = makeTouchID()
        let point = CGPoint(x: 100, y: 100)

        engine.touchesBegan([(touch, point)], now: 0.0)
        engine.touchesEnded([touch], now: 0.05) // 50ms, bien dentro de tapMaxDuration (180ms)

        XCTAssertEqual(sink.intents, [.hapticLight, .click])
    }

    func test_tapThatMovesTooMuch_isNotATap() {
        let (engine, sink) = makeEngine()
        let touch = makeTouchID()
        let start = CGPoint(x: 100, y: 100)
        let moved = CGPoint(x: 130, y: 100) // 30pt > tapMaxMovement (10pt)

        engine.touchesBegan([(touch, start)], now: 0.0)
        engine.touchesMoved([(touch, moved)], now: 0.02)
        engine.touchesEnded([touch], now: 0.05)

        XCTAssertEqual(sink.intents, [.move(dx: 30, dy: 0)])
    }

    func test_tapThatLastsTooLong_isNotATap() {
        let (engine, sink) = makeEngine()
        let touch = makeTouchID()
        let point = CGPoint(x: 100, y: 100)

        engine.touchesBegan([(touch, point)], now: 0.0)
        // se queda quieto, no llega a los 400ms de hold-to-drag, pero supera
        // tapMaxDuration (180ms) antes de soltar
        engine.touchesEnded([touch], now: 0.30)

        XCTAssertEqual(sink.intents, [])
    }

    // MARK: - Doble tap (F-05)

    func test_doubleTap_emitsTwoClicks() {
        let (engine, sink) = makeEngine()
        let firstTouch = makeTouchID()
        let secondTouch = makeTouchID()
        let point = CGPoint(x: 50, y: 50)

        engine.touchesBegan([(firstTouch, point)], now: 0.0)
        engine.touchesEnded([firstTouch], now: 0.05)

        engine.touchesBegan([(secondTouch, point)], now: 0.15) // dentro de doubleTapWindow (250ms)
        engine.touchesEnded([secondTouch], now: 0.18)

        XCTAssertEqual(sink.intents, [.hapticLight, .click, .hapticLight, .click])
    }

    func test_secondTapAfterWindowExpires_isIndependentTap() {
        let (engine, sink) = makeEngine()
        let firstTouch = makeTouchID()
        let secondTouch = makeTouchID()
        let point = CGPoint(x: 50, y: 50)

        engine.touchesBegan([(firstTouch, point)], now: 0.0)
        engine.touchesEnded([firstTouch], now: 0.05)
        engine.tick(now: 0.05 + 0.250 + 0.01) // vence doubleTapWindow

        engine.touchesBegan([(secondTouch, point)], now: 1.0)
        engine.touchesEnded([secondTouch], now: 1.05)

        XCTAssertEqual(sink.intents, [.hapticLight, .click, .hapticLight, .click])
    }

    // MARK: - Clic derecho (F-06)

    func test_twoFingerQuickTap_emitsRightClick() {
        let (engine, sink) = makeEngine()
        let a = makeTouchID()
        let b = makeTouchID()

        engine.touchesBegan(
            [(a, CGPoint(x: 10, y: 10)), (b, CGPoint(x: 40, y: 10))],
            now: 0.0
        )
        engine.touchesEnded([a, b], now: 0.05)

        XCTAssertEqual(sink.intents, [.hapticMedium, .rightClick])
    }

    func test_twoFingerTapThatMoves_isNotRightClick_becomesScroll() {
        let (engine, sink) = makeEngine()
        let a = makeTouchID()
        let b = makeTouchID()

        engine.touchesBegan(
            [(a, CGPoint(x: 10, y: 10)), (b, CGPoint(x: 40, y: 10))],
            now: 0.0
        )
        engine.touchesMoved(
            [(a, CGPoint(x: 10, y: 30)), (b, CGPoint(x: 40, y: 30))],
            now: 0.02
        )
        engine.touchesEnded([a, b], now: 0.05)

        XCTAssertEqual(sink.intents, [.scroll(dx: 0, dy: 20)])
    }

    // MARK: - Scroll (F-08)

    func test_twoFingerScroll_averagesDeltas() {
        let (engine, sink) = makeEngine()
        let a = makeTouchID()
        let b = makeTouchID()

        engine.touchesBegan(
            [(a, CGPoint(x: 0, y: 0)), (b, CGPoint(x: 50, y: 0))],
            now: 0.0
        )
        engine.touchesMoved(
            [(a, CGPoint(x: 0, y: 20)), (b, CGPoint(x: 50, y: 24))],
            now: 0.02
        )

        XCTAssertEqual(sink.intents, [.scroll(dx: 0, dy: 22)])
    }

    // MARK: - Drag por hold (F-07, alternativa "mantener presionado")

    func test_holdWithoutMoving_startsDragAfter400ms() {
        let (engine, sink) = makeEngine()
        let touch = makeTouchID()
        let point = CGPoint(x: 100, y: 100)

        engine.touchesBegan([(touch, point)], now: 0.0)
        engine.tick(now: 0.39) // todavía no
        XCTAssertEqual(sink.intents, [])

        engine.tick(now: 0.41) // pasó holdToDragDuration (400ms)
        XCTAssertEqual(sink.intents, [.hapticMedium, .dragStart])

        engine.touchesMoved([(touch, CGPoint(x: 110, y: 100))], now: 0.42)
        engine.touchesEnded([touch], now: 0.5)

        XCTAssertEqual(
            sink.intents,
            [.hapticMedium, .dragStart, .dragMove(dx: 10, dy: 0), .dragEnd]
        )
    }

    // MARK: - Drag por tap-y-retap (F-07)

    func test_tapThenRetapAndMove_startsDrag_whenTapToDragEnabled() {
        let (engine, sink) = makeEngine()
        engine.tapToDragEnabled = true
        let first = makeTouchID()
        let second = makeTouchID()
        let point = CGPoint(x: 50, y: 50)

        engine.touchesBegan([(first, point)], now: 0.0)
        engine.touchesEnded([first], now: 0.05) // click inmediato

        engine.touchesBegan([(second, point)], now: 0.10) // dentro de dragHoldWindow (250ms)
        engine.touchesMoved([(second, CGPoint(x: 65, y: 50))], now: 0.15) // > tapMaxMovement

        XCTAssertEqual(
            sink.intents,
            [.hapticLight, .click, .hapticMedium, .dragStart, .dragMove(dx: 15, dy: 0)]
        )

        engine.touchesEnded([second], now: 0.20)
        XCTAssertEqual(
            sink.intents,
            [.hapticLight, .click, .hapticMedium, .dragStart, .dragMove(dx: 15, dy: 0), .dragEnd]
        )
    }

    func test_tapThenRetapAndMove_isSecondClick_whenTapToDragDisabled() {
        let (engine, sink) = makeEngine()
        engine.tapToDragEnabled = false
        let first = makeTouchID()
        let second = makeTouchID()
        let point = CGPoint(x: 50, y: 50)

        engine.touchesBegan([(first, point)], now: 0.0)
        engine.touchesEnded([first], now: 0.05)

        engine.touchesBegan([(second, point)], now: 0.10)
        engine.touchesMoved([(second, CGPoint(x: 65, y: 50))], now: 0.15) // se ignora: tapToDrag off
        engine.touchesEnded([second], now: 0.20)

        XCTAssertEqual(sink.intents, [.hapticLight, .click, .hapticLight, .click])
    }

    // MARK: - Cambio de cantidad de dedos (regla 5)

    func test_secondFingerDuringMove_resetsToTwoFingerGesture() {
        let (engine, sink) = makeEngine()
        let a = makeTouchID()
        let b = makeTouchID()

        engine.touchesBegan([(a, CGPoint(x: 0, y: 0))], now: 0.0)
        engine.touchesMoved([(a, CGPoint(x: 20, y: 0))], now: 0.02) // -> moving, emite 1 .move

        // UIKit solo entrega el touch nuevo (b) en touchesBegan, no el que ya
        // estaba en curso (a) — el motor tiene que combinarlos internamente.
        engine.touchesBegan([(b, CGPoint(x: 60, y: 0))], now: 0.03)
        engine.touchesEnded([a, b], now: 0.06) // tap de 2 dedos rápido -> rightClick

        XCTAssertEqual(sink.intents, [.move(dx: 20, dy: 0), .hapticMedium, .rightClick])
    }
}
