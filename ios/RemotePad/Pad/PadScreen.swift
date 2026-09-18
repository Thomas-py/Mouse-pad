import Combine
import Network
import SwiftUI
import UIKit

/// Estado de conexión para la barra fina de F-03: verde conectado, amarillo
/// reconectando, rojo sin conexión.
enum ConnectionStatus: Equatable {
    case connecting
    case connected
    case reconnecting
    case disconnected
}

struct DebugStats: Equatable {
    var rttMillis: Double?
    var packetsPerSecond: Double = 0
}

/// Abre la sesión completa contra un host ya emparejado: handshake TCP
/// (hello/auth) + canal UDP de movimiento, traduce `GestureIntent` a
/// mensajes reales, y mantiene la sesión viva con ping/pong + reconexión
/// automática con backoff (F-03, S-15).
///
/// Esta orquestación no tenía una story propia asignada explícitamente —
/// sin ella PadView quedaría inalcanzable desde la UI. Se agrega en S-10 y
/// se extiende en S-11 (gestos), S-14 (ajustes) y acá (reconexión/debug).
@MainActor
final class PadSession: ObservableObject {
    enum State: Equatable {
        case connecting
        case connected
        case failed(String)
    }

    private static let pingInterval: TimeInterval = 2.0
    private static let maxMissedPings = 3
    private static let backoffSteps: [TimeInterval] = [0.5, 1, 2, 4]

    @Published private(set) var state: State = .connecting
    @Published private(set) var connectionStatus: ConnectionStatus = .connecting
    @Published private(set) var debugStats = DebugStats()

    private let host: DiscoveredHost
    private let settings: SettingsStore
    private let controlChannel = ControlChannel()
    private let motionChannel = MotionChannel()
    private var filter = MotionFilter()
    private var messageCounter = 0
    private var cancellables: Set<AnyCancellable> = []

    private var token: Data?
    private var sessionId: String?
    private var hapticLight: UIImpactFeedbackGenerator?
    private var hapticMedium: UIImpactFeedbackGenerator?

    private var listenTask: Task<Void, Never>?
    private var pingTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var missedPings = 0
    private var lastPingSentAt: TimeInterval?
    private var backoffIndex = 0
    private var isPadVisible = false
    private var lastPacketSampleCount = 0
    private var statsTimerTask: Task<Void, Never>?

    init(host: DiscoveredHost, settings: SettingsStore = .shared) {
        self.host = host
        self.settings = settings
    }

    // MARK: - ciclo de vida desde la vista

    func onAppear() {
        isPadVisible = true
        backoffIndex = 0
        Task { await connect() }
    }

    func onDisappear() {
        isPadVisible = false
        teardown()
    }

    func enterBackground() {
        // F-03: al ir a background, cerrar sockets.
        teardown()
    }

    func enterForeground() {
        guard isPadVisible else { return }
        backoffIndex = 0
        Task { await connect() }
    }

    // MARK: - conexión

