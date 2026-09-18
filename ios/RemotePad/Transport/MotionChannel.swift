import Network
import QuartzCore

/// Agrupa deltas de movimiento/scroll a 120 Hz (`CADisplayLink`) y los manda
/// por UDP firmados (docs/02-PROTOCOLO.md §3). Sin heartbeat: si no hay
/// movimiento en un frame, no se manda nada (regla del protocolo).
///
/// Hereda de NSObject porque CADisplayLink usa target-action, que necesita
/// un objeto compatible con el runtime de Objective-C.
final class MotionChannel: NSObject {
    private var connection: NWConnection?
    private var displayLink: CADisplayLink?
    private var seq: UInt32 = 0

    private var pendingMoveDx = 0
    private var pendingMoveDy = 0
    private var pendingScrollDx = 0
    private var pendingScrollDy = 0
    private var hasPending = false

    var token: Data?
    var clientId: String?

    /// Total de datagramas mandados en esta conexión — S-15 lo muestrea cada
    /// 1s para el overlay de debug (paquetes/s, F-09).
    private(set) var sentDatagramCount = 0

    func connect(to endpoint: NWEndpoint) {
        disconnect()
        let connection = NWConnection(to: endpoint, using: .udp)
        self.connection = connection
        connection.start(queue: .main)
        startDisplayLink()
    }

    func disconnect() {
        stopDisplayLink()
        connection?.cancel()
        connection = nil
        seq = 0
        pendingMoveDx = 0
        pendingMoveDy = 0
        pendingScrollDx = 0
        pendingScrollDy = 0
        hasPending = false
        sentDatagramCount = 0
    }

    func addMove(dx: Int, dy: Int) {
        pendingMoveDx += dx
        pendingMoveDy += dy
        hasPending = true
    }

    func addScroll(dx: Int, dy: Int) {
        pendingScrollDx += dx
        pendingScrollDy += dy
        hasPending = true
    }

    private func startDisplayLink() {
        let link = CADisplayLink(target: self, selector: #selector(tick))
        link.preferredFramesPerSecond = 120
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    private func stopDisplayLink() {
        displayLink?.invalidate()
        displayLink = nil
    }

    @objc private func tick() {
        guard hasPending else { return }

        var events: [MotionEvent] = []
        if pendingMoveDx != 0 || pendingMoveDy != 0 {
            events.append(MotionEvent(kind: .move, dx: clamp(pendingMoveDx), dy: clamp(pendingMoveDy)))
        }
        if pendingScrollDx != 0 || pendingScrollDy != 0 {
            events.append(MotionEvent(kind: .scroll, dx: clamp(pendingScrollDx), dy: clamp(pendingScrollDy)))
        }

        pendingMoveDx = 0
        pendingMoveDy = 0
        pendingScrollDx = 0
        pendingScrollDy = 0
        hasPending = false

        guard !events.isEmpty, let token, let clientId, let connection else { return }

        seq = seq &+ 1
        guard let datagram = MotionDatagramEncoder.encode(clientId: clientId, seq: seq, token: token, events: events) else {
            return
        }
        sentDatagramCount += 1
        connection.send(content: datagram, completion: .contentProcessed { _ in })
    }

    private func clamp(_ value: Int) -> Int16 {
        Int16(clamping: value)
    }
}
