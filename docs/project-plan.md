# Facet 项目开发计划

日期：2026-10-02

状态：Phase 0 完成，Phase 1 开发计划

目标：交付可自托管的 Gmail 选择性投影服务，并为后续数据源保留清晰的扩展位置。

Facet 为 AI agents 提供经过用户选择的数据视图。第一期以主 Gmail 为数据源，将允许披露的完整会话投影到独立 Gmail；用户可以直接查看目标邮箱，确认 AI 被授权读取的内容。

这份计划定义产品范围、工程阶段、验收和发布条件。产品承诺见 [产品契约](product-contract.md)，实现细节见 [Gmail 投影规格](gmail-projection-spec.md)，运行面板见 [Dashboard 规格](dashboard-spec.md)，已完成的实测见 [Phase 0 结果](phase-0-gmail-spike-results.md)。原始附件作为设计参考；本计划与上述仓库文档反映讨论后的决定。

## 项目边界和已有决定

| 项目 | Phase 1 决定 |
| --- | --- |
| 运行方式 | 单用户、自托管、单进程、Docker Compose、SQLite |
| 数据源和目标 | 一对不同的 Gmail 账号；source 为唯一事实来源 |
| 投影单位 | 一封邮件命中后，整个 source thread 纳入跟踪 |
| 初始历史 | 最近六个月内命中的 thread，复制其完整历史 |
| 后续同步 | History polling，包含用户从 source 发出的回复 |
| 默认 source 权限 | `gmail.readonly`；支持 CLI 和观察手工 action labels |
| 便利模式 | 显式开启 `gmail.modify`，自动维护 action labels |
| target 权限 | `gmail.insert` 和 `gmail.readonly`，用于写入、回读和恢复 |
| 目标邮箱展示 | 默认只在 All Mail；专用标签和 Inbox 设置为可选项 |
| BlackList | 阻止该 sender 的新 admission，停止当前 thread 后续同步，保留已投影历史 |
| 撤回和清理 | 保存 provenance 和映射；purge、retention 和删除权限留到后续 |
| 交付保证 | 持久队列、可恢复、重复抑制；跨 Gmail 和 SQLite 不承诺 exactly once |
| AI 产品责任 | connector 的授权、索引、附件读取和检索由各 AI 产品负责 |
| Web Dashboard | 第一期开启只读状态、进度、数量、异常和诊断，不展示邮件细节 |
| Web 访问边界 | Facet 提供 HTTP，前置 Nginx 负责 HTTPS 和用户认证 |
| 内容存储 | DB 只保存必要 metadata 和状态；默认 raw 仅驻内存，不建立磁盘 spool |

Facet 的验收终点是邮件被正确写入 target，并能通过 Gmail API 和 Gmail UI 回读。AI connector 兼容性可以作为外部使用报告，但不阻塞开发或发布，也不计入 Facet 同步延迟。

## Phase 0 结论和覆盖边界

实测已确认 raw MIME 内容、旧日期、Message-ID、附件和目标会话可以保留；source History 包含入站、用户发出邮件和 action label 事件。用户已确认四封邮件组成的目标会话可见，并确认含三个 PDF 的邮件和附件能打开。

正式实现必须吸收三个结论：Gmail 会增加 transport header，因此全 raw 哈希不能作为跨邮箱一致性判据；重复 `messages.insert` 会产生重复邮件；insert 成功但本地未记录时，target 搜索可用于恢复，但实测一次成功不代表搜索延迟存在固定上限。

Phase 0 验证了数据面的可行性。六个月 backfill、长期运行、History 404、规则执行、可信发件人判断和生产队列仍需要在 Phase 1 验收。原样复制已有 `Fwd:` 邮件不会消除其原始标题；Facet 本身不生成转发邮件。

2026-10-02，用户报告已清理 source action labels 和 target 旧邮件。只读检查确认三种 action labels 已不存在，但当时 target API 仍返回八封普通邮件和一个草稿，且两个已验证的 spike 样本仍为无标签邮件。正式初始化重新建立数据库、账号绑定和 H0，不导入 spike cursor 或旧映射；在 preview 中核对实际 target 内容，不能将用户的清理操作直接等同于邮箱 API 已完全为空。

## Phase 1 功能范围

第一期包含以下完整使用路径：

