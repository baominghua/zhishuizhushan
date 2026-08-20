# 智慧竹山本地直发生产服务器

本地直发用于服务器访问 GitHub 不稳定的场景。本机会把当前已提交的 `HEAD` 打成 Git Bundle，通过 SSH/SCP 上传到生产服务器；服务器校验 SHA256、Bundle 完整性、目标提交和 Fast-forward 后，再调用正式发布脚本。源码传输不依赖服务器访问 GitHub。

## 安装桌面入口

在项目工作树打开 Windows PowerShell，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/scripts/install-primary-release-publisher.ps1
```

安装后桌面会出现：

- `本地直发智慧竹山平台.lnk`：推荐双击此快捷方式；
- `本地直发智慧竹山平台.cmd`：备用入口。

第一次正式发布会生成独立的 SSH 密钥，并要求输入一次服务器密码；以后不再重复输入。发布前必须提交全部本地修改，工具拒绝上传脏工作树或非当前 `HEAD` 的提交。

## 发布流程

1. 双击桌面快捷方式；
2. 核对提交号、发布标签和服务器地址；
3. 输入大写 `YES`；
4. 等待 Bundle 上传、服务器校验、镜像构建和健康检查；
5. 出现 `PRIMARY_APPLICATION_RELEASE_READY` 和“本地直发完成”即发布成功。

Bundle 默认生成在 `%LOCALAPPDATA%\SmartBamboo\ReleaseCache`，成功后自动删除；失败时服务器端 Bundle 会保留，便于排查和重试。

## 能解决与不能解决的问题

- 能绕过服务器访问 GitHub 超时和错误分支问题；
- Bundle 只传 Git 对象，通常远小于重新复制整个项目；
- 不会上传 `.env`、数据库密码或生产 Token；
- 不会重建数据库和 Nginx，应用健康检查失败时沿用正式回滚流程；
- 本机当前没有 Docker，因此此流程不上传 Docker 镜像。PDAL 基础镜像仍需先在服务器成功缓存一次，缓存后后续发布直接复用。
