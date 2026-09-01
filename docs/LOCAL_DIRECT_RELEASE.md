# 智慧竹山本地直发生产服务器

本地直发用于服务器访问 GitHub 或 Docker Hub 不稳定的场景。普通代码版本默认使用“代码快速发布”：本机生成 Git Bundle 和前端生产产物，服务器复用当前健康生产镜像的 PDAL/Python 依赖层，仅重建应用代码层。依赖变化时仍使用完整镜像直发。两种模式都校验 SHA256、Bundle 完整性、镜像提交标签、目标提交和 Fast-forward，并沿用正式健康检查与自动回滚。

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
4. 等待 Bundle、前端产物上传、服务器代码层构建与健康检查；
5. 出现 `PRIMARY_APPLICATION_RELEASE_READY` 和“本地直发完成”即发布成功。

Bundle 与前端临时包默认生成在 `%LOCALAPPDATA%\SmartBamboo\ReleaseCache`，成功后自动删除；失败时服务器端文件会保留，便于排查和重试。代码快速发布不会生成约 1.1 GB 的完整镜像包，也不访问外部镜像仓库。

若 `server/requirements.txt` 或基础运行环境发生变化，快速发布会主动拒绝。此时执行完整镜像直发：

```powershell
$commit = git rev-parse HEAD
$tag = "$(Get-Date -Format yyyyMMdd)-$($commit.Substring(0,12))"
& .\ops\scripts\publish-primary-release.ps1 -TargetCommit $commit -ReleaseTag $tag -IncludeImage -Force
```

普通代码更新可手工执行：

```powershell
$commit = git rev-parse HEAD
$tag = "$(Get-Date -Format yyyyMMdd)-$($commit.Substring(0,12))"
& .\ops\scripts\publish-primary-release.ps1 -TargetCommit $commit -ReleaseTag $tag -ReuseProductionImage -Force
```

## 能解决与不能解决的问题

- 能绕过服务器访问 GitHub、Docker Hub超时和错误分支问题；
- Bundle 只传 Git 对象，通常远小于重新复制整个项目；
- 不会上传 `.env`、数据库密码或生产 Token；
- 不会重建数据库和 Nginx，应用健康检查失败时沿用正式回滚流程；
- 普通代码更新只传输小型 Bundle 与前端产物，复用生产依赖层；
- 完整镜像模式仍使用 Ubuntu 24.04 WSL 2、Docker Engine、Compose和Buildx，适合依赖或基础镜像变化。
