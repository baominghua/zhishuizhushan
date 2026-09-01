# 智慧竹山 Android APK 工程

这是智慧竹山移动现场端的轻原生壳，业务页面与后台共用 FastAPI、权限、状态机和离线同步协议。默认打开：

https://36.140.138.117:18081/v2/field/mobile

已接入：

- Web 缓存与 IndexedDB 持久化，不再每次启动清空缓存；
- 相机/相册文件选择、系统下载、定位权限与前台轨迹回调；
- 网络状态事件、离线页、系统返回和外部链接分流；
- Android Keystore AES-GCM 安全存储桥接；
- 仅信任系统证书，SSL 错误直接阻断，不提供绕过入口。

本机需要 JDK 17、Android SDK 和 Gradle。构建内测包：

```bash
gradle :app:assembleDebug -PSMART_BAMBOO_URL=https://your-trusted-domain.example/v2/field/mobile
```

正式真机包必须使用受信任域名证书；当前 IP 地址仅作为可配置开发默认值，不得通过忽略证书错误上线。