1. 初始化本地配置和数据库，通过 Desktop OAuth 分别授权 source 和 target。
2. 预览初始规则命中的 thread 数量和完整 thread 披露范围，显式启动 backfill。
3. 从最近六个月的命中邮件发现 thread，复制其全部可用消息。
4. 用 History 增量同步已跟踪 thread，并按规则纳入新的 thread。
5. 用 CLI 或 `AI/AddSender`、`AI/AddDomain`、`AI/BlackList` 调整规则。
6. 在断网、限流、重启和授权故障后保留工作，恢复后继续。
7. 用 Web Dashboard、status、doctor、审计记录和定期校对说明当前进度、异常与缺失。
8. 通过 Compose 长期运行，按文档备份、恢复和升级。

第一期不实现 agent 代发、双向同步、source 状态完整复制、多租户、Web 邮件浏览或规则编辑、LLM 自动分类、通用 MCP、其他邮件 provider 或自动删除 target 邮件。Dashboard 仅用于只读运维观察，setup 与服务控制仍使用 CLI。

## 工程架构

采用 Python 3.12 及以上、Google 官方 Python 客户端、SQLite 和一个后台调度进程。现有 `facet_spike` 保留为实验工具；正式服务放在 `src/facet/`，只迁移已验证且经过测试的 OAuth、账号检查和 MIME 分析逻辑。

```text
Source Gmail
    |
    +-- discovery 和 History poller
    |          |
    |          v
    |    SQLite events / rules / jobs / mappings / audit
    |          |
    +-- raw --> thread 串行 worker --> Target Gmail
                           ^                |
                           +-- reconcile <--+
```

SQLite 保存业务状态和 provenance。Poller 先将事件持久化为 jobs，再推进 History cursor。Worker 按 thread 串行执行，跨 thread 有限并发；target 故障不阻止 source 事件持续入库。Reconcile 比较状态和 ID 集合，按需补齐，不做全量重复复制。

第一期只运行一对账号、一个 projection。数据库使用 `projection_id` 和明确的 source/target binding，为以后扩展保留隔离能力；本期不建立通用 provider 框架。

同一进程提供 HTTP Dashboard 和聚合状态 API，读取运行快照，不读取或返回邮件内容，不因浏览器刷新触发 Gmail 请求。静态前端与后端一起打包；Nginx 承担 HTTPS 和访问认证。

## 开发阶段和验收门槛

以下阶段按顺序交付。每阶段都包含实现、针对性测试和文档更新；阶段完成取决于验收证据，不依赖预计日期。

### M1 产品契约和正式工程基础

交付：正式 `facet` 包和 CLI 骨架、配置校验、账号 binding、SQLite schema v1 和迁移机制、rules 与审计存储、进程互斥、secret 管理，以及 Dashboard 使用的状态聚合与输出白名单。

范围：`pyproject.toml`、`src/facet/config.py`、`src/facet/db/`、`src/facet/gmail/oauth.py`、`src/facet/cli/`、相关 tests。既有 spike 继续可运行，不自动导入其 target 邮件或重跑实验。

补充酒店和银行的脱敏认证样本，定义可信 Gmail authentication header 的判断方式；银行实际域名未经确认不进入默认规则。现有 spike 的 pass 字符串统计只用于观测，不能直接成为 admission 判断。

验收：错误账号、token 对调、source 等于 target、无效配置和第二个写入进程均被拒绝；数据库约束与迁移可以重复执行；规则边界与伪造 authentication header 的测试通过。Doctor 和首次 preview 提示 target 的既有内容与缺失的 action labels；只读模式缺少 action labels 时，CLI 规则管理仍可使用。

### M2 持久化邮件和 thread 投影

交付：raw payload 内存传递、逐 thread worker、source 到 target 映射、目标回读、insert intent 与 pending recovery、retry 和错误分类。不建立 DB 内容缓存或磁盘 spool，重启后重新从 source 获取 raw。

范围：`src/facet/projection/worker.py`、`fidelity.py`、`recovery.py`、`src/facet/gmail/source.py`、`target.py`、`retry.py`，以及 DB repositories。

验收：普通邮件、HTML、内嵌图片、附件和非 ASCII 头部保真；正常恢复不产生重复；insert 后崩溃能恢复唯一候选；多个或不匹配候选进入待处理状态；真实回复和 sender 变化的会话保留内容。Thread fallback 只对已确认的 threading 错误执行，并保存实际 target thread 集合。DB、journal、日志和运行文件不保存完整邮件、正文或附件；source 删除后的恢复限制有明确状态。

此阶段提供手动选定 thread 的最小可用投影，不自动启动大规模历史复制。

### M3 规则和六个月 backfill

交付：sender 和 domain 规范化、PSL 域名提取、admission policy、候选 discovery、持久 backfill 队列、预览、暂停与恢复。

