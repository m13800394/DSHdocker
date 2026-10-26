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
py -3 scripts\deploy.py up
```

如果 PowerShell 允许执行脚本，也可以使用：

```powershell
.\deploy.ps1 up
```

Linux：

```sh
sh deploy.sh up
```

首次打开运行：

```powershell
py -3 scripts\deploy.py open
```

等价入口为 `.\deploy.ps1 open`。脚本会在浏览器中完成登录链接跳转。未登录时直接访问根地址返回 401，属于预期认证行为。首次启动后可访问 http://127.0.0.1:3080 。

## 配置多个 Harness 实例

默认实例名是 `mri-operator`，默认端口是 `3080`。使用不同的 `--agent` 名称和未占用的 `--port`，即可创建多个独立实例。以下 Windows 命令均在本项目目录执行。

### 创建并打开实例

保留当前实例，再创建名为 `manager` 和 `expert` 的实例：

```powershell
py -3 scripts\deploy.py up --agent manager --port 3081
py -3 scripts\deploy.py up --agent expert --port 3082
```

每条命令成功返回并显示 `Agent ... is ready` 后，再打开对应实例：

```powershell
py -3 scripts\deploy.py open --agent mri-operator
py -3 scripts\deploy.py open --agent manager
py -3 scripts\deploy.py open --agent expert
```

| 实例名 | 本机访问地址 | 用途说明 |
| --- | --- | --- |
| `mri-operator` | http://127.0.0.1:3080 | 默认的通用 Harness 实例 |
| `manager` | http://127.0.0.1:3081 | 可后续配置为 Manager |
| `expert` | http://127.0.0.1:3082 | 可后续配置为 Expert |

访问需要登录；请使用对应的 `open --agent <实例名>` 命令。`url --agent <实例名>` 可以输出登录链接，链接含登录凭据，请勿公开。

实例名必须以小写字母开头，只能包含小写字母、数字和连字符，最长 40 个字符。端口范围为 `1024` 至 `65535`；同一台电脑上的实例需要使用不同的可用端口。

### 管理指定实例

以下命令以 `manager` 为例：

```powershell
# 查看运行状态和健康状态
py -3 scripts\deploy.py status --agent manager

# 查看最近 100 行日志
py -3 scripts\deploy.py logs --agent manager

# 停止并移除该实例的容器和网络，保留数据卷
py -3 scripts\deploy.py stop --agent manager

# 重新启动，沿用该实例最近成功部署的版本和端口
py -3 scripts\deploy.py up --agent manager
```

省略 `--agent` 时，操作对象始终是默认实例 `mri-operator`。管理其他实例时，每次都要指定对应名称。

Linux 使用相同参数，将命令前缀替换为 `sh deploy.sh`，例如：

```sh
sh deploy.sh up --agent manager --port 3081
sh deploy.sh status --agent manager
```

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
