# Facet Phase 1 完整执行计划

日期：2026-10-02

状态：计划待独立 review；M1-M6 均未实现。GitHub 跟踪入口为
[Phase 1 Epic #1](https://github.com/GhostFlying/facet/issues/1)。

目标：交付单用户、自托管、可恢复的 Gmail projection，包含只读 Dashboard、
Docker Compose 一键启动、GitHub Actions 发布的镜像、备份恢复和完整 v0.1 验收。
协调 agent 负责依赖分解、派工、review 调度、验收、进度与 blocker 汇报；设计、
代码、测试、文档、提交和冲突处理由负责的子 agent 完成。

本计划落实 [项目计划](project-plan.md) 的 M1-M6，并遵守
[产品契约](product-contract.md)、[投影规格](gmail-projection-spec.md) 与
[Dashboard 规格](dashboard-spec.md)。协作过程和模板见
[agent 工作流](agent-workflow.md)，当前能力以
[开发状态](development-status.md) 为准。计划中的路径、命令、指标和交付件不是
已实现功能；Phase 0 只证明其采样范围内的 Gmail 可行性。

## 完成定义和调度原则

Phase 1 完成必须满足 G1-G6 全部 gate，完成授权范围内的 Gmail API/UI 实测、
指定主机部署、备份恢复、restart/re-auth 恢复，以及至少 72 小时 dogfood。
M4 只是 alpha。未经验证的能力保持明确状态，失败的 gate 不能被缩小范围代替。

每个复杂包先形成文件化 plan 和必要 ADR，再由独立 reviewer 审核；通过后实施，
随后进行独立代码 review 和验收 review。Review 绑定明确的 plan 版本、base SHA
和候选 commit SHA。变更后只继承仍适用的结论，受影响证据重新验证。

下文 owner 是角色，不是固定 agent。协调 agent 派工时在对应 Issue 中绑定实际
agent、worktree、branch 和 reviewer。`S` 表示 `gpt-6.1-sol` / xhigh，主要负责
实施、测试、文档和集成；`A` 表示 `gpt-6-astra` / high，主要负责复杂设计与高风险
review。独立 reviewer 不能审核自己负责设计或编写的同一变更。模型选择由协调
agent 按风险调整，不要求用户逐包指定。

当前总并发槽为 4：协调 agent 加 3 个执行槽。设计期可为 3 个独立设计/检查任务；
实施期默认 2 个 worker 加 1 个 reviewer。Review 是共享服务，不用让所有 worker
都等待同一串行大 PR。若只有两个依赖就绪的包，其余槽用于 review 或测试，不制造
无依赖价值的并行工作。

工作包中的“依赖”指实施所需的已冻结接口/输出；G1-G6 是集成验收依赖，另由 gate
表和就绪记录控制。前阶段已 offline-verified、live gate 待授权时，可继续拥有稳定
工程输入的后续离线实施，不能把前阶段全部宣告通过。派工记录需同时注明这两类依赖。

## 依赖图和里程碑门槛

```text
P1-00 协作/权限台账 ──┬── P1-01 核心接口/ADR ──┬── M1 基础 ── G1
                     └── P1-02 故障/隐私测试 ─┘       │
                                                       ├── M2 投影 ── G2
                                                       │               │
                                                       └───────────────┴── M3 规则/发现 ── G3
                                                                            │
                      M4 History / gap / reconcile / Dashboard ───────────────┴── G4 alpha
                                                                                │
                            M6 离线交付包可在接口冻结后并行      M5 action labels ── G5
                                      │                                          │
                                      └── Compose / image / backup / docs ────────┤
                                                                                v
                            授权 live + host + publication → 部署 → 72h dogfood → G6 v0.1
```

G1→G2→G3→G4→G5→G6 的验收顺序保持不变。后阶段的 ADR、合成测试、独立模块和
交付配置可以在接口依赖满足时提前实施，但不能提前宣告阶段完成。M3 的离线 discovery
测试可以先运行；真实大规模 backfill 必须等 M4-01 和 M4-02 支持持久 H0 消费与 gap
恢复，并且真实范围获授权。M2 手动小范围 live 测试也要限定选定 thread 和 test scope。

| Gate | 最小完成证据 | 不能替代的证据 |
| --- | --- | --- |
| G1 | 正式包/配置/DB/锁/绑定/私密文件/公共 DTO；认证 ADR 通过设计 review | Spike 能运行不能证明正式身份与隐私边界 |
| G2 | 串行 thread 投影、保真、intent/recovery、generation、内存预算与 crash tests；限定 live API/UI 保真 | 唯一搜索候选不等于本次 insert 的归属证明 |
| G3 | 规则、可信 admission、固定六个月边界、H0、可恢复发现和 preview；认证证据启用门槛 | 合成 parser 测试不能独自证明 Gmail-path 信任 |
| G4 | 完整 History 分页、gap/reconcile/audit、runtime 与只读 Dashboard；初始化交错实测和浏览器隐私 | 离线 backfill 完成不等于增量无缝衔接 |
| G5 | 三种 action、legacy、幂等、readonly/便利模式、BlackList 竞争测试与范围内 live 证据 | 当前 label 快照不能复原过期 add/remove 命令 |
| G6 | 备份恢复、公开镜像验证、Compose/Nginx、升级回滚、双语文档、授权部署和 72h dogfood | 构建成功不能证明架构运行、真实部署或长期稳定 |

## P1：开工基础和测试基座

**P1-00 执行台账和协作基线**

依赖：本计划的独立 review。Owner：文档/协调实施 agent，S；review：独立 A。
文件：本文件、`agent-workflow.md`、`AGENTS.md`、`development-status.md`、
GitHub Epic/工作包 Issue 和 PR 模板。

交付：稳定 ID、依赖、权限状态、Issue/PR 生命周期、worktree ownership、验收与
handoff 模板。验收：36 个包均能追到 Epic，未决定项有触发点，计划与现有契约一致；
当前未实现状态保留；协调 agent 不被分配产品代码任务。当前轮只形成计划 PR，工作包
Issues 在实施启动后按就绪波次建立。

**P1-01 核心接口和单 writer 设计**

依赖：P1-00。Owner：架构 agent，A；review：另一独立 A。
文件：`docs/implementation-plans/adrs/core-state-contracts.md`、
`writer-command-protocol.md`，以及每包 plan 的接口引用。

交付：projection/binding、typed event/job/error、generation、claim、checkpoint、
insert result、public snapshot 等接口和 schema ownership。选择 daemon 运行时 CLI
变更协议，明确投递、执行、确认、重放、锁及停机维护的责任；可评估本地 command
入口或停机持锁，但先通过 ADR，不能让两个未协调 DB writer 并存。

验收：状态转移和事务边界能直接生成 crash/竞争测试；没有跨网络事务；read-only
status/doctor 不夺写锁；API 字段与私密 DB 状态明确分离。未通过此 review 的共享
schema/写入协议不能进入各 worker 的独立实现。

**P1-02 Fake Gmail、故障注入和隐私测试基座**

依赖：P1-01 typed 接口冻结。Owner：测试 agent，S；review：独立 S/A。
文件：`tests/fakes/`、`tests/conftest.py`、`tests/unit/`、
`docs/implementation-plans/test-evidence-matrix.md`。

交付：可控制分页、History 404、timeout、限流、insert 成功但响应丢失、索引延迟、
并发插入、source 删除和 persistence failure 的 fake；只用合成 MIME/地址。
验收：能在事件落盘、cursor、intent、insert、map、restart、stop 边界中断并复跑。
分别建立 DB 禁邮件内容 sentinels 和 Web 更严格的 metadata sentinels；DB 允许的
binding/rules/IDs 不被误当作全面禁存字段。测试工具自身不写 raw 临时文件。

## M1：正式工程、身份、持久状态与隐私

**M1-01 正式包、配置和 CLI 基础**

依赖：P1-01。Owner：工程 agent，S；review：独立 S。
文件：`pyproject.toml`、`uv.lock`、`src/facet/__init__.py`、`config.py`、`cli/`。

交付：Python 3.12+ 的 `facet` 入口，严格 config schema，固定默认值和私密 state
路径；保留 `facet-spike` 的独立入口与状态。验收：无效配置、未知字段、非本地 state
不符合部署检查时有受控错误；默认不复制邮件；`facet --help` 与 spike help 同时通过，
锁定环境可从干净 checkout 安装。PSL/IDNA 等行为固定版本。

**M1-02 DB schema、迁移与 repositories**

依赖：P1-01、P1-02。Owner：持久化 agent，S；review：A。
文件：`src/facet/db/schema.py`、`migrations/`、`repositories/`、DB tests。

交付：规格中的 metadata-only 表、复合唯一键、foreign keys、WAL 与可靠事务策略，
规则 effective_at、generation、intent、audit 和 resumable epoch storage。
验收：建库/迁移重复执行安全；故障回滚不初始化空库；重复事件不重复业务效果；
typed payload/error 拒绝任意邮件/provider JSON；DB、WAL、journal 和日志中不存在
正文/附件/raw sentinels。迁移前 backup hook 与版本兼容检查明确。

**M1-03 进程锁与 CLI 命令协议**

依赖：M1-01、M1-02、P1-01 writer ADR。Owner：运行时 agent，S；review：A。
文件：`src/facet/db/lock.py`、`runtime.py`、`cli/command.py`、多进程测试。

交付：一个 daemon 的写入所有权、运行中变更的协议、停机维护模式与受控错误。
验收：第二 daemon 被拒；运行中的 CLI 不形成未协调第二 writer；投递、执行、应答
各 crash 点不重复规则效果；停机 CLI 必须取得锁；read-only 查询可用；任何网络等待
不持 DB 事务。锁丢失/进程异常可解释而非悄悄开新库。

**M1-04 OAuth、profile binding 与 token 更新**

依赖：M1-01、M1-02；协议由 M1-03 接入。Owner：Gmail agent，S；review：A。
文件：`src/facet/gmail/oauth.py`、`binding.py`、私密文件 helper、CLI auth tests。

交付：独立 source/target Desktop loopback flow、明确 scope/mode、原子私密 token
替换、按账号串行 refresh、每次启动 profile 校验。验收：token 对调、相同账号、绑定
身份改变均拒绝；worker 不共享 refresh 写入；文件 owner-only；异常不泄漏 credential。
只实现授权工具，真实账号授权另受 D3 的范围决定；不能导入 spike token 或 cursor。

**M1-05 公共状态 DTO、受控错误与日志**

依赖：P1-01、P1-02、M1-02。Owner：隐私/状态 agent，S；review：A。
文件：`src/facet/status/models.py`、`errors.py`、`logging.py`、privacy tests。

交付：独立 allowlist response models、固定 error code/message、指标单位及 stale/
unknown/unavailable 语义，内部 doctor 与 Web DTO 分离。验收：synthetic addresses、
subject、IDs、fingerprints、raw exceptions、paths、tokens 注入后不进入公共输出；
DEBUG 同样受限；DB audit 不成为自由文本内容仓库。此时可测试模型，不宣称 HTTP 已实现。

**M1-06 规则基础、authentication ADR 与 G1 集成**

依赖：M1-01 至 M1-05、P1-02。Owner：安全设计 A + 集成 S；review：独立 A。
文件：`docs/implementation-plans/adrs/authentication-trust.md`、
`projection/rules.py`、`authenticity.py`、`cli/init.py`、`doctor.py`、合成认证 tests。

交付：sender/domain 规范化、点边界、公共后缀拒绝、PSL/IDNA 版本，以及可信 Gmail
接收路径/From alignment 的 ADR。Doctor/init 检查 profile、scope、权限、schema、
target unmanaged 普通邮件/草稿/Spam/Trash 和 missing action labels；不复制邮件。

验收：同名 authserv-id、任意追加 `Authentication-Results`、duplicate/conflict、
forward/ARC 与伪造 From 都不会凭文本变为可信 pass；每个 accept 分支有可说明的来源
依据和 policy 版本。未知→review。G1 关闭基础与设计 gate；G3 启用真实自动 admission
仍须有范围内证据，不能把 parser 测试当信任证明。用户不需要先确认银行名单才能继续 M1。

## M2：thread 投影、保真和未知结果恢复

**M2-01 Gmail adapters、错误分类和限流**

依赖：M1-01 至 M1-06 的工程接口、P1-02。Owner：Gmail agent，S；review：A。
文件：`gmail/source.py`、`target.py`、`retry.py`、adapter tests。

交付：scope 受限的读取/insert/回读接口、各 worker 独立 HTTP transport、账号限速，
typed 确定失败/未知结果。验收：无 send/forward/delete 方法；insert 无无条件客户端
重试；401/invalid_grant、403 各类别、429 Retry-After、5xx/timeout 正确分类；provider
原始响应不持久化或输出。真实 network 接入只用于获授权的 live harness。

**M2-02 版本化 fidelity 与原始 bytes 处理**

依赖：M2-01、P1-02。Owner：MIME agent，S；review：A。
文件：`projection/fidelity.py`、合成 MIME fixtures、`test_fidelity.py`。

交付：不重序列化的原 raw 传递，source digest 和稳定 header/MIME semantic digest，
有效 Date 的 `dateHeader` 与缺失/非法 Date 降级。验收：HTML、内嵌图、附件、非 ASCII
头部、multipart 顺序/参数、reply headers 保真；Gmail 增加 transport header 不误判；
不把原始 Date 与 source internalDate 必相等作为硬条件；保真失败进 review，不再次 insert。

**M2-03 串行 worker、generation 与 raw 内存预算**

依赖：M2-01、M2-02、M1-02、M1-03。Owner：运行时 agent，S；review：A。
文件：`projection/worker.py`、`scheduler.py`、`raw_budget.py`、worker fault tests。

交付：同 thread prepare/insert/map 串行、默认跨 thread 并发 4、实时优先且历史公平、
claim generation guards、内存 budget 和 target 长期失败释放 raw。验收：base64、解析
和 target 回读的内存放大计入预算；oversize 有可解释状态且不饿死其他 thread；stop 后
未开始工作不写入，在途结果仍入库；DB 事务不跨网络；全程无 spool/`.eml` 临时文件。

**M2-04 Intent、insert 归属 ADR 与 recovery**

依赖：M2-01、M2-02、M2-03、P1-02。Owner：恢复设计 A + 实施 S；review：独立 A。
文件：`docs/implementation-plans/adrs/insert-attribution.md`、
`projection/recovery.py`、intent repository、fault tests。

交付：intent→确定结果/unknown→恢复/attention 状态机。先评审可验证的本次 insert
归属证据，例如 target History fence 或 intent 前候选排除的适用性；方案未验证前不能
因为唯一 fingerprint 匹配就绑定。历史 Date/internalDate 不是 target 创建时间。

验收：预存在的 unmanaged/spike 内容与 source 完全相同且为唯一候选时不误认；本次
可归因 insert 能恢复；相同/缺失 RFC ID、索引延迟、多候选、映射冲突、其他写者、fence
分页/过期和 preflight 竞争均有反例。候选在 Spam/Trash 报可见性异常。零搜索结果不证明
没有插入；默认保 attention，任何受限重试必须有 ADR 规定的预算和明确风险。30s/2m/5m
只是初始检查节奏，不是搜索 SLA。停机、gap、restore 不重新激活 stopped thread。

**M2-05 手动 thread preview/track 与 G2**

依赖：M2-01 至 M2-04、M1-06；live 依赖 D3。Owner：集成 agent，S；review：A。
文件：`cli/track.py`、`review.py`、`tests/integration/`、G2 验收记录。

交付：手动选择 thread 的完整披露 preview、明确 start/approve、target 实际 thread
集合/anchor/fallback。验收：旧历史、附件、own replies、其他参与者、tracked 后 sender
变化被正确解释；只对确认 threading 错误 fallback，其他 400 不重写；source_missing
有明确状态。合成 crash evidence 与限定真实 Gmail API/UI 日期、会话、附件证据分开记录。

## M3：规则、生效时间和六个月发现

**M3-01 Admission policy 与 review**

依赖：M2-05 的离线输出、M1-06、M2-04。Owner：规则 agent，S；review：A。
文件：`projection/admission.py`、`rules.py`、`authenticity.py`、policy tests。

交付：blacklist→allow match→trusted auth→admit/review 的决策、explicit thread approval、
规则 effective_at。验收：公共后缀/相似恶意域名/多 From/未知 auth 不能 admission；
Spam/Trash/drafts 不引起新自动纳入；动态新增仅未来与当前明确选择 thread；删除 allow
不停止已 tracked thread。真实 automatic accept 在 authentication ADR 证据未闭合前关闭。

**M3-02 固定六个月 discovery、H0 与 durable backfill**

依赖：M3-01、M2-03、M1-02。Owner：发现 agent，S；review：A。
文件：`projection/backfill.py`、checkpoint/epoch repos、discovery tests。

交付：UTC 日历月 cutoff、epoch、先持久 H0 后分页扫描、本地复核、durable thread
jobs、去重与可重扫。验收：三个月内命中且首封九个月前复制完整 thread；仅九个月前
命中不纳入；边界日期/月末有测试；page token 失效或 crash 可重扫；H0 持久失败不开始
扫描；resultSizeEstimate 不充当确定总量。此包不开始真实 bulk backfill。

**M3-03 Rules/backfill/review CLI 与授权 preview**

依赖：M3-01、M3-02、M1-03。Owner：CLI agent，S；review：A。
文件：`cli/rules.py`、`backfill.py`、`review.py`、CLI tests。

交付：preview/start/pause/resume、规则变更和显式历史扩展 epoch。验收：init/preview
零 insert；preview 解释 thread 持续授权、旧历史及可能 Spam/Trash；暂停只影响历史 jobs，
实时 tracking 继续；resume 沿用固定 epoch/cutoff；CLI 不绕过 writer 协议或 queue；新
domain 规则和 reconcile 不构成隐式历史 backfill。当前目标既有内容必须提示。

**M3-04 G3 集成与 disclosure 验收**

依赖：M3-01 至 M3-03；可信认证启用依赖 D3 和 AUTH 证据；bulk 仍等 M4-01/02。
Owner：验收 agent，S；review：A。文件：M3 integration tests、G3 evidence、文档。

交付：六个月、rule effective time、认证反例、停止状态、disclosure preview 的完整
测试矩阵。验收：所有选中工作可解释为 queued/success/review/cancelled/failure；认证
样本与声明覆盖对应；未确认银行 domains 不成为默认 allowlist。G3 可记录离线实现完成，
缺少 live 认证证据时 live gate 保持未闭合，不把结果包装为全部验收通过。

## M4：History、恢复、校对与 Dashboard alpha

**M4-01 History ingestion 和无缝初始化**

依赖：M3-02、M1-02、M2-01；可提前设计/离线实施。Owner：History agent，S；review：A。
文件：`projection/history.py`、typed event repos、pagination/crash tests。

交付：默认 30 秒 poll、typed events、稳定去重、每页 events/jobs 先落盘、全页完成
后 cursor 提交。验收：History ID 当字符串；通用 messages 不重复执行 typed entries；
中途 crash 重读不漏不重业务；target 故障不阻碍 source durable ingestion；磁盘失败不
推进 cursor；无事件 poll 仍记录覆盖边界；discovery 期间收信/own reply 能从 H0 补齐。

**M4-02 History 404 与 gap recovery**

依赖：M4-01、M3-01、M2-04。Owner：恢复 agent，S；review：A。
文件：`projection/gap_recovery.py`、recovery epoch repos、gap tests。

交付：先持久 H1，再扫描所有 active thread 和整个可信停机 admission 窗口，扫描期间
事件由 H1 接续。验收：超过六个月/24h 的停机不被缩窗；未知起点进入用户决策；rule
effective_at 与 stopped generation 生效；label add 后 remove 已过期无法重建时报告
限制；分页、restart、source auth 中断可续；不能认领未管理副本或重启 stopped tracking。

**M4-03 Source reconcile、target audit 与 repair 边界**

依赖：M4-01、M4-02、M2-04。Owner：校对 agent，S；review：A。
文件：`projection/reconcile.py`、`audit.py`、CLI audit、resumable tests。

交付：每日 source ID 集合比较、每周映射 target 存在性检查、按需全 target audit，
durable epoch/进度与实时优先。验收：source 漏项安全补齐；target 缺失/Trash/重复和
未映射内容被分类；不自动 reinsert/delete/adopt；repair 必须明确范围授权；reconcile
不扩大动态规则历史范围。未知结果和重复 RFC ID 不能仅靠 IDs 声称内容等值。

**M4-04 Aggregate snapshots 与只读 HTTP**

依赖：M1-05、M3-02、M4-01；fake 数据可提前实施。Owner：状态/API agent，S；review：A。
文件：`status/aggregation.py`、`snapshots.py`、`web/api.py`、API privacy tests。

交付：规格定义的 status/progress/issues/diagnostics 和 healthz/readyz，缓存聚合
快照、互斥 job 类别、唯一确认映射计数、明确 message/thread 单位。验收：discovery
未知总量不假造比例/ETA；重试不加成功数；部分失败和 stale/unknown 真实显示；所有 GET
在 fake Gmail I/O spy 和 queue/rules snapshot 下零副作用；敏感 DB/event/exception
sentinels 不进入任一 HTTP 响应。只提供 HTTP，不内建 Web auth/TLS。

**M4-05 静态 Dashboard 与浏览器验收**

依赖：M4-04 DTO；界面可先用合成快照。Owner：UI agent，S；review：独立 UI/隐私 agent。
文件：`web/static/`、packaging assets、browser tests、合成截图。

交付：本地打包的轻量自适应页面，显示状态、进度、数量、异常、诊断和 freshness，
默认 10 秒刷新。验收：桌面/手机关键状态可见，无横向溢出或 page errors；断网 stale
和恢复正确；DOM、frontend state、URL、network/export 不含邮箱/邮件/规则/ID/path/
provider error；无外部 CDN、OAuth UI、邮件链接、content 路由或写控制。浏览器截图
仅用合成数据，可公开进入 PR。

**M4-06 Runtime 整合、alpha 与 G4**

依赖：M4-01 至 M4-05、G3；真实 bulk 依赖 D3。Owner：集成 agent，S；review：A。
文件：`runtime.py`、scheduler/shutdown tests、G4 evidence、runbook。

交付：单 sync/HTTP 进程、graceful SIGTERM、实时优先/backfill 公平、snapshot
刷新和各周期任务集成。验收：初始化/实时/backfill/gap 交错不漏；target 故障/raw budget
压力不拖死其他 thread；关机未知 insert 保 recovery；Web 刷新不触发 Gmail；G4 alpha
包含实际 CLI + Dashboard 路径和授权初始化交错实测。此后才允许获授权的大范围 backfill。

## M5：Action labels 和 BlackList

**M5-01 Durable action commands 和学习**

依赖：M4-01、M3-01；可提前用 synthetic events 实施。Owner：动作 agent，S；review：A。
文件：`projection/actions.py`、action repos、action replay tests。

交付：`AI/AddSender`/`AI/AddDomain`/`AI/BlackList` 按 projection/history record/
label/thread 聚合；最新合法 external sender、own-address 排除、PSL 学习。
验收：多个 message entries 仅一个 command；最新 own reply 能找到较早 external；
不能学习 primary domain；格式歧义 review；command/rule/tracking/jobs 原子且重放
不重复效果；action 当前 thread approval 与 future rule 认证策略有独立状态。

**M5-02 Readonly、legacy 与便利清理**

依赖：M5-01、M1-04、M1-03。Owner：Gmail/CLI agent，S；review：A。
文件：`gmail/labels.py`、CLI mode/legacy/review、label cleanup tests。

交付：legacy labels 仅报告、remove/re-add 激活、readonly 无 source mutation、显式
便利模式/可选状态标签与 durable 后 cleanup。验收：旧 label snapshots 不执行新命令；
cleanup crash 只重试清理不重复业务；缺少标签时 readonly CLI 可用；scope 不足不自动
扩大；status labels 默认关闭。Live 便利 mode 需 D3 中独立 scope 许可。

**M5-03 BlackList 竞争、停止/恢复和 G5**

依赖：M5-01、M5-02、M2-03/04、M4-02/03。Owner：验收 agent，S；review：A。
文件：generation/cancellation fault tests、CLI stop/track、G5 evidence。

交付：exact sender blacklist + 选定 thread stop、取消 unstarted work、记录 in-flight
事实、显式恢复。验收：同域其他 sender/其他 tracked thread 不批停；移除 blacklist
不复活；reconcile/gap/restore/recovery 不绕过 generation；在途 insert 完成被记录；
target 历史保留。范围内 label live evidence 与合成 race evidence 分开。

## M6：Compose、Actions 镜像和自托管 v0.1

**M6-01 停机备份**

依赖：M1-02、M1-03、稳定 schema；可与后续模块并行。Owner：持久化 agent，S；review：A。
文件：`db/backup.py`、`cli/backup.py`、backup tests、运维文档。

交付：停 daemon、持 writer lock、SQLite backup API、配置/binding/credential 成套
owner-only 备份和完整性 metadata。验收：有 WAL 的库可恢复；不复制 live 主 DB 代替
备份；backup 失败不破坏当前库；备份不含 raw；public logs 不含路径或凭据；备份和
artifact/镜像隔离。迁移使用此机制或已评审的同等 SQLite backup API 流程。

**M6-02 Restore、迁移和 rollback 状态验证**

依赖：M6-01、M2-04、M4-02、M5-03。Owner：恢复 agent，S；review：A。
文件：`cli/restore.py`、`db/migrations/`、restore/restart fault tests、rollback runbook。

交付：停止持锁恢复、schema/账号绑定核验、unknown insert 优先恢复，再恢复写入；
升级记录原 image digest/schema/备份。不支持 DB 降级时按旧镜像+整套备份回滚。
验收：错误账号、损坏/不兼容备份被拒，不能静默新建空库；stopped 状态保留；pending
jobs 和 unknown outcomes 不丢；中断迁移有明确恢复路径；凭据 owner-only。

**M6-03 非 root image、Compose 和 Nginx 示例**

依赖：M1-01、M4-06、M6-01；配置可提前实施。Owner：交付 agent，S；review：A。
文件：`Dockerfile`、`.dockerignore`、`compose.yaml`、`config.example.yaml`、
`deploy/nginx/`、container smoke tests。

交付：单进程非 root 镜像、打包静态资源、本地 state volume、healthcheck、loopback
发布和 Nginx shared-network 配置两种受控入口。首次配置、Desktop OAuth 和 preview
完成后，以明确 `FACET_IMAGE` 版本/digest 运行 `docker compose up -d` 一命令启动。
首次授权是必要交互，startup 不隐式开始 backfill；不要求每次 build、装依赖或手工迁移。

验收：干净主机按 runbook 可以用容器 CLI 完成 loopback/SSH 转发 OAuth；container
重建保留 DB/credentials/jobs，raw 从 source 重读；默认 host 仅 `127.0.0.1:8080`，
Nginx 模式不额外发布公网端口；容器 UID/权限、read-only filesystem（若采用）、health
语义和一个 sync owner 可验证；image/context/layers 中无私密配置或 spike evidence。

**M6-04 GitHub Actions build/publish**

依赖：M6-03、P1-00；publish 依赖 D2。Owner：CI agent，S；review：A。
文件：`.github/workflows/image.yml`、现有 `ci.yml`、release/image runbook。

交付：PR 运行测试和镜像 build，不 push；获授权的 main/tag 发布规则构建
`linux/amd64`、`linux/arm64`。用户已确认 public registry/package
`ghcr.io/ghostflying/facet`，main 合并后自动发布 full commit-SHA image（D2）。
镜像记录完整源 commit SHA 标签和 digest，
发布时另给明确版本标签；部署按 digest 或明确版本选取，不依赖 `latest`。

验收：Actions/base images 固定已核验 digest/commit；publish job 才获得
`packages: write`，默认只 `contents: read`；attestation 所需权限显式限定到对应 job；
fork/PR 不能用发布 credential；没有 Gmail secrets；cache、SBOM、provenance、build
logs/artifacts 不含 runtime state。版本发布 trigger 和 tag 权限遵守 D2，不能把计划
需求当作首次正式 release 授权。

**M6-05 镜像可拉取性、双架构和供应链证据**

依赖：M6-04 发布授权、M6-03。Owner：交付验收 agent，S；review：A。
文件：release verification scripts、artifact tests、image evidence 文档。

交付：manifest、每架构 digest、源 revision、SBOM/provenance 和匿名 pull 验证。
验收：无 registry 登录能拉 public image；SHA 标签不可被流水线无说明覆盖，最终
digest 可追到 reviewed commit；SBOM/provenance 与 artifact 相符；两个架构分别有
runtime smoke evidence。仅 arm64 build/QEMU 检查成功不伪装成真实 arm64 主机部署
证据；缺环境需保留该 gate 或说明真实验收方法。

**M6-06 双语使用/运维文档与受限 live harness**

依赖：M4-06、M5-03、M6-01 至 M6-04 的工程输出；docs 可随接口更新。
Owner：文档/QA agent，S；review：A。
文件：`README.md`、`README.zh-CN.md`、`docs/deployment.md`、`operations.md`、
`tests/integration/`、CI 和 release checklist。

交付：全新安装、OAuth、preview/start、CLI/action、Dashboard、诊断、backfill pause、
repair、backup/restore、upgrade/rollback、re-auth runbook；明确 External Testing token
限制。Live harness 默认关闭，验证账号、target、允许 thread/rule/test scope。

验收：独立 agent 从文档干净环境演练；CI 无 Gmail 凭据；真实操作不 send/delete/清理
旧副本；公开 fixtures/screenshots/reports 只合成或汇总；升级中断/invalid_grant/
target failure/disk pressure 各有可操作说明。OAuth 不通过聊天传 token。

**M6-07 指定主机部署和升级/回滚演练**

依赖：G5、M6-01 至 M6-06、D2/D3/D4。Owner：部署 agent，S；review：A。
文件：私密本地主机运行记录、脱敏 deployment evidence、部署状态 handoff。

交付：用户选定的 host/local volume/Nginx 入口、明确 image digest、配置和绑定、
部署前 backup/rollback reference。验收：本地文件系统支持 WAL；health/provenance、
非 root、state 保留、HTTP/Nginx 和桌面/手机 UI 验证；restart、升级与支持的 rollback
路径实际演练；凭据/私人 host paths 不进入 GitHub。未选主机可以完成交付文件，不能
宣告已部署或替用户选择真实机器。

**M6-08 至少 72 小时 dogfood 与指标证据**

依赖：M6-07、D3/D4。Owner：运行验收 agent，S；review：A。
文件：受限私密运行记录、脱敏 dogfood report、指标定义/样本量说明。

交付：至少 72 小时连续使用窗口，覆盖 restart、token refresh、一次受控故障恢复和
backup/restore；有效 source/target 账号和规则范围保持一致。验收：没有 selected work
静默消失；失败/review/取消明确；真实 Gmail API/UI 的日期、thread、附件符合契约；
队列/资源/Dashboard 与实际状态一致。72 小时到时仍有 gate 失败则继续整改，不能按时
钟自动通过；如需后台持续观察，应单独取得 automation/跨 turn 唤醒授权。

性能目标：正常 API、有效授权、无积压时，从 source 新消息到 target insert+回读的
P95 < 60 秒。测量 plan 在实测前冻结 source 事件时间定义、discovered/queued/verified
timestamps、样本量、backfill 排除及无样本状态；不能用历史 RFC Date 算旧邮件延迟。
分别报告 polling、queue 和 processing，AI connector 延迟不计入；未达标报告实测，
不得减少样本或改口径使 gate 通过。

**M6-09 G6 与 v0.1 release candidate**

依赖：G1-G5、M6-01 至 M6-08、D5 license 和版本 release 决定。
Owner：发布验收 agent，S；review：独立 A。
文件：release checklist、版本 metadata、公开已知限制、`development-status.md`。

交付：候选 commit/image digest 与所有 review/CI/offline/live/deployment/dogfood
证据的索引，支持的升级/回滚方式和已知外部限制。验收：所有 gate 有实际证据，无
未解释 selected work；public artifacts 不含私密 mailbox identities/IDs/evidence；
许可证和首次 release 决定完成；未满足的项保持阻塞。实际 tag/release/publication
遵守用户决定，工程 agent 执行，协调 agent 只调度与验收。

## 可并行波次和关键路径

| 波次 | 可调度的包 | 关键约束 |
| --- | --- | --- |
| W0 | P1-00、P1-01 设计、P1-02 测试基座设计 | 计划 review 后才写产品实现；先冻结共享接口 |
| W1 | M1-01 + M1-02，review 槽交替；随后 M1-04 + M1-05 | M1-03 依赖 DB/ADR；M1-06 聚合 G1 |
| W2 | M2-01 + M2-02；随后 M2-03 + M2-04 设计 | Recovery ADR/反例是 G2 关键路径；M2-05 最后集成 |
| W3 | M3-01 + M4-01 设计/离线实现；随后 M3-02/03 | 后阶段提前工作不提前过 gate；真实 bulk 等 M4-01/02 |
| W4 | M4-01/02 + M4-04；M4-03 + M4-05；M4-06 集成 | DTO 与 History 各有 reviewer，alpha 包含 Web 与恢复 |
| W5 | M5-01/02 + M6-01/03；随后 M5-03 与 M6-04/06 | 使用两个 worker+review 槽，不同时改共享 schema |
| W6 | M6-02/05/06，随后 M6-07→08→09 | Publish/live/host/license decision 只阻塞对应分支 |

工作量按 gate 和 review-ready 包管理，不在证据不足时承诺日期。关键路径主要是
AUTH/insert 归属 ADR→M2/G2→admission/H0→History/gap/alpha→action races→真实
部署/dogfood。只有 M6-08 有固定最低 72 小时；认证证据、OAuth 和主机决策可能影响
等待时长，协调 agent 会报告下一就绪包而非伪造 ETA。

## 风险、决策和外部动作台账

| ID | 状态与责任 | 影响/触发点 | 提交用户的内容或工程处理 |
| --- | --- | --- | --- |
| D1 自主合并权限 | 2026-10-02 用户已授权 | 本项目 Plan/工程 PR，经独立 plan/implementation review + CI 门槛 | 协调 agent 核证并调度集成 agent 自主合并；GitHub required approval 仍须满足，不包含 live/deploy/release |
| D2 镜像位置/触发 | 2026-10-02 用户已授权 | M6-04 publish、M6-05 拉取 | 仅 public `ghcr.io/ghostflying/facet`；main 合并后 full-SHA 自动发布；PR 不 publish；正式版本 tag/GitHub Release 另确认 |
| D3 Live Gmail/规则范围 | 生产 live 未授权，spike 授权不沿用 | G2/G3/G4/G5 live、bulk、M6 dogfood | 私下配置 source/target、限定 thread/rules/test scope、允许操作、OAuth mode 与退出策略；不把账号放 GitHub |
| D4 Dogfood host/volume/Nginx | 待用户选定 | M6-07/08 | 推荐部署形态、确切 host 与 local FS 检查、backup/digest/rollback；部署前呈现可 review 的交付物 |
| D5 License/版本 release | 待用户决定 | 首次 v0.1 release；不阻塞普通实现 | 给具体 license 选项和 version/artifact 清单；不凭公开仓库推断许可 |
| D6 银行 allow domains | 未确认；不是默认 allowlist | 对应 domain 自动 admission | 根据获授权私密实样提出精确 domains 和认证覆盖；未确认关闭/review，其他功能继续 |
| D7 不可归因 insert/未知 gap | 按真实运行触发；用户负责披露/重复风险决定 | 对应 work 恢复 | 只呈现受限 CLI 内的候选/范围/风险，推荐保 attention；不盲 retry/全历史披露/删除重复 |
| D8 长期唤醒/monitor | 本轮未授权 automation 或新 chat | 跨 turn 72h 观察 | 在部署方案具体后提交观察频率/通知条件/终止条件；等待不等于已有自动调度 |

| 工程风险 | 先行门槛/检测 | 安全失败状态 |
| --- | --- | --- |
| Spoofable 认证结果 | M1-06 AUTH ADR + M3 accept 分支证据/反例 | unknown/review，未证实自动 admission 关闭 |
| 匹配旧未管理/spike 副本 | M2-04 insert 归属 ADR + pre-existing candidate tests | needs_attention，不自动认领或再 insert |
| 单 writer 与 CLI 竞态 | P1-01 + M1-03 多进程 crash/replay tests | 拒绝未协调写者，不绕锁 |
| History 窗口过期/初始化漏信 | H0/H1、全分页 cursor、持久 recovery epoch | 可信范围恢复，未知 gap 用户决定 |
| 内容经 JSON/日志/HTTP 泄露 | typed storage + 双层 sentinels + 浏览器网络检查 | 拒绝自由文本/provider payload，不公开 raw |
| 大附件/target outage | Raw 放大预算、有限并发、释放内存、公平调度 | 工作保留/受控 backpressure，不落盘 raw |
| 镜像与部署来源不一致 | Full SHA/digest、SBOM/provenance、pull/runtime 检查 | 失败停止发布或部署，不依赖 mutable latest |
| 备份/迁移恢复失败 | 停机锁、SQLite backup API、故障与 rollback 演练 | 不空库、不复活 stopped、不丢 pending intents |

协调 agent 只把需要用户的新产品或外部权限决定上报；库选择、模块切分、重试实现、
DTO 技术等契约内工程决定由 agent 通过 ADR/review 作出。遇到 blocker 的包保持状态，
继续其他依赖就绪的离线任务。Decision packet 模板和汇报节奏见
[agent 工作流](agent-workflow.md)。

## 本轮与首次实施 handoff

本轮交付是完整计划、独立 review 结果、文档一致性检查及计划 PR。满足 D1 门槛后
计划 PR 可以自主合并；本轮不会启动产品 daemon、重新 OAuth、调用 Gmail、发布
镜像或部署。用户此前允许多 worktree、
subagents、Issue/PR 和原子提交，当前 planning worktree 只承载这个文档单元。

首次实施 dispatch 从 P1-01 接口/ADR 与 P1-02 测试设计开始，再派 M1-01/M1-02；
每包 Issue 写入当轮实际 branch/base/owner/reviewer 和计划链接。协调 agent 的正常
汇报说明“已完成且有证据 / 进行中 / 下一依赖 / 需用户决定”；生产能力继续用
implemented、offline-verified、Gmail-verified、deployment-verified 区分，不以 Issue
关闭、PR merge 或模型 review 自动等同产品验收。

## 发布实施参考

实施 agent 核对官方文档中的当前发布行为，再选已核验 action commit/base-image
digest；示例 action 版本不直接作为 pin：

- [GitHub Actions 发布 Docker images](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)：发布 job/token 和 artifact 证据。
- [GHCR container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)：package visibility、Actions token 和匿名拉取。
- [Docker multi-platform GitHub Actions](https://docs.docker.com/build/ci/github-actions/multi-platform/)：双架构 manifest 和构建流程。
- [Compose production deployment](https://docs.docker.com/compose/how-tos/production/)：部署与重建流程。
