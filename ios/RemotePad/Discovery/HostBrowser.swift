import Combine
import Network
import os.log

/// Envuelve NWBrowser para descubrir hosts RemotePad en la LAN (F-01).
///
/// NOTA: el manejo de "permiso de red local denegado" (`permissionDenied`)
/// se basa en que el browser queda indefinidamente en `.waiting` sin pasar
/// nunca a `.ready`. No se encontró en esta sesión (sin acceso confiable a
/// la documentación de Apple) un código de error específico y documentado
/// para "Local Network permission denied" — verificar en dispositivo real
/// durante S-06 y ajustar si iOS expone algo más preciso.
@MainActor
final class HostBrowser: ObservableObject {
    @Published private(set) var hosts: [DiscoveredHost] = []
    @Published private(set) var permissionDenied = false

    private var browser: NWBrowser?
    private var waitingTask: Task<Void, Never>?

    static let serviceType = "_remotepad._tcp"

    func start() {
        stop()

        let parameters = NWParameters()
        parameters.includePeerToPeer = false

        let browser = NWBrowser(
            for: .bonjour(type: Self.serviceType, domain: nil),
            using: parameters
        )
        self.browser = browser

        browser.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            Task { @MainActor in
                switch state {
                case .ready:
                    self.permissionDenied = false
                case .waiting:
                    // Esperar unos segundos antes de asumir que es un permiso
                    // denegado: al arrancar, `waiting` también aparece mientras
                    // se resuelve la interfaz de red normalmente.
                    self.scheduleWaitingCheck()
                case .failed, .cancelled:
                    break
                case .setup:
                    break
                @unknown default:
                    break
                }
            }
        }

        browser.browseResultsChangedHandler = { [weak self] results, _ in
            guard let self else { return }
            let parsed = results.compactMap { DiscoveredHost(result: $0) }
                .sorted { $0.name < $1.name }
            Task { @MainActor in
                self.hosts = parsed
            }
        }

        browser.start(queue: .main)
    }

    func stop() {
        waitingTask?.cancel()
        waitingTask = nil
        browser?.cancel()
        browser = nil
        hosts = []
        permissionDenied = false
    }

    private func scheduleWaitingCheck() {
        waitingTask?.cancel()
        waitingTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard let self, !Task.isCancelled else { return }
            if case .waiting = self.browser?.state {
                self.permissionDenied = true
            }
        }
    }
}
