# Domain_Manager 域名管理系统

集中管理你收集的免费三级域名（多托管在 Cloudflare），跟踪到期时间、自动计算状态，
并在临近到期时通过页面内提醒与电子邮件主动通知。基于 Python + Flask，可部署到服务器，
通过浏览器访问。

## 功能

- 域名记录管理（增删改查，含格式与到期日期校验、重复检测）
- 自动状态计算：有效 / 临近到期 / 已过期
- 到期提醒：可配置多档提前提醒（默认 30/7/1 天），自动去重，发送失败重试
- 通知渠道：Web 页面内集中展示 + 电子邮件
- 可选 Cloudflare 同步：从账户拉取域名，保留你手动录入的到期时间
- 访问控制：登录鉴权、会话空闲超时、登出、暴力破解锁定
- 凭证安全：登录口令加盐哈希存储，Cloudflare/SMTP 凭证加密存储且不回显明文

## 快速开始

```cmd
:: 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2. 生成加密主密钥（请妥善保存，丢失将无法解密已存凭证）
.venv\Scripts\python.exe -m domain_manager.tools.genkey

:: 3. 设置必要的环境变量
set DM_ENCRYPTION_KEY=<上一步生成的密钥>
set SECRET_KEY=<任意随机字符串，用于会话签名>
set DM_ADMIN_PASSWORD=<管理员初始密码>

:: 4. 启动
.venv\Scripts\python.exe run.py
```

默认监听 `http://127.0.0.1:5000`，默认管理员用户名 `admin`。

### 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DM_ENCRYPTION_KEY` | 是 | Fernet 加密主密钥，用于加密 Cloudflare/SMTP 凭证 |
| `SECRET_KEY` | 建议 | Flask 会话签名密钥；未设置则每次启动随机生成（会使旧会话失效） |
| `DM_ADMIN_USER` | 否 | 管理员用户名，默认 `admin` |
| `DM_ADMIN_PASSWORD` | 否 | 管理员初始密码，默认 `changeme`（请务必覆盖） |
| `DM_DB_PATH` | 否 | SQLite 数据文件路径，默认 `domain_manager.db` |
| `DM_HOST` / `DM_PORT` | 否 | 监听地址与端口，默认 `127.0.0.1:5000` |

## 部署安全须知

- **必须置于 HTTPS（TLS）之后**：登录口令与凭证不可走明文 HTTP。建议用 Nginx/Caddy
  反向代理并启用 TLS，或置于 Cloudflare Tunnel / 内网之后。
- **单进程运行**：后台提醒调度随 Web 进程运行。多进程会导致定时任务重复触发、提醒发重复。
  若需多 worker，请将调度器单独隔离到一个实例。
- **妥善保管 `DM_ENCRYPTION_KEY`**：密钥丢失将无法解密已保存的 Cloudflare/SMTP 凭证。

## 运行测试

```cmd
.venv\Scripts\python.exe -m pytest -q
```

测试包含针对设计中 31 条正确性属性的基于性质的测试（Hypothesis），每条至少 100 个随机用例。

## 项目结构

```
domain_manager/
  models.py          数据模型、枚举、Result 类型
  validation.py      域名/日期校验纯函数
  status.py          状态计算纯函数
  store.py           SQLite 持久化层
  domain_service.py  域名核心服务（CRUD/筛选/排序）
  crypto.py          凭证加密与掩码
  config_service.py  配置管理
  auth.py            认证、会话、锁定
  notification.py    通知渠道抽象与提醒内容
  channels.py        页面内 / 邮件渠道实现
  reminders.py       提醒计算、去重、重试与调度
  scheduler.py       APScheduler 装配
  cloudflare.py      Cloudflare 同步
  web/               Flask 路由与 Jinja2 模板
  tools/genkey.py    生成加密主密钥
run.py               启动入口
```