    private func connect() async {
        state = .connecting
        connectionStatus = .connecting

        guard let token = TokenKeychain.load(forHostId: host.id) else {
            state = .failed("no emparejado")
            connectionStatus = .disconnected
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
                await handleConnectionFailure("handshake inválido")
                return
            }

            let sig = Signer.authSig(token: token, nonceServer: nonceServer, nonceClient: nonceClient)
            try await controlChannel.send(AuthMessage(id: nextId(), clientId: clientId, sig: sig))

            guard case .authOk(let authOk) = try await controlChannel.receiveMessage() else {
                await handleConnectionFailure("auth rechazado")
                return
            }
            sessionId = authOk.session
            try? await sendInitialCfg()
            observeNaturalScrollChanges()

            guard let udpPort = NWEndpoint.Port(rawValue: host.udpPort),
                  let remoteHost = controlChannel.resolvedRemoteHost
            else {
                await handleConnectionFailure("no se pudo resolver la IP del host")
                return
            }

            motionChannel.token = token
            motionChannel.clientId = clientId
            motionChannel.connect(to: .hostPort(host: NWEndpoint.Host(remoteHost), port: udpPort))

            hapticLight = UIImpactFeedbackGenerator(style: .light)
            hapticMedium = UIImpactFeedbackGenerator(style: .medium)

            backoffIndex = 0
            missedPings = 0
            state = .connected
            connectionStatus = .connected

            startListenLoop()
            startPingLoop()
            startStatsSampling()
        } catch {
            await handleConnectionFailure("\(error)")
        }
    }

    /// F-03: reconexión automática con backoff 0.5s -> 1s -> 2s -> 4s (máx),
    /// solo mientras el Pad siga visible.
    private func handleConnectionFailure(_ reason: String) async {
        // Importante: cerrar la conexión vieja ANTES de agendar el reintento.
        // Sin esto, connect() abre un NWConnection nuevo sin haber cancelado
        // el anterior (fuga + estado stale en ControlChannel).
        cleanupConnections()

        state = .failed(reason)
        connectionStatus = isPadVisible ? .reconnecting : .disconnected
        guard isPadVisible else { return }

        let delay = Self.backoffSteps[min(backoffIndex, Self.backoffSteps.count - 1)]
        backoffIndex = min(backoffIndex + 1, Self.backoffSteps.count - 1)

        reconnectTask?.cancel()
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard let self, !Task.isCancelled, self.isPadVisible else { return }
            await self.connect()
        }
    }

    /// Cancela las tareas en curso y cierra los canales, sin tocar `reconnectTask`
    /// (lo maneja cada llamador según si quiere agendar un reintento o no).
    private func cleanupConnections() {
        listenTask?.cancel()
        listenTask = nil
        pingTask?.cancel()
        pingTask = nil
        statsTimerTask?.cancel()
        statsTimerTask = nil
        cancellables.removeAll()
        motionChannel.disconnect()
        controlChannel.disconnect()
    }

    /// Cierre completo y definitivo: además de `cleanupConnections()`, cancela
    /// cualquier reintento agendado. F-03: al ir a background también se usa
    /// esto — `enterBackground()` no toca `isPadVisible`, así que un reintento
    /// que quedara vivo podría reconectar mientras la app está atrás.
    private func teardown() {
        reconnectTask?.cancel()
        reconnectTask = nil
        cleanupConnections()
    }

    // MARK: - ping/pong y RTT

    private func startListenLoop() {
        listenTask?.cancel()
        listenTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let message = try await self.controlChannel.receiveMessage()
                    await self.handleIncoming(message)
                } catch {
                    // Si la tarea ya fue cancelada (teardown() deliberado, p.ej.
                    // al ir a background), no es una desconexión inesperada —
                    // no hay que disparar el backoff de reconexión.
                    guard !Task.isCancelled else { return }
                    await self.handleConnectionFailure("conexión perdida")
                    return
                }
            }
        }
    }

    private func handleIncoming(_ message: IncomingMessage) async {
        guard case .pong(let pong) = message else { return }
        missedPings = 0
        guard lastPingSentAt != nil else { return }
        let rtt = (Date().timeIntervalSince1970 * 1000) - Double(pong.ts)
        debugStats.rttMillis = max(0, rtt)
    }

    private func startPingLoop() {
        pingTask?.cancel()
        pingTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(Self.pingInterval * 1_000_000_000))
                guard !Task.isCancelled else { return }
                await self.sendPingAndCheckTimeout()
            }
        }
    }

    private func sendPingAndCheckTimeout() async {
        guard let token, let sessionId else { return }

        if missedPings >= Self.maxMissedPings {
            await handleConnectionFailure("sin respuesta del servidor")
            return
        }

        let id = nextId()
        let ts = Int64(Date().timeIntervalSince1970 * 1000)
        let sig = Signer.messageSig(token: token, session: sessionId, id: id, type: "ping")
        lastPingSentAt = Date().timeIntervalSince1970
        missedPings += 1
        try? await controlChannel.send(PingMessage(id: id, sig: sig, ts: ts))
    }

    // MARK: - debug stats (F-09 showDebug)

    private func startStatsSampling() {
        statsTimerTask?.cancel()
        lastPacketSampleCount = 0
        statsTimerTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                guard !Task.isCancelled else { return }
                let current = self.motionChannel.sentDatagramCount
                self.debugStats.packetsPerSecond = Double(current - self.lastPacketSampleCount)
                self.lastPacketSampleCount = current
            }
        }
    }

    // MARK: - gestos -> red

    func configure(_ engine: GestureEngine) {
        engine.tapToDragEnabled = settings.tapToDrag
    }

    func handleIntent(_ intent: GestureIntent) {
        applyLiveFilterSettings()
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
            if settings.hapticsEnabled { hapticLight?.impactOccurred() }
        case .hapticMedium:
            if settings.hapticsEnabled { hapticMedium?.impactOccurred() }
        }
    }

    private func applyLiveFilterSettings() {
        filter.sensitivity = settings.sensitivity
        filter.acceleration = settings.acceleration
    }

    private func sendInitialCfg() async throws {
        guard let token, let sessionId else { return }
        let id = nextId()
        let sig = Signer.messageSig(token: token, session: sessionId, id: id, type: "cfg")
        try await controlChannel.send(CfgMessage(id: id, sig: sig, naturalScroll: settings.naturalScroll))
    }

    private func observeNaturalScrollChanges() {
        settings.$naturalScroll
            .dropFirst() // el valor inicial ya se mandó en sendInitialCfg()
            .sink { [weak self] value in
                self?.sendCfg(naturalScroll: value)
            }
            .store(in: &cancellables)
    }

    private func sendCfg(naturalScroll: Bool) {
        guard let token, let sessionId else { return }
        let id = nextId()
        let sig = Signer.messageSig(token: token, session: sessionId, id: id, type: "cfg")
        Task {
            try? await controlChannel.send(CfgMessage(id: id, sig: sig, naturalScroll: naturalScroll))
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
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var settings = SettingsStore.shared

    init(host: DiscoveredHost) {
        self.host = host
        _session = StateObject(wrappedValue: PadSession(host: host))
    }

    var body: some View {
        ZStack(alignment: .top) {
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
                    Text(session.connectionStatus == .reconnecting ? "Reconectando..." : "No se pudo conectar")
                        .font(.headline)
                    Text(reason).foregroundStyle(.secondary)
                }
                .padding()
            }

            statusBar

            if settings.showDebug {
                debugOverlay
            }
        }
        .statusBarHidden(session.state == .connected)
        .task {
            UIApplication.shared.isIdleTimerDisabled = true
            session.onAppear()
        }
        .onDisappear {
            UIApplication.shared.isIdleTimerDisabled = false
            session.onDisappear()
        }
        .onChange(of: scenePhase) { newPhase in
            switch newPhase {
            case .active:
                session.enterForeground()
            case .background:
                session.enterBackground()
            default:
                break
            }
        }
    }

    /// F-03: barra fina de 4pt — verde conectado, amarillo reconectando,
    /// rojo sin conexión. Sin texto salvo amarillo/rojo (ya cubierto arriba).
    private var statusBar: some View {
        Rectangle()
            .fill(color(for: session.connectionStatus))
            .frame(height: 4)
            .ignoresSafeArea(edges: .top)
    }

    private func color(for status: ConnectionStatus) -> Color {
        switch status {
        case .connected: return .green
        case .connecting, .reconnecting: return .yellow
        case .disconnected: return .red
        }
    }

    private var debugOverlay: some View {
        VStack(alignment: .trailing, spacing: 2) {
            if let rtt = session.debugStats.rttMillis {
                Text("RTT: \(Int(rtt)) ms")
            } else {
                Text("RTT: --")
            }
            Text("pps: \(Int(session.debugStats.packetsPerSecond))")
        }
        .font(.caption.monospacedDigit())
        .foregroundStyle(.white)
        .padding(6)
        .background(.black.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
        .padding(.top, 12)
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.trailing, 8)
    }
}
