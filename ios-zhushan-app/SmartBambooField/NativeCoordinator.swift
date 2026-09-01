import CoreLocation
import Foundation
import Network
import Security
import SafariServices
import UIKit
import WebKit

final class NativeCoordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, CLLocationManagerDelegate {
    static let bridgeScript = """
    (() => {
      let online = navigator.onLine;
      window.addEventListener('smart-bamboo-native:network', e => { online = !!e.detail?.online; });
      const post = (action, payload = {}) => window.webkit.messageHandlers.smartBambooNative.postMessage({action, ...payload});
      window.SmartBambooNative = {
        version: () => '1.0-ios', isOnline: () => online,
        platform: () => 'ios', deviceId: () => '\(UIDevice.current.identifierForVendor?.uuidString ?? "ios-unknown-device")',
        startLocation: () => post('location.start'), stopLocation: () => post('location.stop'),
        reload: () => post('reload'), openLocationSettings: () => post('location.settings'),
        get: () => '', set: (key, value) => { post('secure.set', {key, value}); return true; },
        remove: key => post('secure.remove', {key})
      };
    })();
    """

    private weak var webView: WKWebView?
    private let locationManager = CLLocationManager()
    private let pathMonitor = NWPathMonitor()
    private let monitorQueue = DispatchQueue(label: "smart-bamboo-network")

    func attach(_ webView: WKWebView) {
        self.webView = webView
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.distanceFilter = 3
        pathMonitor.pathUpdateHandler = { [weak self] path in self?.emit("network", ["online": path.status == .satisfied]) }
        pathMonitor.start(queue: monitorQueue)
    }

    func stop() {
        locationManager.stopUpdatingLocation()
        pathMonitor.cancel()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame,
              let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
        switch action {
        case "location.start": startLocation()
        case "location.stop": locationManager.stopUpdatingLocation(); emit("location", ["status": "stopped"])
        case "location.settings": UIApplication.shared.open(URL(string: UIApplication.openSettingsURLString)!)
        case "reload": webView?.load(URLRequest(url: AppConfig.applicationURL, cachePolicy: .useProtocolCachePolicy))
        case "secure.set":
            if let key = body["key"] as? String, let value = body["value"] as? String { KeychainStore.set(value, for: key) }
        case "secure.remove":
            if let key = body["key"] as? String { KeychainStore.remove(key) }
        default: break
        }
    }

    private func startLocation() {
        switch locationManager.authorizationStatus {
        case .notDetermined: locationManager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse: locationManager.startUpdatingLocation(); emit("location", ["status": "started"])
        default: emit("location", ["status": "unavailable"])
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedAlways || manager.authorizationStatus == .authorizedWhenInUse {
            manager.startUpdatingLocation(); emit("location", ["status": "started"])
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let point = locations.last else { return }
        emit("location", ["status": "update", "latitude": point.coordinate.latitude, "longitude": point.coordinate.longitude,
                          "accuracy": point.horizontalAccuracy, "altitude": point.altitude,
                          "timestamp": point.timestamp.timeIntervalSince1970 * 1000])
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        emit("location", ["status": "unavailable"])
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if AppConfig.isTrusted(url) || url.scheme == "about" || url.isFileURL { decisionHandler(.allow); return }
        if navigationAction.navigationType == .linkActivated { UIApplication.shared.open(url) }
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard let path = Bundle.main.path(forResource: "offline", ofType: "html"),
              let html = try? String(contentsOfFile: path, encoding: .utf8) else { return }
        webView.loadHTMLString(html, baseURL: Bundle.main.bundleURL)
    }

    private func emit(_ type: String, _ detail: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(detail),
              let data = try? JSONSerialization.data(withJSONObject: detail),
              let json = String(data: data, encoding: .utf8) else { return }
        DispatchQueue.main.async { [weak self] in
            self?.webView?.evaluateJavaScript("window.dispatchEvent(new CustomEvent('smart-bamboo-native:\(type)',{detail:\(json)}));")
        }
    }
}

private enum KeychainStore {
    static let service = "com.zhushan.smartbamboo.field"
    static func set(_ value: String, for key: String) {
        remove(key)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                    kSecAttrAccount as String: key, kSecValueData as String: Data(value.utf8),
                                    kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        SecItemAdd(query as CFDictionary, nil)
    }
    static func remove(_ key: String) {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                       kSecAttrAccount as String: key] as CFDictionary)
    }
}
