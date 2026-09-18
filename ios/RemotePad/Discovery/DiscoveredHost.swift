import Network

/// Host anunciado por Bonjour (`_remotepad._tcp`), parseado desde un
/// `NWBrowser.Result`. Ver docs/02-PROTOCOLO.md §1 para los campos TXT.
struct DiscoveredHost: Identifiable, Equatable {
    /// TXT "id": uuid4 persistente del host (no cambia entre reinicios del servidor).
    let id: String
    /// Nombre de instancia Bonjour (ej. "PC de Thomas").
    let name: String
    /// TXT "os": "windows" | "macos" | "linux".
    let os: String
    /// TXT "v": versión de protocolo.
    let protocolVersion: Int
    /// TXT "udp": puerto UDP de movimiento.
    let udpPort: UInt16
    /// Endpoint original, usado para abrir la conexión TCP de control.
    let endpoint: NWEndpoint

    init?(result: NWBrowser.Result) {
        guard case .service(let name, _, _, _) = result.endpoint else { return nil }
        guard case .bonjour(let txt) = result.metadata else { return nil }

        var values: [String: String] = [:]
        for (key, entry) in txt {
            if case .string(let value) = entry {
                values[key] = value
            }
        }

        guard
            let idValue = values["id"],
            let osValue = values["os"],
            let versionString = values["v"], let version = Int(versionString),
            let udpString = values["udp"], let udpValue = UInt16(udpString)
        else { return nil }

        self.id = idValue
        self.name = name
        self.os = osValue
        self.protocolVersion = version
        self.udpPort = udpValue
        self.endpoint = result.endpoint
    }

    static func == (lhs: DiscoveredHost, rhs: DiscoveredHost) -> Bool {
        lhs.id == rhs.id
    }
}
