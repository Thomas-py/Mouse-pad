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

    /// Constructor directo (no via Bonjour) — usado solo por `manual(ip:)`.
    private init(id: String, name: String, os: String, protocolVersion: Int, udpPort: UInt16, endpoint: NWEndpoint) {
        self.id = id
        self.name = name
        self.os = os
        self.protocolVersion = protocolVersion
        self.udpPort = udpPort
        self.endpoint = endpoint
    }

    /// Fallback cuando el router no deja pasar el multicast de mDNS (pasa en
    /// algunos routers de ISP, ver docs/00-CONTEXTO.md §4bis): conectar
    /// directo por IP, sin descubrimiento. Asume los puertos default del
    /// servidor (52100 TCP / 52101 UDP, docs/02-PROTOCOLO.md) — si se
    /// arrancó `remotepad-server` con `--port`/`--udp-port` distintos, esto
    /// no alcanza.
    static func manual(ip: String, port: UInt16 = 52100, udpPort: UInt16 = 52101) -> DiscoveredHost? {
        let trimmed = ip.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let nwPort = NWEndpoint.Port(rawValue: port) else { return nil }
        return DiscoveredHost(
            id: "manual:\(trimmed):\(port)",
            name: trimmed,
            os: "unknown",
            protocolVersion: 1,
            udpPort: udpPort,
            endpoint: .hostPort(host: NWEndpoint.Host(trimmed), port: nwPort)
        )
    }
}
