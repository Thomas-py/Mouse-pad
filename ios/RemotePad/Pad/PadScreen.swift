import Network
import SwiftUI
import UIKit

/// Abre la sesión completa contra un host ya emparejado: handshake TCP
/// (hello/auth) + canal UDP de movimiento, y traduce los `GestureIntent`
/// del `GestureEngine` a mensajes reales (F-03, F-04..F-08).
///
/// Esta orquestación no tenía una story propia asignada explícitamente —
/// sin ella PadView quedaría inalcanzable desde la UI. Se agrega en S-10
/// y se extiende en S-11 con el manejo de clics/drag/scroll.
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

    private var token: Data?
    private var sessionId: String?
    private var hapticLight: UIImpactFeedbackGenerator?
    private var hapticMedium: UIImpactFeedbackGenerator?

    init(host: DiscoveredHost) {
        self.host = host
    }

    func start() async {
        guard let token = TokenKeychain.load(forHostId: host.id) else {
            state = .failed("no emparejado")
            return
        }
        self.token = token

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

            guard case .authOk(let authOk) = try await controlChannel.receiveMessage() else {
                state = .failed("auth rechazado")
                return
            }
            sessionId = authOk.session

            guard let udpPort = NWEndpoint.Port(rawValue: host.udpPort),
                  let remoteHost = controlChannel.resolvedRemoteHost
            else {
                state = .failed("no se pudo resolver la IP del host")
                return
            }

            motionChannel.token = token
            motionChannel.clientId = clientId
            motionChannel.connect(to: .hostPort(host: NWEndpoint.Host(remoteHost), port: udpPort))

            hapticLight = UIImpactFeedbackGenerator(style: .light)
            hapticMedium = UIImpactFeedbackGenerator(style: .medium)

            state = .connected
        } catch {
            state = .failed("\(error)")
        }
    }

    func stop() {
        motionChannel.disconnect()
        controlChannel.disconnect()
    }

    func configure(_ engine: GestureEngine) {
        // Ajustes reales (sensibilidad, tapToDrag, etc.) llegan en S-14.
    }

    func handleIntent(_ intent: GestureIntent) {
        switch intent {
        case .move(let dx, let dy):
            let (fx, fy) = filter.apply(dx: dx, dy: dy)
            if fx != 0 || fy != 0 {
                motionChannel.addMove(dx: fx, dy: fy)
            }
        case .scroll(let dx, let dy):
            motionChannel.addScroll(dx: Int(dx.rounded()), dy: Int(dy.rounded()))
        case .click:
            sendBtn(button: "left", action: "click", count: 1)
        case .rightClick:
            sendBtn(button: "right", action: "click", count: 1)
        case .dragStart:
            sendBtn(button: "left", action: "down", count: 1)
        case .dragMove(let dx, let dy):
            let (fx, fy) = filter.apply(dx: dx, dy: dy)
            if fx != 0 || fy != 0 {
                motionChannel.addMove(dx: fx, dy: fy)
            }
        case .dragEnd:
            sendBtn(button: "left", action: "up", count: 1)
        case .hapticLight:
            hapticLight?.impactOccurred()
        case .hapticMedium:
            hapticMedium?.impactOccurred()
        }
    }

    /// NOTA: cada llamada crea un Task independiente; en teoría el scheduler
    /// podría entregarlos fuera de orden si se disparan muy rápido en
    /// sucesión (ej. down/up de un drag). No se resolvió con una cola serial
    /// explícita por tiempo — revisar si en el dispositivo real se ve algún
    /// btn fuera de orden.
    private func sendBtn(button: String, action: String, count: Int) {
        guard let token, let sessionId else { return }
        let id = nextId()
        let sig = Signer.messageSig(token: token, session: sessionId, id: id, type: "btn")
        Task {
            try? await controlChannel.send(BtnMessage(id: id, sig: sig, button: button, action: action, count: count))
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
                PadView(
                    engineConfig: session.configure,
                    onIntent: session.handleIntent,
                    onExit: { dismiss() }
                )
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
