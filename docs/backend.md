# 后端开发文档

> 本文档描述 `app/backend` 的**实际实现**：分层职责、认证、数据库与事务边界、六阶段生成流水线、
> API 清单、AI 调用、对象存储、可靠性与部署约束。所有内容以仓库代码为准，与 `docs/mission.md`
> 的产品边界、`docs/plan.md` 的工程方案保持一致。

## 一、技术栈与运行形态

| 层 | 选型 |
|----|------|
| 运行时 | FastAPI + Uvicorn（常驻进程）/ Mangum（AWS Lambda） |
| 语言 | Python 3（异步 I/O） |
| ORM | SQLAlchemy 2.0 AsyncSession |
| 数据库 | PostgreSQL（生产）/ SQLite（本地，`aiosqlite`） |
| 迁移 | Alembic |
| 认证 | Atoms 平台 OIDC（PKCE）+ 自签应用 JWT（python-jose） |
| AI | 平台 AIHub（OpenAI 兼容 SDK） |
| 存储 | 平台对象存储（预签名 URL） |

关键依赖见 `requirements.txt`：`fastapi`、`uvicorn[standard]`、`sqlalchemy`、`asyncpg`、
`alembic`、`pydantic-settings`、`python-jose[cryptography]`、`openai`、`sse-starlette`、
`PyMuPDF`、`mangum`、`stripe`。

## 二、目录结构与职责

```
app/backend/
├── main.py               # [受保护] 应用入口：日志、CORS、路由自动发现、异常处理、启动恢复
├── lambda_handler.py     # [受保护] AWS Lambda 入口（Mangum）与前后端路由
├── core/                 # [受保护] 运行时基础设施
│   ├── config.py         #   设置对象（pydantic-settings + 环境变量动态读取）
│   ├── database.py       #   异步引擎、连接池策略、会话工厂、get_db 依赖
│   ├── auth.py           #   OIDC/PKCE/JWKS、JWT 签发与校验、登出地址
│   ├── environment.py    #   环境变量布尔/整数解析
│   └── telemetry/        #   请求诊断中间件、外部 HTTP 观测、SQLAlchemy 埋点（fail-open）
├── models/               # [受保护] ORM 模型（由 BackendManager 自动生成）
├── routers/              # 接口层，启动时自动发现，前缀必须为 /api/v1/
├── services/             # 业务逻辑层
├── schemas/              # Pydantic 请求/响应模型
├── alembic/              # 数据库迁移
├── dependencies/         # 依赖注入：认证、数据库会话
├── utils/                # 日志清理等通用工具
└── skills_docs/          # 平台开发规范（web_sdk / custom_api / ai_capability / object_storage）
```

`core/**`、`models/**`、`main.py`、`lambda_handler.py` 为受保护路径：业务开发只允许改动
`routers/`、`services/`、`schemas/`、`dependencies/`、`utils/`。

### 路由自动发现

`main.py` 的 `include_routers_from_package(app, "routers")` 用 `pkgutil.walk_packages` 遍历
`routers` 包，把模块级变量 `router`（或 `admin_router`）注册进应用，**无需手动 `include_router`**。
因此新增接口只需在 `routers/` 下新建模块并定义 `router = APIRouter(prefix="/api/v1/...")`。

中间件顺序：`RequestSummaryMiddleware`（诊断，最外层）后注册，CORS 使用
`allow_origin_regex=".*"` 与 `allow_credentials=True`。全局异常处理器仅在生产环境返回
`Internal Server Error`，`ENVIRONMENT=dev` 时返回类型、消息与堆栈。

### 生命周期

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # MGX_IGNORE_MODULE_INIT 默认 True → 跳过显式建连，首次使用惰性初始化
    if not get_env_bool("MGX_IGNORE_MODULE_INIT", default=True):
        await initialize_database()
    # 进程重启后重新调度未完成项目（尽力而为，失败不阻断启动）
    await resume_pending_projects()
    yield
    if not get_env_bool("MGX_IGNORE_MODULE_INIT", default=True):
        await close_database()
