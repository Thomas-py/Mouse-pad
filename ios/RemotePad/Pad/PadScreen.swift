import Network
import SwiftUI
import UIKit

/// Abre la sesión completa contra un host ya emparejado: handshake TCP
/// (hello/auth) + canal UDP de movimiento, y muestra el PadView (F-03, F-04).
///
/// Esta orquestación no tenía una story propia asignada explícitamente —
/// sin ella PadView quedaría inalcanzable desde la UI. Se agrega acá (S-10)
/// como la integración mínima necesaria para que la story sea usable.
/// F-03 completo (barra verde/amarillo/rojo, reconexión con backoff) es
/// S-15 — acá hay solo un estado fijo mientras la sesión sigue viva.
@MainActor
final class PadSession: ObservableObject {
    enum State: Equatable {
        case connecting
        case connected
        case failed(String)
    }

    @Published private(set) var state: State = .connecting

    private let host: DiscoveredHost
    private let controlChannel = ControlChannel()
    private let motionChannel = MotionChannel()
    private var filter = MotionFilter()
    private var messageCounter = 0

    init(host: DiscoveredHost) {
        self.host = host
    }

    func start() async {
        guard let token = TokenKeychain.load(forHostId: host.id) else {
            state = .failed("no emparejado")
            return
        }

        do {
            try await controlChannel.connect(to: host.endpoint)

            let nonceClient = Signer.randomBytes(16)
            let clientId = ClientIdentity.current
            try await controlChannel.send(
                HelloMessage(id: nextId(), v: 1, clientId: clientId, nonce: nonceClient.hexEncoded)
            )

            guard case .helloOk(let helloOk) = try await controlChannel.receiveMessage(),
                  let nonceServer = Data(hex: helloOk.nonce)
            else {
                state = .failed("handshake inválido")
                return
            }

            let sig = Signer.authSig(token: token, nonceServer: nonceServer, nonceClient: nonceClient)
            try await controlChannel.send(AuthMessage(id: nextId(), clientId: clientId, sig: sig))

            guard case .authOk = try await controlChannel.receiveMessage() else {
                state = .failed("auth rechazado")
                return
            }

            guard let udpPort = NWEndpoint.Port(rawValue: host.udpPort),
                  let remoteHost = controlChannel.resolvedRemoteHost
            else {
                state = .failed("no se pudo resolver la IP del host")
                return
            }

            motionChannel.token = token
            motionChannel.clientId = clientId
            motionChannel.connect(to: .hostPort(host: NWEndpoint.Host(remoteHost), port: udpPort))

            state = .connected
        } catch {
            state = .failed("\(error)")
        }
    }

    func stop() {
        motionChannel.disconnect()
        controlChannel.disconnect()
    }

    func handleMove(dx: Double, dy: Double) {
        let (fx, fy) = filter.apply(dx: dx, dy: dy)
        if fx != 0 || fy != 0 {
            motionChannel.addMove(dx: fx, dy: fy)
        }
    }

    private func nextId() -> String {
        messageCounter += 1
        return "m\(messageCounter)"
    }
}

struct PadScreen: View {
    let host: DiscoveredHost
    @StateObject private var session: PadSession
    @Environment(\.dismiss) private var dismiss

    init(host: DiscoveredHost) {
        self.host = host
        _session = StateObject(wrappedValue: PadSession(host: host))
    }

    var body: some View {
        ZStack {
            switch session.state {
            case .connecting:
                ProgressView("Conectando...")
            case .connected:
                PadView(onMove: session.handleMove, onExit: { dismiss() })
                    .ignoresSafeArea()
            case .failed(let reason):
                VStack(spacing: 12) {
                    Text("No se pudo conectar").font(.headline)
                    Text(reason).foregroundStyle(.secondary)
                }
                .padding()
            }
        }
        .statusBarHidden(session.state == .connected)
        .task {
            UIApplication.shared.isIdleTimerDisabled = true
            await session.start()
        }
        .onDisappear {
            UIApplication.shared.isIdleTimerDisabled = false
            session.stop()
        }
    }
}
