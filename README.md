# 🐳 Telegram 115 Bot - Docker 部署说明

本项目使用 Docker Compose 部署 Telegram 115 Bot 服务。以下是配置说明和使用指南。

---

## 📁 文件结构

```text
project-root/
├── docker-compose.yml        # Docker Compose 配置文件
├── config.ini                # 你的 Telegram Bot 配置文件
└── worker.js                 # 用于获取 115 网盘刷新令牌的网页
```

---

## ⚙️ `docker-compose.yml` 示例

```yaml
version: '3.8'

services:
  telegram-bot:
    image: fz19870823190/telegram-115bot
    container_name: telegram-115bot
    volumes:
      - /root/telbot/config.ini:/app/config.ini
    user: root
    networks:
      docker:
        ipv4_address: 172.16.0.5
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  docker:
    external: true
```

---

## 📝 参数说明

| 配置项           | 描述 |
|------------------|------|
| `image`          | 指定镜像名，可为公开或私有镜像。 |
| `container_name` | 容器名称，方便使用 `docker ps` 管理。 |
| `volumes`        | 挂载配置文件到容器内。注意路径对应并具有适当读写权限。 |
| `user`           | 指定以 `root` 身份运行容器（如需写权限）。可根据需求修改。 |
| `networks`       | 使用外部 Docker 网络，便于 IP 管理或与其他容器通信。 |
| `ipv4_address`   | 固定容器 IP 地址（确保不冲突）。 |
| `restart`        | 设置重启策略，推荐使用 `unless-stopped`。 |
| `logging`        | 设置日志轮换，避免日志文件无限增长。 |

---

## 🌐 创建外部 Docker 网络

如未提前创建 `docker` 网络，需先执行以下命令：

```bash
docker network create \
  --driver=bridge \
  --subnet=172.16.0.0/24 \
  docker
```

> 📌 请确保 `ipv4_address` 所设 IP 地址在上述子网范围内且不冲突。

---

## 🚀 启动服务

在配置完成后，运行以下命令启动容器：

```bash
docker-compose up -d
```

---

## 🛠️ `worker.js`：获取 115 网盘刷新令牌网页

`worker.js` 是一个轻量网页服务，用于用户手动登录并获取 115 网盘的 `refresh_token`。

你可以将该文件部署在任意支持 JavaScript 的 Web 平台上，
例如 [Cloudflare Workers](https://workers.cloudflare.com/)。

### ✨ 使用方式

1. 打开 `worker.js`，将文件中的 `appid` 值替换为你自己的 115 应用 ID。
2. 将修改后的 `worker.js` 部署至 [Cloudflare Workers](https://workers.cloudflare.com/) 或你喜欢的平台。
3. 访问部署后的网页并登录 115 网盘账号，网页将显示你的 `refresh_token`。
4. 将获取到的 `refresh_token` 填入 `config.ini` 或其他配置中使用。

### 🌐 示例页面

如果你不想自行部署，也可以使用作者已搭建的演示网页：

🔗 [演示页面](https://115token.fzserver.top)

> ⚠️ 该页面每日限制请求次数为 10 万次，请勿频繁刷新。

---

## ✅ 其他建议

- 修改配置路径时，确保宿主机的 `config.ini` 文件存在且权限允许容器访问。
- 建议定期备份配置文件。
- 若不需要固定 IP，可删除 `ipv4_address` 及相关网络设置，Docker 将自动分配。

---

## 🔧 可选环境变量：自定义 Telegram API 基址

如果你使用私人搭建的反向代理或自定义的 Telegram API 入口，可以通过环境变量覆盖默认的 Telegram API 基址：

- 环境变量名：`TELEGRAM_API_BASE_URL` 或 `TELEGRAM_API_URL`
- 示例值：`https://my.telegram.proxy`（不带尾部斜杠）

在 Docker Compose 中使用示例：

```yaml
services:
  telegram-bot:
    image: fz19870823190/telegram-115bot
    environment:
      - TELEGRAM_API_BASE_URL=https://my.telegram.proxy
    # ... 其他配置
```

代码会在启动时检测该环境变量并将其传递给 Telegram 客户端库，
日志中会记录所使用的基址，方便排查。

## 📄 config.ini 配置说明

该文件用于配置 Telegram 115 Bot 的基本参数。

---

## ✏️ 配置示例

```ini
[telegram]
token = YOUR_BOT_TOKEN_HERE
```

---

## 参数说明

| 参数名 | 描述 |
|--------|------|
| `token` | Telegram Bot 的访问令牌（从 BotFather 获取）。 |
|         | 请将 `YOUR_BOT_TOKEN_HERE` 替换为你自己的 token。 |

---

## 🚨 注意事项

- **请妥善保管 `token`，不要泄露给他人。**
- 若配置文件路径变动，请同步更新 `docker-compose.yml` 中的挂载路径。

---

## 📬 联系与支持

如有疑问或建议，请提交 issue 或联系维护者。
