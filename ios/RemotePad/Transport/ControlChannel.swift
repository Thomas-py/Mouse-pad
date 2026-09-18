import Foundation
import Network

/// Canal de control TCP, framing NDJSON (docs/02-PROTOCOLO.md §2: una línea
/// JSON por mensaje, terminada en `\n`). Uso estrictamente request/response
/// en esta story (S-08): un `send` seguido de un `receiveMessage`. No hay
/// reconexión automática ni escucha en paralelo — eso es S-15.
final class ControlChannel {
    enum ChannelError: Error {
        case notConnected
        case connectionFailed(NWError)
        case connectionClosed
    }

    private var connection: NWConnection?
    private var buffer = Data()
    private var pendingLine: CheckedContinuation<Data, Error>?

    func connect(to endpoint: NWEndpoint) async throws {
        let connection = NWConnection(to: endpoint, using: .tcp)
        self.connection = connection

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            var resumed = false
            connection.stateUpdateHandler = { state in
                guard !resumed else { return }
                switch state {
                case .ready:
                    resumed = true
                    continuation.resume()
                case .failed(let error):
                    resumed = true
                    continuation.resume(throwing: ChannelError.connectionFailed(error))
                case .cancelled:
                    resumed = true
                    continuation.resume(throwing: ChannelError.notConnected)
                default:
                    break
                }
            }
            connection.start(queue: .main)
        }

        scheduleReceive()
    }

    func disconnect() {
        connection?.cancel()
        connection = nil
        buffer.removeAll()
        failPending(ChannelError.connectionClosed)
    }

    func send<T: Encodable>(_ message: T) async throws {
        guard let connection else { throw ChannelError.notConnected }
        var data = try JSONEncoder().encode(message)
        data.append(0x0A)
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            connection.send(
                content: data,
                completion: .contentProcessed { error in
                    if let error {
                        continuation.resume(throwing: ChannelError.connectionFailed(error))
                    } else {
                        continuation.resume()
                    }
                }
            )
        }
    }

    func receiveMessage() async throws -> IncomingMessage {
        let line = try await receiveLine()
        return try ControlProtocol.decode(line)
    }

    // MARK: - framing por líneas

    private func receiveLine() async throws -> Data {
        if let line = takeBufferedLine() {
            return line
        }
        return try await withCheckedThrowingContinuation { continuation in
            self.pendingLine = continuation
        }
    }

    private func takeBufferedLine() -> Data? {
        guard let newlineIndex = buffer.firstIndex(of: 0x0A) else { return nil }
        let line = buffer.subdata(in: buffer.startIndex..<newlineIndex)
        buffer.removeSubrange(buffer.startIndex...newlineIndex)
        return line
    }

    private func scheduleReceive() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self else { return }

            if let data, !data.isEmpty {
                self.buffer.append(data)
                if let continuation = self.pendingLine, let line = self.takeBufferedLine() {
                    self.pendingLine = nil
                    continuation.resume(returning: line)
                }
            }

            if let error {
                self.failPending(ChannelError.connectionFailed(error))
                return
            }
            if isComplete {
                self.failPending(ChannelError.connectionClosed)
                return
            }

            self.scheduleReceive()
        }
    }

    private func failPending(_ error: Error) {
        if let continuation = pendingLine {
            pendingLine = nil
            continuation.resume(throwing: error)
        }
    }
}