```

## 三、本地启动与自测

```bash
cd app/backend
python -m py_compile main.py          # 语法检查（改动的 .py 文件都要过）
uvicorn main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health      # {"status":"healthy"}
curl http://localhost:8000/database/health
```

> 本地联调脚本为 `app/start_app_v2.sh`。**生产部署必须去掉 `uvicorn --reload`**：
> `--reload` 会在文件变更时重启工作进程，重启窗口内没有上游、进程内后台工作器也会被中断，
> 是 502 的直接来源之一。

## 四、配置与环境变量

`core/config.py` 的 `settings` 为 `pydantic-settings` 实例，`__getattr__` 支持按
`snake_case → UPPER_CASE` 动态读取环境变量（例如 `settings.jwt_secret_key` 读 `JWT_SECRET_KEY`）。

| 变量 | 用途 |
|------|------|
| `DATABASE_URL` | 数据库连接串（同步驱动会被自动改写为异步驱动） |
| `HOST` / `PORT` | 服务监听地址与端口（默认 `0.0.0.0:8000`） |
| `PYTHON_BACKEND_URL` | 外部回调可用的后端地址（`backend_url` 优先读它） |
| `FRONTEND_URL` | 前端地址，用于构造登出回跳 |
| `IS_LAMBDA` | 是否 Lambda 环境，决定连接池策略 |
| `OIDC_ISSUER_URL` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` / `OIDC_SCOPE` | 平台 OIDC 配置 |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | 应用 JWT 签名与有效期（默认 60 分钟） |
| `ADMIN_USER_ID` / `ADMIN_USER_EMAIL` | 管理员判定（平台 user_id 命中即为 `admin` 角色） |
| `OSS_SERVICE_URL` / `OSS_API_KEY` | 对象存储服务地址与令牌 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` / `DB_POOL_RECYCLE` / `DB_POOL_PRE_PING` / `DB_POOL_USE_LIFO` | 连接池调参（默认 `5 / 5 / 30s / 280s / true / true`） |
| `DB_DISABLE_POOL` | 逃生开关：设为 true 时使用 `NullPool`（每请求新建连接） |
| `MGX_IGNORE_MODULE_INIT` | 默认 true，跳过启动期显式建连 |
| `MGX_IGNORE_INIT_DB` | 兼容旧开关，设为 true 时跳过 `initialize_database` |
| `ENVIRONMENT` | `dev` 时异常响应返回堆栈 |
| `LOCAL_PATCH` | 本地开发时把回调地址的 `https→http`、`:8000→:3000` |
| `FUNCSEA_BACKEND_LOG_*` | 本地日志轮转与总量上限 |

## 五、认证与授权

### 5.1 登录链路（OIDC + PKCE）

1. `GET /api/v1/auth/login`：生成 `state`、`nonce`、`code_verifier`，把三者写入 `oidc_states`
   表（10 分钟过期，写前清理过期行），再 302 跳转到平台授权页。
2. `GET /api/v1/auth/callback`：用 `state` 取出并一次性删除临时数据，携带
   `code_verifier` 换取 token；用 JWKS（RS256）校验 `id_token` 的签名、`iss`、`aud`，
   并比对 `nonce`；随后 `get_or_create_user` 落库用户，签发应用 JWT。
3. 成功后 302 到 `{FRONTEND_URL}/auth/callback#token=...&expires_at=...&token_type=Bearer`
   （片段方式，避免 token 进入服务端日志）。任何失败都 302 到
   `{FRONTEND_URL}/auth/error?msg=...`，不让用户停在空白页。

`redirect_uri` 由 `get_dynamic_backend_url(request)` 按
`mgx-external-domain > x-forwarded-host > host > settings.backend_url` 的优先级动态推导，
本地可用 `LOCAL_PATCH` 改写。

