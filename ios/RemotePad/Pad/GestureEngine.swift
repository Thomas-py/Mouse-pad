import CoreGraphics
import Foundation

/// Parámetros de `GestureEngine` — docs/01-ARQUITECTURA.md §2 "GestureEngine".
struct GestureConfig {
    var tapMaxDuration: TimeInterval = 0.180
    var tapMaxMovement: CGFloat = 10
    var doubleTapWindow: TimeInterval = 0.250
    var dragHoldWindow: TimeInterval = 0.250
    var holdToDragDuration: TimeInterval = 0.400
}

/// Lo que produce el motor; quien lo consume (PadScreen) decide qué hacer
/// con cada uno (mover el mouse, mandar `btn`, etc). F-05..F-08.
enum GestureIntent: Equatable {
    case move(dx: Double, dy: Double)
    case click
    case rightClick
    case hapticLight
    case hapticMedium
    case dragStart
    case dragMove(dx: Double, dy: Double)
    case dragEnd
    case scroll(dx: Double, dy: Double)
}

/// Identificador liviano de touch — desacopla el motor de UIKit para poder
/// testearlo con secuencias sintéticas (docs/04-STORIES.md S-11: "tests
/// unitarios... con secuencias de touches simuladas").
struct GestureTouchID: Hashable {
    private let raw: ObjectIdentifier
    init(_ raw: ObjectIdentifier) { self.raw = raw }
}

private enum EngineState {
    case idle
    case touching(id: GestureTouchID, start: CGPoint, startTime: TimeInterval)
    case moving(id: GestureTouchID, last: CGPoint)
    case twoFingerDown(ids: [GestureTouchID], starts: [GestureTouchID: CGPoint], startTime: TimeInterval)
    case scrolling(ids: [GestureTouchID], last: [GestureTouchID: CGPoint])
    /// Se soltó un tap válido; esperando doubleTapWindow por un segundo tap o un re-apoyo (drag).
    case tapCandidateReleased(deadline: TimeInterval)
    /// Bajó un segundo dedo dentro de dragHoldWindow tras un tap: puede terminar en drag o en otro click.
    case waitingSecondTouch(id: GestureTouchID, start: CGPoint, deadline: TimeInterval)
    case dragging(id: GestureTouchID, last: CGPoint)
}

/// Máquina de estados de gestos (F-05, F-06, F-07). El movimiento de 1 dedo
/// (F-04) también pasa por acá para poder distinguirlo de un tap.
///
/// Impulsado externamente: `touchesBegan/Moved/Ended/Cancelled` para eventos
/// reales, y `tick(now:)` (llamado periódicamente, p.ej. desde un
/// CADisplayLink) para resolver ventanas de tiempo cuando no llega ningún
/// touch nuevo. Sin esto último, `tapCandidateReleased`/`waitingSecondTouch`/
/// "hold to drag" nunca vencerían por sí solos.
final class GestureEngine {
    var config = GestureConfig()
    var tapToDragEnabled = true
    var onIntent: ((GestureIntent) -> Void)?

    private var state: EngineState = .idle

    func touchesBegan(_ touches: [(id: GestureTouchID, location: CGPoint)], now: TimeInterval) {
        guard !touches.isEmpty else { return }
        switch state {
        case .idle:
            beginFresh(touches: touches, now: now)

        case .touching(let existingId, let existingStart, _):
            // Bajó un segundo dedo mientras había uno: regla 5, cualquier
            // cambio de cantidad de dedos resetea (salvo dragging). UIKit solo
            // entrega el touch NUEVO acá — hay que sumarle el que ya veníamos
            // trackeando para que el gesto de 2 dedos tenga ambos puntos.
            beginFresh(touches: [(existingId, existingStart)] + touches, now: now)

        case .moving(let existingId, let existingLast):
            beginFresh(touches: [(existingId, existingLast)] + touches, now: now)

        case .tapCandidateReleased:
            if touches.count == 1 {
                let t = touches[0]
                state = .waitingSecondTouch(id: t.id, start: t.location, deadline: now + config.dragHoldWindow)
            } else {
                state = .idle
            }

        case .waitingSecondTouch, .twoFingerDown, .scrolling, .dragging:
            break // gesto en curso: ignorar dedos extra
        }
    }

