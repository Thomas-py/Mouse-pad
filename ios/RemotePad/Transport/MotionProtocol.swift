import CryptoKit
import Foundation

/// Codec binario del canal de movimiento — espejo exacto de
/// server/remotepad_server/protocol.py (docs/02-PROTOCOLO.md §3).
enum MotionEventKind: UInt8 {
    case move = 0x01
    case scroll = 0x02
}

struct MotionEvent {
    let kind: MotionEventKind
    let dx: Int16
    let dy: Int16
}

enum MotionDatagramEncoder {
    static let magic: [UInt8] = [0x52, 0x50]
    static let version: UInt8 = 1
    static let maxEventsPerDatagram = 32
    static let maxDatagramBytes = 512

    static func clientHash(_ clientId: String) -> Data {
        Data(SHA256.hash(data: Data(clientId.utf8)).prefix(8))
    }

    /// Puede devolver nil si hay más de `maxEventsPerDatagram` eventos o el
    /// datagrama superaría `maxDatagramBytes` (no debería pasar en la práctica).
    static func encode(clientId: String, seq: UInt32, token: Data, events: [MotionEvent]) -> Data? {
        guard !events.isEmpty, events.count <= maxEventsPerDatagram else { return nil }

        var header = Data(magic)
        header.append(version)
        header.append(UInt8(events.count))
        withUnsafeBytes(of: seq.bigEndian) { header.append(contentsOf: $0) }
        header.append(clientHash(clientId))

        var eventsData = Data()
        eventsData.reserveCapacity(events.count * 6)
        for event in events {
            eventsData.append(event.kind.rawValue)
            eventsData.append(0) // flags, reservado
            withUnsafeBytes(of: event.dx.bigEndian) { eventsData.append(contentsOf: $0) }
            withUnsafeBytes(of: event.dy.bigEndian) { eventsData.append(contentsOf: $0) }
        }

        let sig = Signer.udpSig(token: token, headerPrefix: header, eventsData: eventsData)
        let datagram = header + sig + eventsData
        guard datagram.count <= maxDatagramBytes else { return nil }
        return datagram
    }
}