### 5.2 平台令牌换取

`POST /api/v1/auth/token/exchange` 用 `platform_token` 调平台
`{OIDC_ISSUER_URL}/platform/tokens/verify`；校验通过后按 `user_id == ADMIN_USER_ID`
判定 `admin`/`user` 角色并签发应用 JWT。上游不可用返回 502，校验失败透传上游状态码。

### 5.3 应用 JWT 与请求鉴权

- 签发：`services/auth.py::issue_app_token`，claims 含 `sub`、`email`、`role`，可选 `name`、
  `last_login`，附带 `exp`/`iat`/`nbf`。
- 校验：`core/auth.py::decode_access_token`，过期抛 `AccessTokenError("Token has expired")`。
- 依赖：
  - `dependencies/auth.py::get_bearer_token` —— 缺失/非 Bearer 一律 401；
  - `get_current_user` —— 返回 `UserResponse(id, email, name, role, last_login)`；
  - `get_admin_user` —— 非 `admin` 返回 403。
- 用户表 `users` 由平台身份（`sub`）作为主键，**不自建第二套登录体系**。

### 5.4 登出

`GET|POST /api/v1/auth/logout` 返回 `{"redirect_url": build_logout_url()}`，回跳
`{FRONTEND_URL}/logout-callback`。地址构造失败时降级返回空串而不是 500——令牌清理已在前端
完成，这里的 500 会让用户停在原页面。

## 六、数据库与事务边界

### 6.1 连接管理

`core/database.py::DatabaseManager` 是全进程单例，引擎惰性构建并受 `asyncio.Lock` 保护
（并发冷启动不会建出第二个引擎）。URL 会被规范化为异步驱动（`postgresql → asyncpg`、
`sqlite → aiosqlite`），并剔除 asyncpg 不支持的查询参数（如 `channel_binding`）；命中
事务型连接池（URL 含 `pooler`/`pgbouncer`）时自动关闭 asyncpg 预备语句缓存。

连接池策略：

| 场景 | 策略 |
|------|------|
| 非 Lambda | `QueuePool`，默认 `pool_size=5`、`max_overflow=5`、`pool_timeout=30s`、`pool_recycle=280s`、`pool_pre_ping=true` |
| Lambda | 同上（保留小池以复用跨调用连接）；`DB_DISABLE_POOL=true` 时退化为 `NullPool` |
| SQLite | 不调池参数（`aiosqlite` 自行选择池实现） |

**为什么不是单连接**：生成阶段在进程内后台任务里推进，浏览器同时在轮询。池只有 1 条连接时，
两者互相阻塞，表现为 `QueuePool limit ... timed out` 并放大为 5xx/502。默认 `5 + 5` 是
「小但大于一」的折中。

### 6.2 会话与事务边界（硬性规范）

- `get_db()` 只负责**产出请求级会话并在退出时关闭**，不代做 `rollback`：
  对已失败的 asyncpg 连接二次回滚会抛 "cannot switch to state"。事务归属调用方（服务层负责 `commit()`）。
- 会话工厂 `expire_on_commit=False`，避免提交后触发同步惰性加载。
- **慢调用前后不得持有事务**。凡是混了模型调用、对象存储、支付或第三方 HTTP 的接口，必须拆成
  「短事务写入 → 无连接慢调用 → 短事务回写」。例外情况：纯数据库读写接口可保持单会话。
- 只读快照需要看到其它会话的最新写入时，用 `.execution_options(populate_existing=True)` 强制
  以库内当前值为准（刷新发生在异步查询内部，不会触发 `MissingGreenlet`）。

## 七、数据模型

