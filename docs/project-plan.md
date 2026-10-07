# Facet 项目开发计划

日期：2026-10-03

状态：Phase 0 完成；用户已于 2026-10-02 批准 Phase 1 G0（精确 `caba7c7`），
总计划 PR #2 已 merged。2026-10-03 根据用户纠偏重排第一条产品交付：第一期主线是
自动 discovery/backfill、History 增量、手工 action-label 规则更新和可恢复投影；生产能力与
G1-G6 仍未实现/验收。

目标：交付可自托管的 Gmail 选择性投影服务，并为后续数据源保留清晰的扩展位置。

Facet 为 AI agents 提供经过用户选择的数据视图。第一期以主 Gmail 为数据源，将允许披露的完整会话投影到独立 Gmail；用户可以直接查看目标邮箱，确认 AI 被授权读取的内容。

这份计划定义产品范围、工程阶段、验收和发布条件。产品承诺见 [产品契约](product-contract.md)，实现细节见 [Gmail 投影规格](gmail-projection-spec.md)，运行面板见 [Dashboard 规格](dashboard-spec.md)，已完成的实测见 [Phase 0 结果](phase-0-gmail-spike-results.md)。原始附件作为设计参考；本计划与上述仓库文档反映讨论后的决定。

完整工作包、依赖图、并行波次、验收和决定台账见
[Phase 1 执行计划](phase-1-execution-plan.md)，派工、模型、worktree、Issue/PR 和
独立 review 见 [agent 工作流](agent-workflow.md)。协调 agent 只负责推进和汇报，
工程由子 agent 完成；复杂包先 plan/review，再 implementation/review/acceptance。
进度通过 [Epic #1](https://github.com/GhostFlying/facet/issues/1) 和
[进度台账](phase-1-progress.md) 跟踪。用户已明确批准整体计划，技术 review/CI 没有
替代该决定；内部工作包按依赖和 agent review/验收门槛自主推进。重要产品、隐私或
authority 改变重新提交用户 review。

## 项目边界和已有决定

| 项目 | Phase 1 决定 |
| --- | --- |
| 运行方式 | 单用户、自托管、Docker 提供的 image 内单个前台 sync/HTTP 进程、SQLite；容器外运行环境不在 Facet 保证范围 |
| 数据源和目标 | 一对不同的 Gmail 账号；source 为投影内容的唯一事实来源 |
| target 外部写入 | 允许另行授权的外部 agent 发信/草稿，From 为绑定的 source，回复直接进入 source；Facet 自身不提供发信功能 |
| 投影单位 | 一封邮件命中后，整个 source thread 纳入跟踪 |
| 初始历史 | 最近六个月内命中的 thread，复制其完整历史 |
| 后续同步 | 第一阶段即包含 History polling、完整分页/cursor、事件持久化去重和用户从 source 发出的回复 |
| 默认 source 权限 | `gmail.readonly`；第一阶段只读观察手工 action labels 并更新规则 |
| 便利模式 | 显式开启 `gmail.modify`，自动维护 action labels |
| target 权限 | `gmail.insert` 和 `gmail.readonly`，用于写入、回读和恢复 |
| 目标邮箱展示 | 默认只在 All Mail；专用标签和 Inbox 设置为可选项 |
| BlackList | 阻止该 sender 的新 admission，停止当前 thread 后续同步，保留已投影历史 |
| 撤回和清理 | 保存 provenance 和映射；purge、retention 留到后续；2026-10-07 批准独立显式 target-cleanup 维护例外，非同步删除 |
| 交付保证 | 持久队列、可恢复、重复抑制；跨 Gmail 和 SQLite 不承诺 exactly once |
| AI 产品责任 | connector 的授权、索引、附件读取和检索由各 AI 产品负责 |
| Web Dashboard | 第一期开启只读状态、进度、数量、异常和诊断，不展示邮件细节 |
| 维护入口 | 完整 CLI 必交付：setup/config/auth、服务、规则/thread/backfill、queue/review、审计/受限修复、备份恢复迁移与升级；容器可运行且支持 offline 故障维护 |
| Web 访问边界 | Facet 提供 HTTP，前置 Nginx 负责 HTTPS 和用户认证 |
| 内容存储 | DB 只保存必要 metadata 和状态；默认 raw 仅驻内存，不建立磁盘 spool |
| 镜像交付 | Actions 发布 public `ghcr.io/ghostflying/facet`；main full-SHA 自动发布，PR 只构建，正式版本 tag 另确认 |

Facet 的验收终点是邮件被正确写入 target，并能通过 Gmail API 和 Gmail UI 回读。AI connector 兼容性可以作为外部使用报告，但不阻塞开发或发布。产品没有同步延迟承诺；不设置 P95、轮询间隔或端到端时限 gate。

## Phase 0 结论和覆盖边界

实测已确认 raw MIME 内容、旧日期、Message-ID、附件和目标会话可以保留；source History 包含入站、用户发出邮件和 action label 事件。用户已确认四封邮件组成的目标会话可见，并确认含三个 PDF 的邮件和附件能打开。

正式实现必须吸收三个结论：Gmail 会增加 transport header，因此全 raw 哈希不能作为跨邮箱一致性判据；重复 `messages.insert` 会产生重复邮件；insert 成功但本地未记录时，target 搜索可用于恢复，但实测一次成功不代表搜索延迟存在固定上限。

Phase 0 验证了数据面的可行性。六个月 backfill、长期运行、History 404、规则执行、可信发件人判断和生产队列仍需要在 Phase 1 验收。原样复制已有 `Fwd:` 邮件不会消除其原始标题；Facet 本身不生成转发邮件。

历史证据（2026-10-02）：用户报告已清理 source action labels 和 target 旧邮件。只读检查确认三种 action labels 已不存在，但当时 target API 仍返回八封普通邮件和一个草稿，且两个已验证的 spike 样本仍为无标签邮件。这不是当前部署许可。2026-10-07 的[产品契约](product-contract.md)修正了 2026-10-05 的 sole-mailbox-writer 假设：target 仍须新建、专用，但允许 source 身份的外部 agent 已发送邮件/草稿，不能用总邮件数为零作为持续运行门槛；其余意外未管理内容仍阻止新投影，不清理或认领。正式初始化不导入 spike cursor、旧映射或旧 target 邮件。

## Phase 1 功能范围

第一期包含以下完整使用路径：

1. 初始化本地配置和数据库，通过 Desktop OAuth 分别授权 source 和 target。
2. 通过完整同步命令按当前规则和默认固定六个月范围自动准备/start backfill；内部说明完整 thread 披露语义，不要求用户串 preview/start 或逐个选择 thread。细分命令保留用于维护和当前验证。
3. 从最近六个月的命中邮件自动 discovery，复制每个纳入 thread 的全部可用消息。
4. 第一阶段持续消费 History：分页、cursor、事件持久化/去重，处理 `messagesAdded` 和 action-label 事件，自动创建规则或 projection jobs。
5. 用 CLI 或只读观察 `AI/AddSender`、`AI/AddDomain`、`AI/BlackList` 调整规则；便利 label 清理后移。
6. 在断网、限流、重启和授权故障后保留工作，恢复后继续。
7. 用 Web Dashboard、status、doctor、审计记录和定期校对说明当前进度、异常与缺失。
8. 通过 Compose 长期运行，按文档备份、恢复和升级。

完整命令/JSON/退出码/确认/锁与各阶段验收见 [CLI 契约](cli-spec.md)。M1 的 CLI
foundation 是阶段性基础；G6 要求真实可维护的全套命令及容器 E2E，不以 help-only
骨架过关。Status/doctor 与停机 backup/restore/migrate/inspect 可以 offline 运行，
即使 invalid_grant 或 Gmail 不可用仍能看 pending。维护协调 DB+credential ownership。

第一期不由 Facet 实现 agent 代发/草稿创建、双向同步、source 状态完整复制、多租户、Web 邮件浏览或规则编辑、LLM 自动分类、通用 MCP、其他邮件 provider 或自动删除 target 邮件。允许外部 agent 发信/草稿不等于 Facet 提供发送 API、扩大 scope 或配置 send-as。收件人自动发现规则记录为后续项，不在本期实施或保存每封邮件的 To/Cc；回复进入 source 后仍按现有规则或 tracked thread 授权处理，不因 agent 联系过收件人而自动 admission。Dashboard 仅用于只读运维观察，setup 与服务控制仍使用 CLI。

## 工程架构

采用 Python 3.12 及以上、Google 官方 Python 客户端、SQLite 和 Docker image 内一个前台进程。Docker/Compose 负责生命周期和 restart；不实现独立 daemon、IPC、宿主机 service 安装或 request-receipt broker。容器外 Python/native/runtime 由使用方负责，Facet 不提供额外保证。现有 `facet_spike` 保留为实验工具；正式服务放在 `src/facet/`，只迁移已验证且经过测试的 OAuth、账号检查和 MIME 分析逻辑。

```text
Source Gmail
    |
    +-- discovery、backfill 和 History poller
    |          |
    |          v
    |    SQLite events / rules / jobs / mappings / audit
    |          |
    +-- raw --> thread 串行 worker --> Target Gmail
                           ^                |
                           +-- reconcile <--+
```

SQLite 保存业务状态和 provenance。Poller 先将事件持久化为 jobs，再推进 History cursor。Worker 按 thread 串行执行；第一阶段不把跨 thread 并发、公平调度或复杂 raw budget 作为交付前置，只保留 raw 仅内存和基本上限。Target 故障不阻止 source 事件持久入库。Reconcile 和高吞吐优化属于后续运维增强，不改变核心去重和恢复语义。

第一期只运行一对账号、一个 projection。数据库使用 `projection_id` 和明确的 source/target binding，为以后扩展保留隔离能力；本期不建立通用 provider 框架。

同一进程提供 HTTP Dashboard 和聚合状态 API，读取运行快照，不读取或返回邮件内容，不因浏览器刷新触发 Gmail 请求。静态前端与后端一起打包；Nginx 承担 HTTPS 和访问认证。

## 开发阶段和验收门槛

以下阶段按顺序验收。每阶段都包含实现、针对性测试和文档更新；阶段完成取决于验收
证据，不依赖预计日期。执行计划明确允许输入稳定的独立模块、设计和合成测试提前
并行；后阶段的提前实施不代表前阶段或后阶段 gate 已通过。真实 bulk backfill 等待
H0 消费和 gap 恢复能力，并受单独 Gmail 操作范围授权。

### M1 产品契约和正式工程基础

交付：正式 `facet` 包和 CLI 骨架、配置校验、账号 binding、SQLite schema v1 和迁移机制、rules 与审计存储、进程互斥、secret 管理，以及 Dashboard 使用的状态聚合与输出白名单。

范围：`pyproject.toml`、`src/facet/config.py`、`src/facet/db/`、`src/facet/gmail/oauth.py`、`src/facet/cli/`、相关 tests。既有 spike 继续可运行，不自动导入其 target 邮件或重跑实验。

银行实际域名未经确认不进入默认规则。按照 2026-10-05 用户决定，SMTP 认证与分类交给 Gmail；Facet 不独立验证 sender authentication，不以认证 headers 或 source-path attestation 阻塞规则 admission，也不声明邮件安全。

验收：错误账号、token 对调、source 等于 target、无效配置和第二个写入进程均被拒绝；数据库约束与迁移可以重复执行；规则边界和 metadata-only admission 测试通过，认证 headers 不影响规则决策。操作者声明新建专用 target 及允许的外部 agent 用途；target OAuth 后、首次 projection/insert 前只读核对账号 binding 和普通邮件/SENT/草稿/Spam/Trash。按产品契约分类的 source 身份未管理 SENT/DRAFT 不阻塞、不计投影成功、不自动绑定恢复；其他 unexpected/unmanaged 内容或 mismatch 保持 blocked/report-only，不认领、删除或清理。既有映射及独立证实的本系统 insert 结果优先，标签/From 不证明应用写入者或内容真实性。此条是验收要求而非新增 runtime 已实现证据。Doctor 提示缺失的 action labels；只读模式缺少 action labels 时，CLI 规则管理仍可使用。

### M2 自动 discovery、backfill、History 增量和投影核心（第一条可用产品能力）

交付：source/target adapter、自动 discovery、固定六个月 backfill、History polling 全分页和 cursor、事件持久化/去重、`messagesAdded` 与 readonly action-label 事件、规则更新（含 `effective_at`/generation）和 projection jobs、raw payload 内存传递、逐 thread worker、source 到 target 映射、目标回读、insert intent 与 pending recovery、restart continuation。不建立 DB 内容缓存或磁盘 spool，重启后重新从 source 获取 raw。

Preview/start 的范围校验、稳定 request key、epoch/H0 写入和 command journal 属于共享 DB owner 的持久化行为，不是 CLI 独有的旁路记录或第二条操作路径。

范围：`src/facet/projection/worker.py`、`fidelity.py`、`recovery.py`、`src/facet/gmail/source.py`、`target.py`、`retry.py`，以及 DB repositories。

验收：普通邮件、HTML、内嵌图片、附件和非 ASCII 头部保真；正常恢复不产生重复；insert 后崩溃能恢复唯一候选；多个或不匹配候选进入待处理状态；真实回复和 sender 变化的会话保留内容。Thread fallback 只对已确认的 threading 错误执行，并保存实际 target thread 集合。DB、journal、日志和运行文件不保存完整邮件、正文或附件；source 删除后的恢复限制有明确状态。

此阶段直接提供自动 discovery/backfill 和持续增量投影；不以手动选定 thread 或 one-shot 复制作为交付路径。按 2026-10-07 用户决定，完整 CLI 同步入口按当前规则和固定六个月窗口自动完成内部范围快照/start、历史补齐与增量运行，不要求用户手动串 preview/start；完整入口完全复用细分命令的业务操作。细分命令保留，用于维护和当前测试。独立 preview/setup 零 insert、H0/gap、映射去重、unknown 和停止 generation 等门槛不变。

### M3 History gap、校对、Dashboard 和长期运行增强

交付：History 404/gap recovery、source reconcile、target audit、只读 Web Dashboard、基础 queue/recovery/doctor 汇总和长期运行状态。

范围：`src/facet/projection/gap_recovery.py`、`reconcile.py`、`audit.py`、`src/facet/status/`、`src/facet/web/`，以及 gap/reconcile/doctor 的只读汇总接线。

验收：History 404 不静默丢事件；恢复窗口和 generation 受控；按扫描时规则恢复整个已知停机窗口，不保证规则变更与邮件到达的严格时序，effective_at 留作审计；source/target 缺失和重复有明确报告；Dashboard 只返回聚合状态，不含邮件细节；新增规则不触发任意历史回扫。

Dashboard 验收：显示状态、已完成数量、历史进度、积压、异常分类和诊断，数据过期有提示；Discovery 未完成不虚构总量；重试不重复计数；所有 API 和页面都不包含邮件细节或原始异常。Web 请求不改变同步状态、不调用 Gmail，桌面与手机均可查看关键状态。

M2 已经交付初始 H0、History 消费和自动 backfill；M3 只补 gap、校对和可观察性，不再把 History polling 视为后置能力。

### M4 完整维护 CLI、审计/受限修复和 action-label 便利模式

交付：完整维护 CLI（queue/review/recovery/audit/repair、backup/restore/migrate/upgrade）、更完整的 offline doctor/status、审计/受限修复、普通 action actor 之外的 BlackList 竞争维护和 `gmail.modify` 便利 label 清理。M2 已完成只读 action-label 观察、规则更新和 normal generation/BlackList 竞争语义。

范围：`src/facet/cli/` 中的维护命令（queue/review/recovery/audit/repair/backup/restore/migrate/upgrade）、`src/facet/runtime.py`、`src/facet/gmail/labels.py`，以及 convenience mode 和维护状态/doctor 接线。

验收：queue/review/recovery/audit/repair、backup/restore/migrate/upgrade 和 offline doctor/status 对 pending、unknown、缺失和重复保持可解释且不绕过 writer 协议；便利模式核对实际 `gmail.modify` 授权，并在命令持久化后才清理 action labels；readonly 模式不修改 source。M2 的 BlackList generation 语义不能重新激活已停止的 thread，也不能把动态新规则自动应用到所有历史。

M4 完成后，形成可通过 CLI 配置、带只读 Dashboard、可长期同步的 Gmail alpha。

### M5 自托管交付、Compose 和 Actions 镜像

交付：非 root Docker image、Compose、Nginx 示例、GHCR main-SHA 发布、SBOM/provenance、双架构验证和双语运维文档。高吞吐调度和复杂 raw budget不属于前置关键路径。

范围：`src/facet/projection/actions.py`、`src/facet/gmail/labels.py`、CLI review 和 mode 切换。

验收：thread 上一次操作只产生一个命令；最新一封是自己回复时学习最近 external sender；命令重放不会重复学习；只读模式不调用 source mutation；便利模式在命令持久化后才清理标签；BlackList 阻止尚未开始的旧 jobs。切换模式要检查实际授权，不能自动扩大 scope。

现有 Apps Script 留下的 action labels 作为 legacy 记录展示，首次启动默认不执行；用户可以明确导入，或移除再添加以触发新命令。

### M6 真实 Gmail、部署、备份恢复和 v0.1 验收

完整 CLI 随镜像交付，exec/one-off 维护不要求 host Python。CLI-06/07/08 验收包含
offline 故障维护、锁竞争、稳定 request key/首应答丢失、preview producer、受限
recovery/repair 与升级回滚；真实 OAuth/Gmail/故障撤权仍受明确范围许可。

交付：非 root 镜像、Compose、配置示例、HTTP Dashboard、Nginx proxy 示例、
healthcheck、backup 和 restore CLI、中英文使用文档、离线 CI、显式开启的真实
Gmail 集成测试、发布检查表，以及通过 GitHub Actions 构建/发布的 amd64/arm64
镜像。应用不内置 HTTPS 和 Web 用户认证。

首次完成私密配置、Desktop loopback OAuth 和范围选择（完整入口内部准备或细分 preview）后，使用明确版本/digest
执行 `docker compose up -d` 一命令启动；初次启动不隐式启动 bulk backfill。PR 只
build/test，不 push image；获授权的发布流程使用 full commit SHA/digest、SBOM 和
provenance，验收匿名拉取与各架构运行。用户已授权 public
`ghcr.io/ghostflying/facet` 及 main 合并后 full-SHA 自动发布；正式版本 tag 和 GitHub
Release 仍需决定。公开源码不自动代表 package 已公开，必须实际检查匿名拉取。

范围：`Dockerfile`、`compose.yaml`、`config.example.yaml`、`.github/workflows/`、README、部署和运维文档、`tests/integration/`。

验收：全新环境可按文档完成授权和启动；本地磁盘 volume 中的 DB、凭据和 pending jobs 在重建容器后保留，raw 由 source 重新读取；备份恢复演练通过；授权撤销后不丢 jobs；大附件、磁盘压力和 target 故障不拖死无关 thread；日志和交付文件中没有正文、token 或私密测试数据；Dashboard 经 Nginx 可访问，UI、响应和诊断导出均通过隐私检查。

在指定的自托管主机进行至少 72 小时使用验证，跨一次 restart、token refresh 和故障
恢复，记录 Facet 状态变化与异常（不形成延迟承诺）。此时长是 v0.1 必需验收 gate，与仓库指令一致；
不是已验证的长期运行结果。修改这个 gate 需要明确产品决定。

## 测试计划

| 场景 | 预期行为 | 主要阶段 |
| --- | --- | --- |
| Raw 与附件 | 关键原始头部保留，MIME payload 和附件 hash 一致 | M2 |
| Date 非法或偏差 | 不丢内容，记录时间降级和排序差异 | M2 |
| Thread 重建 | 正常会话合并；fallback 映射完整可审计 | M2 |
| Insert 后 crash | 唯一且内容匹配的候选被绑定；模糊结果不盲目重试 | M2 |
| Message-ID 缺失或重复 | 不能只凭 Message-ID 判定同一封；进入受限恢复或 review | M2 |
| 六个月边界 | 用固定截止时间发现候选，纳入后复制完整 thread | M2 |
| Domain 和 admission | PSL、子域边界、规则生效时间、metadata 歧义和账号边界均有覆盖；不验证 sender authentication | M1 M2 |
| 初始化和分页 crash | H0 之前 discovery 与 H0 之后 History 共同覆盖，事件可重放 | M2 |
| 收信和自己回复 | 自动投影；已 tracked thread 的后续 sender 变化保留 | M2 |
| History 404 | 对 active threads 补漏，并恢复停机窗口内 admission | M3 |
| 新规则与 action jobs | 按处理时选定规则判断，不保证邮件/规则严格时序；`effective_at` 作审计，generation 生效；已知 gap 窗口外不隐式扩大历史披露 | M2 |
| Reconcile | source/target 校对与显式历史回扫边界不被绕过 | M3 |
| Action labels | 多 message 事件聚合；readonly 观察、effective_at/generation 和重复执行受控 | M2 |
| BlackList 竞争 | 未开始的 jobs 被取消；已经在途的 insert 可能完成并被记录 | M2 |
| 故障与部署 | 限流、失效凭据、磁盘满、退出和备份恢复都保留可解释状态 | M2 M6 |
| Dashboard 统计 | 总量未知、重放、部分失败和快照过期都真实显示 | M3 |
| Dashboard 隐私 | HTTP、DOM、前端状态、诊断和导出中无邮件字段或原始错误 | M1 M3 M6 |
| DB 内容边界 | 不保存 raw、正文、附件或完整 headers，重启重新取 source | M1 M2 M6 |

规则、状态机和 crash points 用离线测试验证；Gmail 日期、thread 和 attachment 行为用真实账号验证。CI 默认不持有 Gmail 凭据。真实集成测试限定已选定的测试邮件与 thread，不发送邮件，也不自动删除既有 target 内容。

## 发布标准和运行指标

v0.1 发布须完成 M1 至 M6，公开已知限制，并留存真实 Gmail 验收证据。任何被选中但尚未投影的邮件必须能在队列、review 或明确终止状态中解释，不能静默消失。

产品没有同步延迟承诺。Dashboard/CLI 可以显示最后 poll、队列年龄和完成时间等诊断事实，但不把它们解释为 SLA、P95 目标或发布门槛。

Dashboard 至少显示 source/target 角色的授权状态、权限模式、initialization 进度、最后成功 History 时间、队列深度、最老 job 年龄、tracked threads、成功邮件数、review 和异常分类数量、最近 reconcile 结果、资源状态与 schema version。账号地址、对象 IDs、邮件字段和本地路径仅按必要性保留在内部状态，不进入 Web 输出。

正式日志和公开诊断不包含正文、raw、附件、subject、sender 或 token，DEBUG 也不能绕过该边界。DB 只持久化同步所需的 metadata、rules、状态和受控错误码。Raw 在处理期间驻留内存，不存 DB 或磁盘，完整内容仍在 source/target Gmail。

## 后续路线

| 阶段 | 目标 | 开始条件 |
| --- | --- | --- |
| Phase 1 | Gmail 内容投影和可恢复自托管服务 | 当前计划 |
| Phase 1 后续 | 显式撤回、purge、retention、目标重复修复 | 先定义删除语义，再单独选择权限；不包括已单独批准的固定清单 target-cleanup 维护命令 |
| Phase 2 | 更好的 setup 和规则管理体验；评估日历或文档投影 | Gmail 持续使用反馈证明需要 |
| 后续独立提案 | Agent 以 primary 身份发送、其他 provider、复杂 topic rules | 单独确认产品和权限契约 |

数据源扩展复用 provenance、policy、queue 和 checkpoint 的概念；各 provider 的对象模型与目标实现单独设计，避免将 Gmail thread 当成所有数据源的通用单位。

## 开工前和发布前需要收敛的事项

整体计划获用户明确批准 G0 后可以从 P1/M1 开始，不需要先确定所有后续事项。
当前任务是 P1-00 开工台账与 P1-01 接口设计的独立 plan/review；具体权限状态见
执行计划 D0-D8，未答复的决定不得记录为已授权。

- M1 至 M3：确认银行实际 sender domains；未确认域名不进入默认规则。
- M2：校准 pending recovery 的多次搜索等待策略；不以一次 spike 的 11.8 秒观测作为固定保证。
- M6：选择实际 dogfood 主机与 volume 路径，核对 NAS 使用本地磁盘而非网络文件系统。
- 用户已确认 [GhostFlying/facet](https://github.com/GhostFlying/facet) 使用 public 可见性和用户账号的 GitHub noreply 提交邮箱；推送与 CI 进度见 [开发状态](development-status.md)。
- 用户已授权 G0 通过后，在 phase 内通过独立 plan/implementation review + CI
  自主合并工程/工作包计划 PR，及 Actions 发布 public `ghcr.io/ghostflying/facet` 的
  main full-SHA 镜像；总计划 PR 需用户明确批准后才能 merge，PR 不 publish。
  许可证、正式版本 tag/GitHub Release、live Gmail 范围和部署主机分别决定。

下一步完成 P1-00 review/整合，再按 P1 接口/测试基础→M1 的就绪图派工。每次后续
实施前写该包的具体文件、验收与风险 plan，通过独立 review 后实现，并再次 review
验收；协调 agent 不替代工程作者或独立 reviewer。
