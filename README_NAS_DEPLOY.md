# 智慧竹山与遥感 SDK 部署说明

本发布包同时支持两种部署模式：

- **一体化测试部署**：前端页面、SDK、COG API、GDAL、TiTiler 全部放在一台服务器。
- **应用/GIS 拆分部署**：应用服务器只放页面和 SDK；GIS/GDAL 服务器负责遥感影像、COG 转换和瓦片服务。

完整发布、接口、SDK 调用、文件上传、COG 处理和运维检查说明见：

```text
REMOTE_SENSING_RELEASE_DOCUMENT.md
```

## 页面入口

- 智慧竹山大屏：`index.html` 或 `zhushan-bigdata.html`
- 卫星图传管理系统：`satellite-manager.html`
- 手机端：`zhushan-mobile.html`
- 遥感 SDK：`sdk/remote-sensing-sdk.js`

## 必传文件

```text
assets/
offline-maps/
sdk/
server/
satellite-config.local.js
satellite-config.example.js
start-cog-server.ps1
start-cog-server.sh
zhushan-bigdata.html
zhushan-bigdata.js
zhushan-bigdata.css
satellite-manager.html
satellite-manager.js
satellite-manager.css
```

`sdk/` 必须上传，智慧竹山大屏和卫星图传管理系统都会引用它。

`server/` 用于 GIS/GDAL 服务器。如果只做静态页面展示，可以不启动后端，但以下能力不可用：

- GeoTIFF/TIFF 上传
- GDAL 转 COG
- 动态瓦片
- `/api/scenes` 遥感影像目录同步

## 前端配置

部署前修改 `satellite-config.local.js`：

```js
window.SATELLITE_CONFIG = {
  tiandituTk: "你的天地图浏览器端Key",
  tiandituType: "img",
  remoteApiBase: "",
};
```

一体化测试部署时，`remoteApiBase` 可以留空。页面会默认访问当前服务器的 `8010` 端口。

拆分部署时，把它改成 GIS/GDAL 服务地址：

```js
window.SATELLITE_CONFIG = {
  tiandituTk: "你的天地图浏览器端Key",
  tiandituType: "img",
  remoteApiBase: "https://gis.example.com",
};
```

## 一体化测试部署

适合 1 台高配测试服务器。

Windows：

```powershell
.\start-cog-server.ps1
```

Linux：

```bash
sh ./start-cog-server.sh
```

启动后访问：

```text
http://服务器IP:8010/zhushan-bigdata.html
http://服务器IP:8010/satellite-manager.html
http://服务器IP:8010/api/health
```

## 应用/GIS 拆分部署

应用服务器放：

```text
zhushan-bigdata.html / js / css
satellite-manager.html / js / css
sdk/
assets/
offline-maps/
satellite-config.local.js
```

GIS/GDAL 服务器放：

```text
server/
start-cog-server.ps1 或 start-cog-server.sh
data/remote-sensing/
```

GIS/GDAL 服务器启动时建议设置：

Windows：

```powershell
$env:REMOTE_SENSING_SERVE_STATIC = "0"
$env:REMOTE_SENSING_DATA_DIR = "D:\remote-sensing-data"
$env:REMOTE_SENSING_CORS_ORIGINS = "https://app.example.com"
$env:REMOTE_SENSING_PORT = "8010"
.\start-cog-server.ps1
```

Linux：

```bash
export REMOTE_SENSING_SERVE_STATIC=0
export REMOTE_SENSING_DATA_DIR=/data/remote-sensing
export REMOTE_SENSING_CORS_ORIGINS=https://app.example.com
export REMOTE_SENSING_PORT=8010
sh ./start-cog-server.sh
```

然后在应用服务器的 `satellite-config.local.js` 里配置：

```js
remoteApiBase: "https://gis.example.com"
```

## 后端环境变量

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `REMOTE_SENSING_DATA_DIR` | 原始影像、COG、目录 JSON 存储位置 | `data/remote-sensing` |
| `REMOTE_SENSING_CORS_ORIGINS` | 允许访问 GIS API 的前端域名，多个用英文逗号分隔 | `*` |
| `REMOTE_SENSING_SERVE_STATIC` | 是否由 GIS 服务托管前端页面，拆分部署建议设为 `0` | `1` |
| `REMOTE_SENSING_STATIC_DIR` | 静态页面目录 | 当前发布目录 |
| `REMOTE_SENSING_PORT` | 服务端口 | `8010` |
| `REMOTE_SENSING_IMPORT_DIRS` | 允许注册入库的服务器/NAS 文件目录，多个用英文逗号分隔 | `data/remote-sensing/inbox` |
| `REMOTE_SENSING_TASK_WORKERS` | 后台 COG 转换任务并发数 | `1` |
| `REMOTE_SENSING_CATALOG_BACKEND` | 目录库类型，正式环境使用 `mysql`，本地兼容 `json`，保留 `postgis` 迁移路径 | 本地 `json` / Docker `mysql` |
| `REMOTE_SENSING_DATABASE_URL` | MySQL 8 正式数据库连接串；兼容模式可传 PostGIS 连接串 | 空 |
| `REMOTE_SENSING_TILE_CACHE` | 是否启用瓦片落盘缓存，`1`/`0` | `1` |
| `REMOTE_SENSING_GEOSERVER_URL` | GeoServer 服务根地址 | 空 |
| `REMOTE_SENSING_GEOSERVER_LAYERS` | 手工配置的 GeoServer 图层名，多个用英文逗号分隔 | 空 |

检查部署状态：

```text
http://GIS服务器:8010/api/health
```

返回值里会包含 `deployment.dataDir`、`deployment.serveStatic`、`deployment.corsOrigins`，可用于确认部署配置是否生效。

## NAS 固定发布信息

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

密码不要写入文档或 Git 仓库，发布时使用当前 NAS 管理员密码。

## Docker Compose 部署

智慧竹山平台的一体化 Docker Compose 部署说明见：

```text
docs/deploy-smart-bamboo-platform.md
```