| 表 | 关键字段 | 说明 |
|----|---------|------|
| `users` | `id`(=平台 sub) `email` `name` `role` `last_login` | 平台身份映射，不自建账号 |
| `oidc_states` | `state` `nonce` `code_verifier` `expires_at` | 登录流程临时数据，一次性消费 |
| `projects` | `user_id` `name` `prompt` `status` `current_stage` `template_key` `preview_url` `latest_version` `spec_json` `plan_json` `artifact_key` `test_report_json` | 一个生成项目 |
| `build_tasks` | `user_id` `project_id` `run_no` `stage` `stage_name` `stage_order` `stage_state` `stage_log` `error_message` `output_summary` | 六阶段任务，按 `run_no` 分批 |
| `project_versions` | `user_id` `project_id` `version` `diff_summary` `files_key` | 版本链 |
| `usage_quotas` | `user_id` `period` `plan` `used` `quota_limit` | 按自然月计数配额 |
| `test_cases` | `user_id` `project_id` `title` `case_type` `preconditions` `steps` `expected` `assertion` `source` `case_state` | 项目测试用例。`case_type ∈ {structure, interaction, content}`；`source ∈ {auto, manual}`；`case_state ∈ {active, disabled}`，停用用例不参与执行；`assertion` 是可在产物源码中匹配的片段 |
| `test_runs` | `user_id` `project_id` `status` `triggered_by` `total` `passed` `failed` `duration_ms` `results_json` `error_message` | 每次测试执行的统计与逐用例结果。`status ∈ {passed, failed}`，`triggered_by` 记录发起人，`results_json` 保存逐例明细 |

约定：

- 所有业务表带 `user_id` 且**按用户隔离**，接口层用 `current_user.id` 过滤，不做跨用户读取。
- `created_at` / `updated_at` 由 ORM 维护，业务代码不手动赋值。
- **产物不入库**：库里只存对象键 `artifact_key`（以及 `files_key`），可访问地址每次请求即时解析。

## 八、六阶段生成流水线

### 8.1 阶段定义（`services/generation.py::STAGES`）

| 顺序 | stage | 名称 | 真实工作 | 产出字段 |
|------|-------|------|---------|---------|
| 1 | `parsing` | 解析需求 | `deepseek-v4-flash` 结构化需求 | `spec_json`、`name` |
| 2 | `planning` | 生成方案 | `claude-opus-5` 产出文件清单与组件树 | `plan_json` |
| 3 | `coding` | 编写代码 | `claude-opus-5` 生成单文件应用并上传对象存储 | `artifact_key` |
| 4 | `building` | 构建校验 | 回读产物，结构/行为自检 | `test_report_json` |
| 5 | `testing` | 测试验证 | 基于真实产物内容产出测试报告 | `test_report_json` |
| 6 | `deploying` | 发布预览 | 解析公开地址并校验可达 | `status=succeeded`、版本摘要回填 |

状态取值：`build_tasks.stage_state ∈ {pending, running, done, failed}`；
`projects.status ∈ {queued, pending, running, succeeded, failed}`，其中
`TERMINAL_STATUSES = {succeeded, failed}`。

失败**不清空**：停在失败阶段并把真实报错写入 `error_message` / `stage_log`，用户可重试。

### 8.2 三段式阶段执行（`services/generation.py::advance_pipeline`）

```
① _claim_next_stage  短事务：原子抢占 pending → running，复制只读输入快照
② _run_stage_work    无数据库连接：模型调用 / 对象存储读写（单次最长 180s）
③ _finish_stage      短事务：回写结果；仅当阶段仍为 running 时才写
   _abort_stage      短事务：写入可见失败态 + 首轮额度退款判定
```

返回值语义：`advanced`（本次执行了一个阶段）、`finished`（已终态或无待执行阶段）、
`idle`（阶段被其它执行者持有，本次不重复执行）。

抢占与回收：

- `_claim_stage` 用 `UPDATE ... WHERE id=? AND stage_state='pending'` 的条件更新实现原子抢占，
  多进程部署也不会重复执行同一阶段。