范围：`src/facet/projection/rules.py`、`authenticity.py`、`admission.py`、`backfill.py`、规则和 backfill CLI。

验收：最近三个月有命中、首封九个月前的 thread 被完整投影；九个月前即无后续命中的 thread 不进入初始 backfill；相似恶意域名被排除；不可信或不明确的发件人进入 review；分页中断可重扫并去重；新增规则不会隐式扩大历史披露。

Discovery 前记录初始化 History cursor。大量真实 backfill 的使用验证在 M4 可消费该 cursor 后执行，避免将尚未实现的增量恢复当成已完成能力。

### M4 History daemon 和定期校对

交付：30 秒 polling、History 分页和事件去重、无缝初始化、实时优先调度、History 404 恢复、每日 source 校对、每周 target 存在性校对、按需 target audit，以及只读 Web Dashboard。

范围：`src/facet/projection/history.py`、`reconcile.py`、`src/facet/runtime.py`、`src/facet/status/`、`src/facet/web/`、静态页面和同步状态 CLI。

验收：初始化期间的新邮件和自己回复不漏；target 中断时 cursor 仍在 durable jobs 后推进；恢复窗口覆盖整个停机期；校对发现 source 缺消息并补齐；target 手工删除或重复产生明确报告。恢复不能重新激活已 BlackList 的 thread，也不能把动态新规则自动应用到所有历史。

Dashboard 验收：显示状态、已完成数量、历史进度、积压、异常分类和诊断，数据过期有提示；Discovery 未完成不虚构总量；重试不重复计数；所有 API 和页面都不包含邮件细节或原始异常。Web 请求不改变同步状态、不调用 Gmail，桌面与手机均可查看关键状态。

M4 完成后，形成可通过 CLI 配置、带只读 Dashboard、可长期同步的 Gmail alpha。

### M5 Gmail 规则学习

交付：三种 action labels、按 History record 和 thread 聚合命令、own-address 排除、BlackList 停止 tracking、只读和便利两种模式。

范围：`src/facet/projection/actions.py`、`src/facet/gmail/labels.py`、CLI review 和 mode 切换。

验收：thread 上一次操作只产生一个命令；最新一封是自己回复时学习最近 external sender；命令重放不会重复学习；只读模式不调用 source mutation；便利模式在命令持久化后才清理标签；BlackList 阻止尚未开始的旧 jobs。切换模式要检查实际授权，不能自动扩大 scope。

现有 Apps Script 留下的 action labels 作为 legacy 记录展示，首次启动默认不执行；用户可以明确导入，或移除再添加以触发新命令。

### M6 自托管交付和 v0.1 验收

交付：非 root 镜像、Compose、配置示例、HTTP Dashboard、Nginx proxy 示例、healthcheck、backup 和 restore CLI、中英文使用文档、离线 CI、显式开启的真实 Gmail 集成测试、发布检查表。应用不内置 HTTPS 和 Web 用户认证。

范围：`Dockerfile`、`compose.yaml`、`config.example.yaml`、`.github/workflows/`、README、部署和运维文档、`tests/integration/`。

验收：全新环境可按文档完成授权和启动；本地磁盘 volume 中的 DB、凭据和 pending jobs 在重建容器后保留，raw 由 source 重新读取；备份恢复演练通过；授权撤销后不丢 jobs；大附件、磁盘压力和 target 故障不拖死无关 thread；日志和交付文件中没有正文、token 或私密测试数据；Dashboard 经 Nginx 可访问，UI、响应和诊断导出均通过隐私检查。

在指定的自托管主机进行至少 72 小时使用验证，跨一次 restart、token refresh 和故障恢复，记录 Facet 同步延迟与异常。这个时长是本计划的发布检查建议，不代表已验证长期运行。

## 测试计划

