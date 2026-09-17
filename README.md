# Leo Vocabulary — CET-4 个人词库 v0.1

一个面向个人、自托管的真题驱动词汇学习 Web。把阅读/听力中真实不认识的词整理成固定 JSON，预览后导入；系统按 `lemma` 合并词条，同时保留每次来源、词形和语境。

## 一键启动

需要 Docker 与 Docker Compose：

```bash
cp .env.example .env
docker compose up --build -d
```

如果访问 Docker Hub 需要本机代理：

```bash
HTTP_PROXY=http://127.0.0.1:10808 \
HTTPS_PROXY=http://127.0.0.1:10808 \
ALL_PROXY=socks5://127.0.0.1:10808 \
docker compose up --build -d
```

打开 <http://localhost:8080>。健康检查：<http://localhost:8080/api/health>，API 文档：<http://localhost:8080/api/docs>。

停止服务：

```bash
docker compose down
```

## 不使用 Docker 直接部署

需要 Python 3.12/3.13、Node.js 22 和 npm。直接部署模式会先构建 Vue，然后由 FastAPI 在同一个端口同时提供 Web 页面与 API，不要求额外安装 Nginx。

```bash
./scripts/install-direct.sh
./scripts/run-direct.sh
```

打开 <http://localhost:8080>。首次安装会创建：

```text
.venv/          Python 虚拟环境
data/vocab.db   SQLite 数据库
.env.direct     直接部署配置
```

修改 `.env.direct` 可以配置监听地址、端口、数据库和前端目录。启动脚本每次启动前都会执行 Alembic migration。

生产服务器可参考 `deploy/leo-vocabulary.service.example` 配置 systemd。若已经有 Nginx/Caddy，也可以把它反向代理到直接部署端口，但这不是运行所必需的。

更新代码后执行：

```bash
./scripts/install-direct.sh
# 然后重启 run-direct.sh 或 systemd 服务
```

数据保存在 Docker 卷 `vocab_data` 的 `/data/vocab.db`。`docker compose down` 不会删除数据；不要使用 `docker compose down -v`，除非确实要清空词库。

### 局域网手机访问

电脑和手机连同一个 Wi-Fi，在电脑查看局域网 IP，然后手机打开 `http://电脑IP:8080`。如系统防火墙询问，请允许 Docker 接收入站连接。需要从公网访问时，建议放在带 HTTPS 和访问控制的反向代理后面，不要直接暴露端口。

## JSON Import Schema v1

正式机器可读规范见 [`import-schema-v1.json`](./import-schema-v1.json)，可直接导入的样例见 [`example-import.json`](./example-import.json)。顶层固定为：

```json
{
  "schema_version": 1,
  "source": { "name": "来源名称", "type": "reading", "date": "2026-09-17" },
  "words": [
    {
      "word": "contributing",
      "lemma": "contribute",
      "phonetic": "/kənˈtrɪbjuːt/",
      "meanings": [{ "pos": "v.", "zh": "贡献；促成；导致" }],
      "word_family": ["contribution", "contributor"],
      "priority": "high",
      "context": "Factors contributing to...",
      "note": "contribute to = 促成；导致"
    }
  ]
}
```

约束：

- `schema_version` 必须是数字 `1`。
- `source.type`：`reading`、`listening`、`writing`、`translation`、`other`。
- `priority`：`high`、`normal`、`low`。
- `word` 是原文词形，`lemma` 是规范原形，也是词条去重键。
- 同一批中最多 1000 条。每个词至少有一个 `meanings` 项。
- 重复 lemma 不新建孤立词条：合并新释义和词族成员，并始终新增 encounter 记录。因此“同一个词在不同文章再次遇到”会累计遭遇次数。

推荐以后让 ChatGPT 按 `import-schema-v1.json` 输出，且只输出 JSON 代码块，禁止猜测语境；原文中没有的信息应写 `null` 或空数组。

## 已实现

- 中文响应式界面，适合手机和桌面端
- 单词创建、浏览、搜索、编辑、删除
- 来源创建、浏览、删除；reading/listening 等类型
- JSON v1 校验、预览、新建/合并统计、正式导入
- lemma 去重、词族、多词性释义、遭遇历史与语境
- 视觉和听觉两套独立熟练度
- “忘了 / 模糊 / 认识 / 秒懂”四档复习与简化 SM-2 排期
- 首页：待复习、本周新词、已掌握、近期来源、顽固词
- SQLite 持久化、Alembic 迁移、Docker 健康检查
- OpenAPI 文档与基础 API 测试
- 通用 encounter 写入 API，可供未来阅读与晨读模块复用
- 带稳定 UID 的 JSON/CSV 数据导出、复习前后快照与完整数据包
- 词条与来源使用软删除，避免误删历史学习事件

## 目录结构

```text
.
├── backend/
│   ├── app/                 # FastAPI、ORM、Schema、业务逻辑
│   ├── alembic/             # 数据库迁移
│   ├── tests/               # API 与去重/复习测试
│   └── Dockerfile
├── frontend/
│   ├── src/                 # Vue 3 单页界面
│   ├── nginx.conf           # 静态站点与 API 反向代理
│   └── Dockerfile
├── docker-compose.yml
├── import-schema-v1.json
├── export-schema-v1.json
├── ARCHITECTURE.md
└── example-import.json
```

## 本地开发与测试

后端（建议 Python 3.12 或 3.13）：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
DATABASE_URL=sqlite:///./dev.db alembic upgrade head
DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app --reload
pytest -q
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 开发模式会把 `/api` 代理到本机 `8000` 端口的后端；完整部署仍建议使用 Docker Compose。

## 数据库与未来扩展

业务层使用 SQLAlchemy 2，表结构规范化，不依赖 SQLite 专有 SQL；未来可把 `DATABASE_URL` 切换为 MySQL/PostgreSQL，并添加对应 Python 驱动。Alembic 负责结构升级。

已预留的扩展落点：

- TTS：`ReviewState.mode = audio` 已独立建模，前端听觉卡片保留声音入口。
- 真题全文比对：`Source` 与 `Encounter` 可关联将来的 document/passage 表。
- 可读性统计：可基于全文 token、lemma 和现有词库做覆盖率，不需要改变词条主表。

详细领域边界、建议的 Document/Passage/WordOccurrence 结构与待决定事项见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。

## 数据导出

后端提供稳定的 Export Schema v1；JSON 使用 `schema_version: 1`，CSV 使用稳定列名：

```text
GET /api/export/vocabulary?format=json|csv
GET /api/export/reviews?format=json|csv&date_from=2026-01-01&date_to=2026-12-31
GET /api/export/encounters?format=json|csv&date_from=...&date_to=...
GET /api/export/statistics?format=json|csv&date_from=...&date_to=...
GET /api/export/all
```

完整机器可读定义见 [`export-schema-v1.json`](./export-schema-v1.json)。`export/all` 已能产生完整数据包；在新实例恢复该数据包的 Import API 留到后续版本实现。

暂未实现账号与多用户、TTS 音频、全文录入、完整数据包恢复导入和公网鉴权。