- `_recover_stale_stage` 回收失去执行者的 `running` 阶段：超过
  `STAGE_STALE_SECONDS = 600` 未回写，或早于「本进程启动时刻」（`orphan_before`，由启动恢复传入）
  即判定中断，标记为可见失败允许重试。
- `_finish_stage` / `_abort_stage` 在阶段已不是 `running`（被回收或项目已删除）时丢弃本次结果，
  不覆盖更新后的状态。

### 8.3 后台工作器（`services/pipeline_runner.py`）

| 常量 | 值 | 含义 |
|------|----|------|
| `MAX_STAGES_PER_RUN` | 12 | 单轮最多推进阶段数（正常 6 个，重试后计数） |
| `RESUME_PROJECT_LIMIT` | 20 | 启动恢复最多接管项目数 |
| `INLINE_KICK_SECONDS` | 10.0 | 请求返回前留给工作器的起步时间 |

- `schedule` / `kick`：进程内按 `project_id` 去重，同一项目同时只有一个工作器；
  `kick` 用 `asyncio.wait_for(asyncio.shield(task))` 限时等待——超时只结束本次等待，**不取消阶段执行**。
- 设计同时兼容两种部署：常驻进程下请求很快返回、阶段在后台跑完；无服务器环境下每次轮询都会
  再推进一段，进度始终向前，且单个请求永不逼近网关时限。
- `resume_pending_projects`：启动时接管 `queued/pending/running` 项目，把启动时刻之前的
  `running` 阶段当作孤儿立即回收，`pending` 阶段继续推进。

### 8.4 配额与退款

- 默认套餐 `FREE_PLAN = "free"`，`FREE_QUOTA = 20`，周期为 UTC 自然月（`YYYY-MM`）。
- `get_or_create_quota` 幂等创建当期配额行，并发插入冲突时回滚并复用已存在行。
- `consume_quota` 用条件原子更新扣减：
  `UPDATE usage_quotas SET used = used + 1 WHERE id = ? AND used < quota_limit`；
  未命中行即抛 `QuotaExceeded`，接口返回 **429**，并提示本周期已用/总额度。并发首建不会超扣。
- `refund_quota` 用 `GREATEST(used - 1, 0)` 退还。
- **退款规则**：仅当「首轮（`run_no == 1`）且尚无产物（`artifact_key` 为空）」时退还一次；
  第 2 轮起都是免费重试，一律不退。因此每个项目最多退一次，不会重复退款。

### 8.5 重试

`POST /api/v1/generation/projects/{id}/retry` 开启新一批任务（`run_no + 1`），**不重复扣配额**：

- 若 `spec_json` 已落库且上一轮失败不在解析阶段，则解析阶段直接标记为 `done`（复用结果，省一次模型调用）。
- 上一轮失败的 `error_message` 经 `generation_ai.build_repair_hint` 生成修复提示，注入模型上下文。

### 8.6 测试报告口径

`_check_report(html)` 依据真实产物内容计算，不是固定文案：

- 结构校验（`STRUCTURE_CHECKS`）：`<!doctype html>`、`<html></html>`、`<head></head>`、`<body></body>`、`<title>`；
- 冒烟检查（`BEHAVIOR_CHECKS`）：脚本、交互元素（button/onclick/addeventlistener）、布局样式（style/display/grid/flex）、中文文案；
- 实现覆盖：7 个标记（`<style`、`display`、`<script`、`onclick`、`addeventlistener`、`grid`、`flex`）命中比例；
- 结构校验全通过才判定构建通过；否则抛出可见失败。

## 九、API 清单

所有路由前缀均为 `/api/v1/`（自动发现与网关代理的前提）。除下方标注为公开的接口外，均需
`Authorization: Bearer <app_token>`。

