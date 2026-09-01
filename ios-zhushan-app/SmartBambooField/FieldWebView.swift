import SwiftUI
import WebKit

struct FieldWebView: UIViewRepresentable {
    func makeCoordinator() -> NativeCoordinator { NativeCoordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "smartBambooNative")
        controller.addUserScript(WKUserScript(source: NativeCoordinator.bridgeScript, injectionTime: .atDocumentStart, forMainFrameOnly: true))

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController = controller
        configuration.allowsInlineMediaPlayback = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .always
        context.coordinator.attach(webView)
        webView.load(URLRequest(url: AppConfig.applicationURL, cachePolicy: .useProtocolCachePolicy))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ webView: WKWebView, coordinator: NativeCoordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "smartBambooNative")
        coordinator.stop()
    }
}