    func touchesMoved(_ touches: [(id: GestureTouchID, location: CGPoint)], now: TimeInterval) {
        switch state {
        case .touching(let id, let start, _):
            guard let t = find(id, in: touches) else { return }
            if distance(start, t.location) > config.tapMaxMovement {
                onIntent?(.move(dx: Double(t.location.x - start.x), dy: Double(t.location.y - start.y)))
                state = .moving(id: id, last: t.location)
            }

        case .moving(let id, let last):
            guard let t = find(id, in: touches) else { return }
            onIntent?(.move(dx: Double(t.location.x - last.x), dy: Double(t.location.y - last.y)))
            state = .moving(id: id, last: t.location)

        case .waitingSecondTouch(let id, let start, let deadline):
            guard let t = find(id, in: touches) else { return }
            if tapToDragEnabled, distance(start, t.location) > config.tapMaxMovement {
                onIntent?(.hapticMedium)
                onIntent?(.dragStart)
                // El delta que cruzó el umbral también se manda: si no, el
                // primer tramo del arrastre se pierde (queda como "salto muerto").
                onIntent?(.dragMove(dx: Double(t.location.x - start.x), dy: Double(t.location.y - start.y)))
                state = .dragging(id: id, last: t.location)
            } else {
                state = .waitingSecondTouch(id: id, start: start, deadline: deadline)
            }

        case .dragging(let id, let last):
            guard let t = find(id, in: touches) else { return }
            onIntent?(.dragMove(dx: Double(t.location.x - last.x), dy: Double(t.location.y - last.y)))
            state = .dragging(id: id, last: t.location)

        case .twoFingerDown(let ids, let starts, let startTime):
            let currents = touches.filter { ids.contains($0.id) }
            let moved = currents.contains { t in
                guard let start = starts[t.id] else { return false }
                return distance(start, t.location) > config.tapMaxMovement
            }
            if moved {
                // Mismo cuidado que en el drag: el delta que cruzó el umbral
                // también cuenta, si no el primer tramo del scroll se pierde.
                var sumDx = 0.0
                var sumDy = 0.0
                var count = 0.0
                var last: [GestureTouchID: CGPoint] = starts
                for t in currents {
                    if let start = starts[t.id] {
                        sumDx += Double(t.location.x - start.x)
                        sumDy += Double(t.location.y - start.y)
                        count += 1
                    }
                    last[t.id] = t.location
                }
                if count > 0 {
                    onIntent?(.scroll(dx: sumDx / count, dy: sumDy / count))
                }
                state = .scrolling(ids: ids, last: last)
            } else {
                state = .twoFingerDown(ids: ids, starts: starts, startTime: startTime)
            }

        case .scrolling(let ids, var last):
            let relevant = touches.filter { ids.contains($0.id) }
            guard !relevant.isEmpty else { return }
            var sumDx = 0.0
            var sumDy = 0.0
            var count = 0.0
            for t in relevant {
                if let prev = last[t.id] {
                    sumDx += Double(t.location.x - prev.x)
                    sumDy += Double(t.location.y - prev.y)
                    count += 1
                }
                last[t.id] = t.location
            }
            if count > 0 {
                onIntent?(.scroll(dx: sumDx / count, dy: sumDy / count))
            }
            state = .scrolling(ids: ids, last: last)

        case .idle, .tapCandidateReleased:
            break
        }
    }

    func touchesEnded(_ endedIDs: [GestureTouchID], now: TimeInterval) {
        guard !endedIDs.isEmpty else { return }
        switch state {
        case .touching(let id, _, let startTime):
            guard endedIDs.contains(id) else { return }
            if now - startTime <= config.tapMaxDuration {
                onIntent?(.hapticLight)
                onIntent?(.click)
                state = .tapCandidateReleased(deadline: now + config.doubleTapWindow)
            } else {
                state = .idle
            }

        case .moving(let id, _):
            if endedIDs.contains(id) { state = .idle }

        case .twoFingerDown(let ids, _, let startTime):
            guard ids.allSatisfy(endedIDs.contains) else { return }
            if now - startTime <= config.tapMaxDuration {
                onIntent?(.hapticMedium)
                onIntent?(.rightClick)
            }
            state = .idle

        case .scrolling(let ids, _):
            if ids.allSatisfy(endedIDs.contains) { state = .idle }

        case .waitingSecondTouch(let id, _, _):
            guard endedIDs.contains(id) else { return }
            // Se soltó sin cruzar el umbral de movimiento: segundo tap válido.
            // (Si tapToDrag está desactivado, este es el único desenlace posible.)
            onIntent?(.hapticLight)
            onIntent?(.click)
            state = .tapCandidateReleased(deadline: now + config.doubleTapWindow)

        case .dragging(let id, _):
            guard endedIDs.contains(id) else { return }
            onIntent?(.dragEnd)
            state = .idle

        case .idle, .tapCandidateReleased:
            break
        }
    }

    func touchesCancelled(_ cancelledIDs: [GestureTouchID], now: TimeInterval) {
        if case .dragging = state {
            onIntent?(.dragEnd)
        }
        state = .idle
    }

    /// Llamar periódicamente (p.ej. junto con el CADisplayLink de MotionChannel)
    /// para resolver ventanas de tiempo cuando no llega ningún touch nuevo.
    func tick(now: TimeInterval) {
        switch state {
        case .tapCandidateReleased(let deadline):
            if now >= deadline { state = .idle }

        case .waitingSecondTouch(_, _, let deadline):
            if now >= deadline { state = .idle } // el click ya se mandó en touchesEnded

        case .touching(let id, let start, let startTime):
            if now - startTime >= config.holdToDragDuration {
                onIntent?(.hapticMedium)
                onIntent?(.dragStart)
                state = .dragging(id: id, last: start)
            }

        default:
            break
        }
    }

    // MARK: - helpers

    private func beginFresh(touches: [(id: GestureTouchID, location: CGPoint)], now: TimeInterval) {
        if touches.count == 1 {
            let t = touches[0]
            state = .touching(id: t.id, start: t.location, startTime: now)
        } else {
            var starts: [GestureTouchID: CGPoint] = [:]
            var ids: [GestureTouchID] = []
            for t in touches.prefix(2) {
                starts[t.id] = t.location
                ids.append(t.id)
            }
            state = .twoFingerDown(ids: ids, starts: starts, startTime: now)
        }
    }

    private func find(_ id: GestureTouchID, in touches: [(id: GestureTouchID, location: CGPoint)]) -> (id: GestureTouchID, location: CGPoint)? {
        touches.first { $0.id == id }
    }

    private func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        hypot(a.x - b.x, a.y - b.y)
    }
}