| 场景 | 预期行为 | 主要阶段 |
| --- | --- | --- |
| Raw 与附件 | 关键原始头部保留，MIME payload 和附件 hash 一致 | M2 |
| Date 非法或偏差 | 不丢内容，记录时间降级和排序差异 | M2 |
| Thread 重建 | 正常会话合并；fallback 映射完整可审计 | M2 |
| Insert 后 crash | 唯一且内容匹配的候选被绑定；模糊结果不盲目重试 | M2 |
| Message-ID 缺失或重复 | 不能只凭 Message-ID 判定同一封；进入受限恢复或 review | M2 |
| 六个月边界 | 用固定截止时间发现候选，纳入后复制完整 thread | M3 |
| Domain 和真实性 | PSL、子域边界、认证来源、alignment 和未知结果均有覆盖 | M1 M3 |
| 初始化和分页 crash | H0 之前 discovery 与 H0 之后 History 共同覆盖，事件可重放 | M3 M4 |
| 收信和自己回复 | 自动投影；已 tracked thread 的后续 sender 变化保留 | M4 |
| History 404 | 对 active threads 补漏，并恢复停机窗口内 admission | M4 |
| 新规则和 reconcile | 未来生效与显式历史回扫边界不被校对绕过 | M3 M4 |
| Action labels | 多 message 事件聚合；legacy labels 和重复执行受控 | M5 |
| BlackList 竞争 | 未开始的 jobs 被取消；已经在途的 insert 可能完成并被记录 | M5 |
| 故障与部署 | 限流、失效凭据、磁盘满、退出和备份恢复都保留可解释状态 | M2 M6 |
| Dashboard 统计 | 总量未知、重放、部分失败和快照过期都真实显示 | M3 M4 |
| Dashboard 隐私 | HTTP、DOM、前端状态、诊断和导出中无邮件字段或原始错误 | M1 M4 M6 |
| DB 内容边界 | 不保存 raw、正文、附件或完整 headers，重启重新取 source | M1 M2 M6 |

规则、状态机和 crash points 用离线测试验证；Gmail 日期、thread 和 attachment 行为用真实账号验证。CI 默认不持有 Gmail 凭据。真实集成测试限定已选定的测试邮件与 thread，不发送邮件，也不自动删除既有 target 内容。

## 发布标准和运行指标

v0.1 发布须完成 M1 至 M6，公开已知限制，并留存真实 Gmail 验收证据。任何被选中但尚未投影的邮件必须能在队列、review 或明确终止状态中解释，不能静默消失。

性能目标为正常 API、有效授权且没有积压时，新 source 消息到 target 插入并完成回读的 P95 小于 60 秒。记录 source 时间、事件被发现时间、入队时间、target 成功时间，分别报告 polling 延迟、排队时间和处理时间；历史 backfill 单独统计。第三方索引延迟不在指标内。

Dashboard 至少显示 source/target 角色的授权状态、权限模式、initialization 进度、最后成功 History 时间、队列深度、最老 job 年龄、tracked threads、成功邮件数、review 和异常分类数量、最近 reconcile 结果、资源状态与 schema version。账号地址、对象 IDs、邮件字段和本地路径仅按必要性保留在内部状态，不进入 Web 输出。

正式日志和公开诊断不包含正文、raw、附件、subject、sender 或 token，DEBUG 也不能绕过该边界。DB 只持久化同步所需的 metadata、rules、状态和受控错误码。Raw 在处理期间驻留内存，不存 DB 或磁盘，完整内容仍在 source/target Gmail。

## 后续路线

| 阶段 | 目标 | 开始条件 |
| --- | --- | --- |
| Phase 1 | Gmail 内容投影和可恢复自托管服务 | 当前计划 |
| Phase 1 后续 | 显式撤回、purge、retention、目标重复修复 | 先定义删除语义，再单独选择权限 |
| Phase 2 | 更好的 setup 和规则管理体验；评估日历或文档投影 | Gmail 持续使用反馈证明需要 |
| 后续独立提案 | Agent 以 primary 身份发送、其他 provider、复杂 topic rules | 单独确认产品和权限契约 |

数据源扩展复用 provenance、policy、queue 和 checkpoint 的概念；各 provider 的对象模型与目标实现单独设计，避免将 Gmail thread 当成所有数据源的通用单位。

## 开工前和发布前需要收敛的事项

可以立即开始 M1，不需要先确定所有后续事项。

- M1 至 M3：验证银行实际 sender domains 和认证样本；未确认项保持关闭或 review。
- M2：校准 pending recovery 的多次搜索等待策略；不以一次 spike 的 11.8 秒观测作为固定保证。
- M6：选择实际 dogfood 主机与 volume 路径，核对 NAS 使用本地磁盘而非网络文件系统。
- 用户已确认 [GhostFlying/facet](https://github.com/GhostFlying/facet) 使用 public 可见性和用户账号的 GitHub noreply 提交邮箱；推送与 CI 进度见 [开发状态](development-status.md)。
- 正式发布前：确定许可证和镜像发布位置；源码仓库公开不代表产品发布或部署已经获授权。

下一步交付 M1：正式配置、账号 binding、SQLite schema 和 CLI 基础。每次后续实施前将该阶段的具体文件改动与验收更新到本计划或对应实施记录。