### 生成编排 `/api/v1/generation`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/projects` | 创建生成任务：落库项目与六阶段任务并占用一次额度，**不调用模型**，返回待执行快照（201）。额度用尽 429，落库失败 500 |
| GET | `/projects` | 当前账号项目列表（按创建时间倒序，`limit`/`skip`），同时返回配额 |
| GET | `/projects/{project_id}` | 流水线快照；非终态时先 `pipeline_runner.kick` 确保后台在推进 |
| POST | `/projects/{project_id}/retry` | 失败后重跑，不重复扣额度 |
| GET | `/projects/{project_id}/versions` | 版本链（按版本号倒序） |
| DELETE | `/projects/{project_id}` | 删除项目及其任务与版本记录 |
| GET | `/templates/{template_key}` | 模板推荐方案（确定性数据，不消耗模型额度） |

### 测试能力 `/api/v1/testing`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/projects/{project_id}/suite` | 测试面板快照：用例列表、最近运行与运行历史 |
| POST | `/projects/{project_id}/cases/generate` | 基于方案与真实产物生成 6-10 条用例（`claude-opus-5`），替换既有 `auto` 用例，保留手动用例 |
| POST | `/projects/{project_id}/cases` | 手动新增用例 |
| PUT | `/cases/{case_id}` | 编辑用例（标题、类型、步骤、预期、断言、启用状态） |
| DELETE | `/cases/{case_id}` | 删除用例；历史运行记录保留 |
| POST | `/projects/{project_id}/runs` | 在当前产物上执行全部启用用例并落库 |
| GET | `/runs/{run_id}` | 单次运行详情（逐例结果与失败原因） |

约束：没有 `artifact_key` 的项目拒绝生成用例与执行（无产物可测，返回可见错误）；生成与执行会回读对象存储中的真实产物，断言通过与否由产物内容决定，**不由模型判定**；`artifact_key` 为空或回读失败即失败，不伪造通过。删除项目会一并清理该项目的用例与运行记录。

响应核心结构 `PipelineResponse`：`run_no`、`spec`、`stages[]`、`test_report[]`、`quota`、`project`。
`project.preview_url` 由后端按 `artifact_key` 即时解析，**不落库**。

三个写接口与详情接口都在「等待工作器之前归还请求连接」，随后用 `_snapshot_with_quota`
（独立短会话）读取最新快照与额度，保证响应是最新状态且不占用连接。

### 认证 `/api/v1/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/login` | 公开。发起 OIDC + PKCE，302 到平台授权页 |
| GET | `/callback` | 公开。换取 token、校验 id_token 与 nonce、签发应用 JWT，302 回前端 |
| POST | `/token/exchange` | 公开。平台令牌换取应用令牌 |
| GET | `/me` | 返回当前用户信息 |
| GET/POST | `/logout` | 返回平台登出地址（构造失败降级为空串） |

### 用户 `/api/v1/users`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/profile` | 当前用户资料 |
| PUT | `/profile` | 更新 `name` |

### 实体 CRUD（自动生成）`/api/v1/entities/{projects|build_tasks|project_versions|usage_quotas}`

每个实体提供 `GET ""`（列表）、`GET /{id}`、`POST ""`、`POST /batch`、`PUT /{id}`、
`PUT /batch`、`DELETE /{id}`、`DELETE /batch`。列表支持 `query`（JSON 过滤）、`sort`
（`-` 前缀降序）、`skip`、`limit`（≤2000）、`fields`。写入与删除均校验 `user_id` 归属。

### AI 能力 `/api/v1/aihub`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/gentxt` | 文本生成；`stream=true` 走 SSE（`data: {"content": ...}`，结束发 `[DONE]`） |
| POST | `/genimg` | 文生图 / 图生图（传 `image` 即走编辑） |
| POST | `/genvideo` | 文生视频 / 图生视频 |
| POST | `/genaudio` | 文本转语音（TTS） |
| POST | `/transcribe` | 语音转文字（STT） |
| POST | `/analyzepdf` | 单份 PDF 问答或结构化抽取 |

