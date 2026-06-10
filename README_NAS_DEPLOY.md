# 智慧竹山平台 NAS 部署说明

本发布包包含两部分：

- 静态前端：智慧竹山大屏、移动端、卫星图传管理系统、遥感 SDK。
- COG 瓦片服务：用于 GeoTIFF/TIFF 上传、GDAL 转 COG、rio-tiler 动态出瓦片。

## 页面入口

- 智慧竹山大屏：`index.html` 或 `zhushan-bigdata.html`
- 卫星图传管理系统：`satellite-manager.html`
- 手机端：`zhushan-mobile.html`

## 固定 NAS 发布信息

以后发布不要再重新找路径，直接使用下面这组地址。

- NAS 管理入口：`http://bmhlfc.top:8088/`
- 线上 Web 入口：`http://bmhlfc.top:12306/zhushan/`
- 大屏线上地址：`http://bmhlfc.top:12306/zhushan/zhushan-bigdata.html`
- 卫星图传管理地址：`http://bmhlfc.top:12306/zhushan/satellite-manager.html`
- 手机端地址：`http://bmhlfc.top:12306/zhushan/zhushan-mobile.html`
- FTP 发布目录：`ftp://bmhlfc.top:21/Web/zhushan/`
- SFTP/SSH 主机：`bmhlfc.top`
- SFTP/SSH 端口：`22`
- SFTP/SSH 用户：`admin`
- SFTP 真实目录：`/share/CACHEDEV1_DATA/Web/zhushan`

说明：QNAP 的 FTP 路径 `/Web/zhushan/` 对应系统真实路径 `/share/CACHEDEV1_DATA/Web/zhushan`。
密码不要写进文档或 Git 仓库，发布时使用当前 NAS 管理员密码。

## 必须一并上传的目录

```text
assets/
offline-maps/
sdk/
server/
satellite-config.local.js
start-cog-server.ps1
```

`sdk/` 必须上传。智慧竹山大屏和卫星图传管理系统都会引用 `sdk/remote-sensing-sdk.js`。

`server/` 也建议上传。没有后端服务时，页面可以打开，但 GeoTIFF/TIFF 转 COG、动态切瓦片、COG 影像同步不能工作。

## Windows NAS / Windows Server 启动 COG 服务

进入发布目录后执行：

```powershell
.\start-cog-server.ps1
```

启动后访问：

```text
http://NAS-IP:8010/
http://NAS-IP:8010/zhushan-bigdata.html
http://NAS-IP:8010/satellite-manager.html
```

## Linux NAS 启动 COG 服务

如果 NAS 支持 Python：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r server/requirements.txt
./.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8010
```

## 只做静态 Web Station 部署

可以把本目录上传到 QNAP `Web/zhushan`。

静态方式可访问普通页面，但以下能力不可用：

- GeoTIFF/TIFF 上传
- GDAL 转 COG
- 动态切瓦片
- `/api/scenes` 遥感影像目录同步

要使用完整 SDK 能力，请启动上面的 COG 服务。
