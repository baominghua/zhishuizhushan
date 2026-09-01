# 智慧竹山 iOS 现场端（I1 原型）

轻原生 `WKWebView` 壳，与 Android 共用 `/v2/field/mobile` 业务页面和 `smart-bamboo-native:*` 事件协议。已包含受限同源导航、系统 TLS 校验、默认 Web 缓存、相机/相册 Web 文件入口、Core Location、网络监听、Keychain 写入、离线页和返回手势。

## 生成工程

在 macOS 安装 Xcode 16 与 XcodeGen，然后运行：

```bash
cd ios-zhushan-app
xcodegen generate
open SmartBambooField.xcodeproj
```

发布前必须把 `Info.plist` 的 `SMART_BAMBOO_URL` 改为具有受信任证书的正式域名，配置 Team、签名和应用图标。当前 Windows 工作区不能执行 Xcode 编译或真机验证，因此本目录只表示可审查的 I1 源码原型，不代表 TestFlight 版本。
