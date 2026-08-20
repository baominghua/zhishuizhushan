# DJI 3D Tiles 直接登记与服务器入库

平台支持直接登记 DJI Terra 已生成的 PNTS 或 B3DM 目录。登记过程不会复制或转换瓦片，只会递归校验 `tileset.json` 引用、读取空间范围、统计瓦片并生成成果档案。

## Windows 一键发布

首次使用或脚本更新后，在 Windows PowerShell 执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/scripts/install-dji-material-publisher.ps1
```

安装器会把发布工具复制到不含中文的稳定目录 `%LOCALAPPDATA%\SmartBamboo\Tools`，并在桌面生成同名的 `.lnk` 和 `.cmd` 两个入口。桌面入口不再直接引用仓库中文路径，避免 `cmd.exe` 解析乱码。

安装完成后，优先双击桌面的 `发布大疆素材到智慧竹山.lnk`；也可以双击桌面或仓库中的 `.cmd`：

```text
ops/scripts/发布大疆素材到智慧竹山.cmd
```

脚本会自动扫描 `D:\拷贝任务`，列出可发布的 `terra_pnts` 和 `terra_b3dms`。选择序号后，它会：

1. 校验根 `tileset.json`；
2. 生成不压缩 TAR，避免对已压缩瓦片重复耗时；
3. 上传到 `36.140.138.117`；
4. 在服务器原子切换到固定快捷路径；
5. 将旧的同名目录移动到 `.releases`，出现异常时不会直接删除旧成果；
6. 把平台登记路径复制到剪贴板并打开影像成果页面。

第一次运行会询问是否安装素材发布专用 SSH 密钥，需要输入一次服务器密码；后续发布不再重复输入密码。固定路径示例：

```text
/app/data/remote-sensing/inbox/大横厂房/terra_pnts
```

同一项目再次发布时，该平台路径保持不变，已登记的成果不需要重新填写路径。成功后，本地临时 TAR 默认删除，`D:\拷贝任务` 下的源素材不会被修改；如需保留 TAR，可直接运行 PowerShell 脚本并添加 `-KeepArchive`。

## 推荐成果

- 林业点云浏览和点数统计：优先登记 `terra_pnts`。
- 倾斜摄影实景模型：登记 `terra_b3dms`。
- 原始 LAS/LAZ 需要生成 COPC 或重新加工时，仍使用“LAS/LAZ 点云”入口。
- PNTS 和 B3DM 应作为两份成果分别登记，不要混在同一个目录。

## 云服务器目录

生产容器将宿主机 `/srv/smart-bamboo/data` 挂载到容器 `/app/data`。建议将成果放到：

```text
宿主机：/srv/smart-bamboo/data/remote-sensing/inbox/<项目>/<成果目录>
平台填写：/app/data/remote-sensing/inbox/<项目>/<成果目录>
```

登记后不要移动、改名或删除该目录；三维地图会按需读取其中的 `tileset.json`、PNTS、B3DM 及子瓦片。

## 从 Windows 传到云服务器

大量小瓦片先打成 TAR 再上传，通常比逐文件 SCP 更稳定。以下以 `terra_pnts` 为例：

```powershell
tar -C "D:\拷贝任务\大横厂房\大横厂房\lidars" -cf "D:\拷贝任务\大横厂房-terra_pnts.tar" "terra_pnts"
scp -P 22 "D:\拷贝任务\大横厂房-terra_pnts.tar" root@36.140.138.117:/srv/smart-bamboo/data/remote-sensing/inbox/
```

登录服务器后解包到独立项目目录：

```bash
mkdir -p /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房
tar -xf /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房-terra_pnts.tar \
  -C /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房
chmod -R a+rX /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房/terra_pnts
```

传输完成后先核对根文件和容量：

```bash
test -f /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房/terra_pnts/tileset.json
du -sh /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房/terra_pnts
find /srv/smart-bamboo/data/remote-sensing/inbox/大横厂房/terra_pnts -type f | wc -l
```

## 平台登记

进入“无人机任务 → 影像成果 → 上传成果”，选择“DJI 3D Tiles”，填写：

```text
/app/data/remote-sensing/inbox/大横厂房/terra_pnts
```

平台会异步完成：

1. 校验根和子 `tileset.json`、相对路径及瓦片头；
2. 兼容 DJI Terra 的 `asset.version=0.0`，但不改写源文件；
3. 自动识别 PNTS/B3DM、点数、瓦片数、容量和覆盖范围；
4. 计算跨林班相交面积，由操作人确认一个或多个林班；
5. 在成果详情中通过“在三维地图打开”加载成果。

平台会拒绝远程 URL、越出登记目录的引用、缺失文件、隐藏工作目录、无效瓦片头和不受支持的根包围体。
