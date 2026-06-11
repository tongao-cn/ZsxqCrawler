> [!IMPORTANT]
> 当前后端入口已整理到 `backend/`，根目录仅保留 `main.py` 作为兼容启动入口。
> 推荐使用 `uv run zsxq-api` 或 `uv run python -m backend.main` 启动后端服务。

<div align="center">
  <img src="images/_Image.png" alt="知识星球数据采集器" width="200">
  <h1>知识星球数据采集器</h1>
  <p>知识星球内容爬取与文件下载工具，支持话题采集、文件批量下载等功能</p>
  
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/) [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Platform](https://img.shields.io/badge/Platform-Windows | Linux | macOS-lightgrey.svg)]()
  
  <img src="images/info.png" alt="群组详情页面" height="400">
</div>

## 项目特性

- **智能采集**: 支持全量、增量、智能更新等多种采集模式
- **文件管理**: 自动下载和管理知识星球中的文件资源，支持直接下载
- **Web 界面**: 现代化的 React 前端界面，操作直观

## 界面展示

### Web 界面

<div align="center">
  <img src="images/home.png" alt="首页界面" height="400">
  <p><em>首页 - 群组选择和概览</em></p>
</div>

<div align="center">
  <img src="images/config.png" alt="配置页面" height="400">
  <p><em>配置页面 - 爬取间隔设置</em></p>
</div>

<div align="center">
  <img src="images/log.png" alt="日志页面" height="400">
  <p><em>日志页面 - 实时任务执行日志</em></p>
</div>

<div align="center">
  <img src="images/column.png" alt="专栏文章页面" height="400">
  <p><em>专栏文章页面 - 专栏目录浏览、文章内容展示与视频下载</em></p>
</div>

## 快速开始

### 1. 安装部署

```bash
# 1. 克隆项目
git clone https://github.com/2977094657/ZsxqCrawler.git
cd ZsxqCrawler

# 2. 安装uv包管理器（推荐）
pip install uv

# 3. 安装依赖
uv sync
```

### 2. 获取认证信息

在使用工具前，需要获取知识星球的 **Cookie**（无需再手动填写群组ID）：

1. **获取Cookie**:
   - 使用浏览器登录知识星球
   - 按 `F12` 打开开发者工具
   - 切换到 `Network` 标签
   - 刷新页面，找到任意API请求
   - 复制请求头中的 `Cookie` 值

2. **首次使用**：
   - 启动 Web 界面后，在“配置认证信息/账号管理”中粘贴 Cookie 完成登录
   - 后端会根据该账号自动获取您加入的全部星球，前端选择不同星球时会将对应的群组ID动态传入后端进行抓取
   - 如果需要使用 AI 分析，请通过环境变量 `OPENAI_API_KEY` 提供密钥，不要把明文密钥写入 `config.toml`

### 3. 运行应用

#### 方式一：Web界面（推荐）

```bash
# 1. 启动后端API服务
uv run python -m backend.main

# 2. 启动前端服务（新开终端窗口）
npm --prefix frontend run dev
```

如果前后端不在同一台机器/容器中，前端默认请求 `http://localhost:8508` 会导致 `Failed to fetch`，请在 `frontend/.env.local` 中配置后端地址（示例）：

```bash
NEXT_PUBLIC_API_BASE_URL=http://192.168.x.x:8508
```

后端 CORS 默认只允许来自 `http://localhost:18080` 和 `http://127.0.0.1:18080` 的浏览器请求；如果前端运行在其他地址，请在启动后端前设置 `CORS_ALLOW_ORIGINS`，多个来源用逗号分隔。

然后访问：
- **Web 界面**: http://localhost:18080
- **API 文档**: http://localhost:8508/docs

## 项目代码结构

后端代码已经按职责整理到 `backend/`：

- `backend/main.py`: FastAPI 应用真实入口。
- `backend/routes/`: API 路由模块。
- `backend/services/`: AI 分析、A 股分析、导出等业务服务。
- `backend/storage/`: PostgreSQL 访问、任务持久化、账号存储。
- `backend/core/`: 配置、日志、路径、账号上下文、爬虫运行时、本地群运行时等核心能力。
- `backend/crawlers/`: 知识星球话题采集和文件下载器。
- `scripts/`: 一次性或辅助命令行脚本。

架构分层、数据边界和后续演进路线见 `docs/project-architecture-roadmap.md`。

推荐使用新目录入口：

```bash
uv run python -m backend.main
```

安装后也可以使用 `pyproject.toml` 中定义的命令入口：

```bash
uv run zsxq-api
uv run a-share-analysis
uv run csv-chart-server
uv run manage-postgres-core-schema --apply
uv run manage-postgres-core-access --apply
uv run generate-postgres-status-report --output docs\postgres_status_report.md
uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:password@host:5432/zsxq"
```

`manage-postgres-core-schema --apply` 是唯一推荐的 PostgreSQL schema 初始化、补列和建索引入口。API、采集、文件下载、账号、任务、日报和 A 股分析运行时不会自动执行 DDL；新环境必须先运行该命令。

为兼容旧后端启动命令，项目根目录暂时仅保留 `main.py`；其它命令请使用 `pyproject.toml` 中的入口或 `python -m ...` 新目录入口。新增后端代码时优先放入 `backend/` 对应子目录。

## 数据存储与下载路径

结构化数据统一存储在 PostgreSQL 的 `zsxq_core` schema。`output/databases` 目录只保留为下载文件和图片缓存的本地目录，不再作为真实数据库文件存储位置。

- **话题 / 文章内容 / 文件元数据**: PostgreSQL `zsxq_core` schema；其他项目通过只读账号直接读取 `zsxq_core`。
- **已下载附件 / 文件**: `output/databases/{group_id}/downloads/`  
  - 通过 Web 界面触发的文件下载，实际都会保存在这里。  
  - 例如当前示例配置中，群组 `88851415151812` 的文件路径为：`output/databases/88851415151812/downloads/`。
- **图片缓存（可安全删除）**: `output/databases/{group_id}/images/`  
  - 用于话题图片预览的本地缓存，如被删除，后续访问时会自动重新生成。

> 提示：当前版本不会将文章导出为 Markdown/HTML 文件，**文章内容都存储在 PostgreSQL 中**；若需要再导出为文件，可以后续通过数据库二次处理实现。

### PostgreSQL 存储

当前部署以 PostgreSQL 为唯一结构化数据源。请在 `config.toml` 中配置：

```toml
[database]
backend = "postgres"
postgres_dsn = "postgresql://user:password@localhost:5432/zsxq"
```

也可以用环境变量覆盖：

```bash
$env:ZSXQ_DATABASE_BACKEND = "postgres"
$env:ZSXQ_POSTGRES_DSN = "postgresql://user:password@localhost:5432/zsxq"
```

其它项目共享读取同一份 PostgreSQL 数据时，使用 `zsxq_reader` 只读账号直接读取 `zsxq_core`：

```bash
uv run backfill-postgres-core-group-ids --apply
uv run manage-postgres-core-access --apply --login-roles --reader-password "<reader-password>" --writer-password "<writer-password>"
```

只读账号的查询约定和常用 SQL 示例见 `docs/postgres_core_reader_usage.md`。

旧的 path-derived `zsxq_*` schema、`zsxq_public` 和迁移追踪列属于迁移残留。真实库清理前必须先暂停任务、完成 PostgreSQL 备份，并用 dry-run 检查删除清单：

```bash
uv run cleanup-postgres-legacy-artifacts --dry-run
```

生产部署时，可用管理员 DSN 初始化登录角色和内部表索引：

```bash
uv run manage-postgres-core-schema --apply
uv run manage-postgres-core-access --apply --login-roles --reader-password "<reader-password>" --writer-password "<writer-password>"
```

应用运行时只做 `zsxq_core` 读写；如果缺表或缺列，错误信息会提示重新执行 `uv run manage-postgres-core-schema --apply`。
仅测试或紧急兼容场景可临时设置 `ZSXQ_BOOTSTRAP_SCHEMA_ON_CONNECT=true` 让连接时补 schema，生产部署不建议启用。

日常 PG 状态巡检可产出 Markdown 快照报告：

```bash
uv run generate-postgres-status-report --output docs\postgres_status_report.md
```

给其它项目发 reader DSN 前，可验证它只能读取 `zsxq_core`，不能写入或访问旧 schema：

```bash
uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:password@host:5432/zsxq"
uv run verify-postgres-writer-access --dsn "postgresql://zsxq_writer:password@host:5432/zsxq"
```

修改 core schema、权限或清理逻辑后，可运行 Docker smoke 验证 `zsxq_core`、reader/writer 权限和 legacy cleanup dry-run：

```bash
.\scripts\run_postgres_core_smoke.ps1
```

修改运行时存储入口后，可运行 cutover smoke 验证业务 storage 类的新写入只进入 `zsxq_core`，且不会新建旧 `zsxq_*` schema：

```bash
.\scripts\run_postgres_runtime_cutover_smoke.ps1
```

## 赞助与支持

如果本项目对你有帮助，欢迎通过以下方式赞助。付款时请在备注中填写“希望公开展示的链接”（如个人主页、GitHub 仓库等），我们会在 README 的“赞助鸣谢”表格中展示。

<div align="center">
  <table>
    <tr>
      <td align="center">
        <img src="https://github.com/LifeArchiveProject/BilibiliHistoryFetcher/raw/master/public/wechat.png" alt="微信收款码" width="220"><br>
        微信赞助
      </td>
      <td align="center">
        <img src="https://github.com/LifeArchiveProject/BilibiliHistoryFetcher/raw/master/public/zfb.jpg" alt="支付宝收款码" width="220"><br>
        支付宝赞助
      </td>
    </tr>
  </table>
</div>

| 联系内容                                              | 付款金额 |
| ----------------------------------------------------- | -------- |
| https://github.com/yankai19900930 | ￥28.88      |
| https://github.com/freejacklee | ￥3 |
| 匿名用户 | ￥88.88 |

提示：已赞助但未收录，请在 Issues 提交凭证与备注链接；如需匿名可说明。

提示：已赞助但未收录，请在 Issues 提交凭证与备注链接；如需匿名可说明。

## 贡献指南

欢迎提交Issue和Pull Request！

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

## 免责声明

本工具仅供学习和研究使用，请遵守知识星球的服务条款和相关法律法规。使用本工具产生的任何后果由使用者自行承担。

---

<div align="center">
  <p>如果这个项目对你有帮助，请给个 Star 支持一下。</p>
</div>
