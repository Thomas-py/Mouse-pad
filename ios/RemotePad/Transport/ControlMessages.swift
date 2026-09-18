import Foundation

// Mensajes del canal de control — docs/02-PROTOCOLO.md §2.
// Espejo exacto de server/remotepad_server/protocol.py: cualquier cambio acá
// implica cambiar el doc primero, después ambos lados (00-CONTEXTO.md §8.3).

// MARK: - Cliente -> Servidor

struct HelloMessage: Encodable {
    let t = "hello"
    let id: String
    let v: Int
    let clientId: String
    let nonce: String

    enum CodingKeys: String, CodingKey {
        case t, id, v, nonce
        case clientId = "client_id"
    }
}

struct AuthMessage: Encodable {
    let t = "auth"
    let id: String
    let clientId: String
    let sig: String

    enum CodingKeys: String, CodingKey {
        case t, id, sig
        case clientId = "client_id"
    }
}

struct PairStartMessage: Encodable {
    let t = "pair_start"
    let id: String
    let v: Int
    let clientId: String
    let clientName: String
    let nonce: String

    enum CodingKeys: String, CodingKey {
        case t, id, v, nonce
        case clientId = "client_id"
        case clientName = "client_name"
    }
}

struct PairAnswerMessage: Encodable {
    let t = "pair_answer"
    let id: String
    let proof: String
}

struct BtnMessage: Encodable {
    let t = "btn"
    let id: String
    let sig: String
    let button: String   // "left" | "right" | "middle"
    let action: String   // "click" | "down" | "up"
    let count: Int
}

struct CfgMessage: Encodable {
    let t = "cfg"
    let id: String
    let sig: String
    let naturalScroll: Bool

    enum CodingKeys: String, CodingKey {
        case t, id, sig
        case naturalScroll = "natural_scroll"
    }
}

struct PingMessage: Encodable {
    let t = "ping"
    let id: String
    let sig: String
    let ts: Int64
}

// MARK: - Servidor -> Cliente

struct HelloOkMessage: Decodable {
    let re: String
    let nonce: String
    let serverName: String

    enum CodingKeys: String, CodingKey {
        case re, nonce
        case serverName = "server_name"
    }
}

struct ErrorMessage: Decodable {
    let re: String
    let code: String
}

struct AuthOkMessage: Decodable {
    let re: String
    let session: String
}

struct PairChallengeMessage: Decodable {
    let re: String
    let nonce: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case re, nonce
        case expiresIn = "expires_in"
    }
}

struct PairOkMessage: Decodable {
    let re: String
}

struct PongMessage: Decodable {
    let re: String
    let ts: Int64
}

// MARK: - Decodificación por tipo (`t`)

enum IncomingMessage {
    case helloOk(HelloOkMessage)
    case error(ErrorMessage)
    case authOk(AuthOkMessage)
    case pairChallenge(PairChallengeMessage)
    case pairOk(PairOkMessage)
    case pong(PongMessage)
}

enum ControlProtocolError: Error {
    case malformedEnvelope
    case unknownType(String)
    case decodeFailed(type: String, underlying: Error)
}

enum ControlProtocol {
    private struct Envelope: Decodable { let t: String }

    static func decode(_ data: Data) throws -> IncomingMessage {
        let decoder = JSONDecoder()
        guard let envelope = try? decoder.decode(Envelope.self, from: data) else {
            throw ControlProtocolError.malformedEnvelope
        }
        do {
            switch envelope.t {
            case "hello_ok":
                return .helloOk(try decoder.decode(HelloOkMessage.self, from: data))
            case "error":
                return .error(try decoder.decode(ErrorMessage.self, from: data))
            case "auth_ok":
                return .authOk(try decoder.decode(AuthOkMessage.self, from: data))
            case "pair_challenge":
                return .pairChallenge(try decoder.decode(PairChallengeMessage.self, from: data))
            case "pair_ok":
                return .pairOk(try decoder.decode(PairOkMessage.self, from: data))
            case "pong":
                return .pong(try decoder.decode(PongMessage.self, from: data))
            default:
                throw ControlProtocolError.unknownType(envelope.t)
            }
        } catch let error as ControlProtocolError {
            throw error
        } catch {
            throw ControlProtocolError.decodeFailed(type: envelope.t, underlying: error)
        }
    }
}
