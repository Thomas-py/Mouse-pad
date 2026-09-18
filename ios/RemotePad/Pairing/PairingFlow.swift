import Foundation
import UIKit

/// Orquesta el pairing completo (F-02): pair_start -> pantalla de PIN ->
/// pair_answer -> guardar token en Keychain. Ver docs/02-PROTOCOLO.md §2.2.
@MainActor
final class PairingFlow: ObservableObject {
    enum State: Equatable {
        case connecting
        case waitingForPin
        case verifying
        case paired
        case badPin
        case locked
        case failed(String)
    }

    @Published private(set) var state: State = .connecting

    private let host: DiscoveredHost
    private let channel: ControlChannel
    private let clientId: String
    private let clientName: String

    private var nonceClient: Data?
    private var nonceServer: Data?
    private var messageCounter = 0

    init(host: DiscoveredHost, channel: ControlChannel = ControlChannel(), clientName: String? = nil) {
        self.host = host
        self.channel = channel
        self.clientId = ClientIdentity.current
        self.clientName = clientName ?? UIDevice.current.name
    }

    func start() async {
        state = .connecting
        do {
            try await channel.connect(to: host.endpoint)

            let nonceClient = Signer.randomBytes(16)
            self.nonceClient = nonceClient

            try await channel.send(
                PairStartMessage(
                    id: nextId(),
                    v: 1,
                    clientId: clientId,
                    clientName: clientName,
                    nonce: nonceClient.hexEncoded
                )
            )

            switch try await channel.receiveMessage() {
            case .pairChallenge(let challenge):
                guard let serverNonce = Data(hex: challenge.nonce) else {
                    state = .failed("nonce inválido")
                    return
                }
                self.nonceServer = serverNonce
                state = .waitingForPin
            case .error(let err) where err.code == "locked":
                state = .locked
            case .error(let err):
                state = .failed(err.code)
            default:
                state = .failed("respuesta inesperada")
            }
        } catch {
            state = .failed("\(error)")
        }
    }

    func submit(pin: String) async {
        guard let nonceClient, let nonceServer else { return }
        state = .verifying
        do {
            let proof = Signer.pairProof(pin: pin, nonceServer: nonceServer, nonceClient: nonceClient)
            try await channel.send(PairAnswerMessage(id: nextId(), proof: proof))

            switch try await channel.receiveMessage() {
            case .pairOk:
                let token = Signer.deriveToken(pin: pin, nonceServer: nonceServer, nonceClient: nonceClient)
                try TokenKeychain.save(token: token, forHostId: host.id)
                state = .paired
            case .error(let err) where err.code == "locked":
                state = .locked
            case .error(let err) where err.code == "bad_pin":
                state = .badPin
            case .error(let err):
                state = .failed(err.code)
            default:
                state = .failed("respuesta inesperada")
            }
        } catch {
            state = .failed("\(error)")
        }
    }

    func cancel() {
        channel.disconnect()
    }

    private func nextId() -> String {
        messageCounter += 1
        return "p\(messageCounter)"
    }
}
