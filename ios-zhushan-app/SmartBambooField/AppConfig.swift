import Foundation

enum AppConfig {
    static let applicationURL: URL = {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: "SMART_BAMBOO_URL") as? String,
              let url = URL(string: raw), url.scheme == "https", url.host != nil else {
            preconditionFailure("SMART_BAMBOO_URL 必须是有效的 HTTPS 地址")
        }
        return url
    }()

    static func isTrusted(_ url: URL?) -> Bool {
        guard let url else { return false }
        return url.scheme == applicationURL.scheme && url.host == applicationURL.host && url.port == applicationURL.port
    }
}