错误映射：入参非法 400，AI 配置缺失 503，其余 500；`extract_error_message` 会从
`{"error":{"message":...}}`、Python 字面量字典或带前缀的字符串中抽出可读消息。

### 对象存储 `/api/v1/storage`

`POST /create-bucket`（管理员）、`GET /list-buckets`、`GET /list-objects`、
`GET /get-object-info`、`POST /rename-object`、`DELETE /delete-object`、
`POST /upload-url`、`POST /download-url`。下载 URL 的 `content_type` 按对象键后缀推断。

### 管理与健康

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 公开。进程存活探针 |
| GET | `/database/health` | 公开。执行 `SELECT 1`，返回 `healthy`/`unhealthy` |
| GET/PUT/POST/DELETE | `/api/v1/admin/settings[/{backend\|frontend}/{key}]` | 管理员读写 `.env` 配置项 |

## 十、AI 调用约定（`services/generation_ai.py`）

| 常量 | 值 |
|------|----|
| `PARSE_MODEL` | `deepseek-v4-flash` |
| `CODE_MODEL` | `claude-opus-5` |
| `MODEL_CALL_TIMEOUT_SECONDS` | `180.0` |
| `ENTRY_FILE` | `index.html` |

统一调用链：**提示词约束 → 完整输出 → JSON 块提取 → 本地容错 → 必填字段校验 → 一次模型修复重试 → 抛错**。

- 硬超时：`asyncio.wait_for(..., timeout=180)`。上游卡死必须变成可重试的可见失败，
  而不是把请求挂到网关超时。
- 异常收敛：SDK 抛出的额度不足（`insufficient_ai_balance`）、限流（429）、鉴权（401/403）、
  连接异常等一律翻译为 `GenerationAIError` 并给出中文可读原因。**不得让上游异常穿透成 500**
  ——穿透会跳过失败落库与额度退款。
- 结构化输出容错：`_extract_json_block` 剥离 ```json 包裹与前后缀说明；
  `_local_fix` 先清尾随逗号再补全被截断的字符串与括号；仅在本地修复仍失败时才发一次修复调用。
- 字段校验：`pages` ≥ 2、`entities` ≥ 1、`stack` ≥ 1 且必须包含 React；文件清单必须含
  `index.html`；入口内容必须含 `<html`、`</html>`、`<body>`，否则抛错。
- 生成的应用为**自包含单文件 HTML**：内联全部 CSS/JS，不引用外部资源，深色背景 `#0b0c0e`、
  主色 `#c8f751`、中文文案。

## 十一、对象存储与产物

`services/generation_artifacts.py`：

- Bucket：`generation-artifacts`；对象键：`projects/{project_id}/v{version}/index.html`。
- 上传：取预签名上传地址后 `PUT` 内容，`Content-Type: text/html; charset=utf-8`。
- 回读：取下载地址后 `GET`，用于构建校验与测试验证。
- 发布：`public_url()` 解析出可访问地址，`is_reachable()` 校验 200 且响应含 `<html` 才允许发布。
- 库内只存 `artifact_key`；签名地址有时效，落库会过期，因此每次请求即时解析。

`services/storage.py` 基于平台 OSS 服务封装：统一 `Authorization: Bearer <OSS_API_KEY>`，
校验响应 `code == 0`，非 0 抛出含 `error`/`message` 的 `ValueError`；预签名使用 `expires_in: 0`
（由平台侧决定有效期语义）。

> 已知待办：删除项目目前只清理业务表，**不清理对象存储产物**，会产生孤儿对象。若需要彻底清理，
> 应在删除接口中追加 `object_key` 删除。

## 十二、可靠性设计

### 12.1 502/524 根因与修复

问题表现：`POST /api/v1/generation/projects` 与轮询接口经 Cloudflare 返回 502/524。根因有三：

