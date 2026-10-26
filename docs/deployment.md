# 部署与版本管理

## Windows 使用

在本项目目录运行 `.\deploy.ps1 up`。已有实例保留当前版本，首次部署使用最近构建的镜像；若没有发布版本则构建一个。命令成功返回前必须通过容器健康检查。

首次访问需要上游生成的登录令牌。Windows 上执行 `.\deploy.ps1 open` 会在默认浏览器中打开认证链接；`url` 命令仅在你需要复制链接时输出完整链接。普通根地址在没有登录 Cookie 时返回 401，这是正常认证行为。请勿公开 `url` 的输出。

如果 Windows 策略阻止 PowerShell 脚本，可以使用等价命令 `python scripts\deploy.py up`，无需更改系统执行策略。

`--agent` 指定实例，`--port` 指定本机端口。例如 `.\deploy.ps1 up --agent expert --port 3082`。不同实例需要不同端口。

## Linux 交付

在 Windows 执行：

```powershell
.\deploy.ps1 export --release <完整发布编号>
```

输出位于 `exports/<发布编号>/`，包括 `image.tar`、校验清单、发布清单、源码快照和跨平台部署脚本。该包不含运行实例的数据、会话、模型权重或密钥。

将整个导出目录复制到已安装 Docker Engine、Compose 和 Python 3.10+ 的 Linux amd64 服务器，在该目录运行：

```sh
sh deploy.sh up --bundle .
```

脚本校验文件 SHA256、导入镜像、核对镜像 ID 和版本标签，随后启动并等待健康检查。传输校验用于发现文件损坏，不是发布者数字签名。

服务监听服务器的回环地址。通过 SSH 端口转发访问，例如 `ssh -L 3080:127.0.0.1:3080 user@server`，再在本机打开 http://127.0.0.1:3080 。本项目尚未在用户的实际 Linux 服务器上验证。

首次通过隧道访问时，在服务器执行 `sh deploy.sh url` 并在本机浏览器打开其输出的认证链接。转发端口需与部署端口一致。

## 发布和回滚

`VERSION` 是封装版本号，上游 harness 版本另见 `upstream.json`。每次构建产生独立发布 ID，不覆盖历史发布。镜像部署按实际内容 ID 选择，不依赖可变的 `latest` 标签。

`releases/<发布编号>/manifest.json` 保存发布信息；`source.zip` 保存当次构建和部署脚本输入。官方 npm 元数据未提供 gitHead，因此 `reviewed_commit` 仅表示检查过的上游源码版本，不伪称该提交就是 npm 包的构建来源。npm 包身份由精确版本和 integrity 校验确定。

升级：先执行 `build`，再 `up --release <新编号>`。回到历史镜像：`up --release <旧编号>`。镜像回滚不会回退数据卷；跨 harness 版本回滚前应停止实例、备份数据卷，并确认上游数据格式兼容性。

当前通用封装不冻结 Web UI 中修改的模型配置或后装插件。这些属于实例的可变状态；生产业务发布应将审核后的插件和非密钥配置纳入新的镜像版本。运行身份不能仅由镜像标签概括全部可变配置。

## 数据和记录

| 位置 | 内容 |
| --- | --- |
| `runtime/package-lock.json` | 锁定 npm 依赖版本与校验值 |
| `releases/` | 本机生成的不可覆盖发布清单与源码快照 |
| `instances/<实例>/compose.json` | 当前部署描述 |
| `instances/<实例>/deployment.json` | 最近一次健康部署结果 |
| Docker 卷 `dsh-<实例>_state` | Harness 配置、会话、缓存与凭据 |
| Docker 卷 `dsh-<实例>_workspace` | 容器内工作文件 |
| `logs/deployment.jsonl` | 构建、部署、停止、导入、导出及失败事件 |
| `docs/learning-log.md` | 实施目的、知识点、问题及解决方式 |

`logs` 命令显示最近 100 行进程日志；Docker 进程日志按 10 MiB、3 份轮换。上游会话记录保存在状态卷中。业务截图与操作事件的专门审计格式将在 MRI 插件阶段添加。

停止实例使用 `stop`，不会删除数据卷。若部署失败，应先运行 `status` 和 `logs` 检查实际容器；`deployment.json` 只代表最近一次成功部署，不代表失败尝试已自动回滚。

## 健康检查范围

健康检查读取仅容器用户可读的临时登录信息，完成 Cookie 交换并验证 Web 服务返回 HTML；不代表模型推理、真实 MRI 操作或浏览器全部交互已经通过。此阶段不需要模型地址或 API 密钥。

容器根文件系统只读，状态卷和工作卷可写。`/tmp` 使用可执行的内存文件系统，因为上游原生加载器需要从该目录加载共享库；仍保留 nosuid、nodev 和非 root 用户。当前本地配置关闭上游会话贡献和 OTel 上传。
