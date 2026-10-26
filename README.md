# DeepSeek harness 容器化

将官方 `@deepseek-ai/dsh@0.2.1-rc.3` 封装为独立 Docker 容器。

## 交付目标

- 一个智能体实例运行在一个独立容器中，配置、持久化数据和日志按实例隔离。
- 每个发布版本可以唯一定位到源码、依赖与镜像，支持明确指定版本和回滚。
- 提供 Windows 与 Linux 的一键安装部署入口，包含前置检查、启动和健康验证。
- 将实施、学习、测试与故障处理过程保存在仓库中，随代码一起管理。

## 一键启动

前置条件：运行中的 Linux Docker 引擎、Docker Compose 和 Python 3.10+。首次从源码构建需要联网。脚本安装容器内的应用依赖，不自动安装宿主操作系统的 Docker 或 Python。

Windows PowerShell，在本项目目录执行：

```powershell
.\deploy.ps1 up
```

Linux：

```sh
sh deploy.sh up
```

启动后访问 http://127.0.0.1:3080 。当前构建目标是 `linux/amd64`。无须模型、API 密钥或远程桌面配置即可启动 Web UI；模型对话需要后续配置模型服务。

首次打开使用 `.\deploy.ps1 open`，脚本会在浏览器中完成登录链接跳转。未登录时直接访问根地址返回 401，属于预期认证行为。

另建一个独立实例：

```powershell
.\deploy.ps1 up --agent manager --port 3081
```

这会创建独立容器、网络和数据卷。实例名称 `manager` 本身不赋予管理能力；专家提示词和跨容器协作尚未实现。上游 Web UI 允许多个会话和内部子智能体，本阶段的隔离单位是一个独立 harness 部署实例，尚未强制限制为一个模型会话。

## 版本管理

每次 `build` 生成唯一编号：语义版本 + UTC 时间 + 随机标识。发布清单保存镜像 ID、源码文件 SHA256、依赖锁文件摘要与构建输入快照。部署使用不可变镜像 ID，并验证版本标签与清单一致。

```powershell
.\deploy.ps1 build
.\deploy.ps1 versions
.\deploy.ps1 up --release <完整发布编号>
.\deploy.ps1 status
.\deploy.ps1 logs
.\deploy.ps1 stop
```

普通 `up` 保持已有实例版本；更新需要显式指定新发布编号。`stop` 保留数据卷。历史镜像可以重新部署，但应用数据升级后的降级兼容性需要独立验证。

源码安装依赖使用锁文件，基础镜像固定摘要。系统软件包在构建时安装并记录实际版本；不承诺不同日期重建得到逐字节相同镜像。跨机器使用同一导出镜像可保持完全相同的镜像内容。

## 项目记录

- [实施计划与验收标准](docs/implementation-plan.md)
- [学习与操作记录](docs/learning-log.md)
- [部署与版本管理](docs/deployment.md)
- [MRI 项目与封装的关系](docs/architecture.md)