1. **长事务占用连接**：阶段执行在整个慢模型调用期间持有数据库连接；
2. **连接池过小**：无服务器分支原先 `pool_size=1 / max_overflow=0 / pool_timeout=5s`，
   单连接会让后台阶段与浏览器轮询互相阻塞，5 秒获取超时即抛 `QueuePool limit`；
3. **请求持连接等待工作器**：请求在等后台 worker 时仍占用连接，而 worker 自身也要连接，形成自锁式争抢。

对应修复：

| 修复 | 位置 |
|------|------|
| 创建接口不再同步调用模型，只做两次落库 | `services/generation.py::create_project` |
| 阶段执行拆为短事务抢占 → 无连接慢调用 → 短事务回写 | `services/generation.py::advance_pipeline` |
| 连接池放宽为 `5 + 5`、`pool_timeout=30s`（均可环境变量覆盖） | `core/database.py` |
| 请求先归还连接再等待工作器，快照用独立短会话重读 | `routers/generation.py` |
| 阶段执行搬到后台工作器，接口只做快照与调度 | `services/pipeline_runner.py` |

### 12.2 幂等与恢复

- 同一项目进程内工作器去重；跨进程靠数据库原子抢占，不会重复执行阶段。
- `600` 秒陈旧阶段回收；进程重启由启动恢复 + 用户访问双重兜底，项目不会永久停在「生成中」。
- 建连惰性初始化受锁保护，并发冷启动不会建出第二个引擎。

## 十三、验证方式

后端改动后按下面顺序自测：

```bash
cd app/backend
python -m py_compile <changed_python_files>   # 或 mgx-pycheck
python -c "import main; import services.generation; import services.pipeline_runner"
```

仓储内验证脚本：

| 脚本 | 覆盖 |
|------|------|
| `verify_stage3.py` | 真实 AI 调用、对象存储上传与回读、预览地址可达性、iframe 兼容性（无 `X-Frame-Options`/CSP 阻断） |
| `verify_pipeline.py` | 六阶段端到端：状态 `succeeded`、结构校验、冒烟检查、覆盖率、版本摘要、重试 `run_no` 递增且不重复扣额 |
| `verify_quota_refund.py` | 模型失败路径：额度回到 `0/20`、无残留项目、无残留阶段任务 |
| `verify_gateway_timeout.py` | HTTP 级：创建耗时、轮询耗时、并发轮询、无 5xx、无 `QueuePool` 超时 |
| `verify_test_suite.py` | 阶段四测试链路：无产物项目拒绝生成与执行、通过/失败统计与产物一致、停用用例被排除、运行历史倒序、跨用户项目与运行访问均被拒、删除用例不影响历史、项目删除后用例与运行清理干净 |

注意：脚本依赖平台 AI 额度；额度不足时失败原因是 `insufficient_ai_balance`（HTTP 403），
属于外部额度问题而非代码缺陷，此时阶段会落为可见失败并触发首轮退款。

## 十四、开发规范要点

1. 新增接口放在 `routers/` 下并定义 `router = APIRouter(prefix="/api/v1/...")`，无需手动注册。
2. 业务逻辑写在 `services/`，路由只做参数校验、鉴权与响应组装。
3. 所有读写都必须带 `user_id` 过滤，禁止跨用户访问；项目未命中一律 404（不泄露存在性）。
4. 慢外部调用前后不得持有事务；需要跨会话最新值时用 `populate_existing`。
5. 上游异常必须收敛为业务异常并落库为可见失败；不要让异常穿透成 500。
6. 不要伪造成功态：预览地址、测试报告、版本摘要都必须来自真实产物。
7. 不要改动受保护路径（`core/**`、`models/**`、`main.py`、`lambda_handler.py`）。
8. 前端统一通过 web-sdk（`client.apiCall.invoke` / `client.auth.*` / `client.storage.*`）调用，
   详见 `skills_docs/`。
