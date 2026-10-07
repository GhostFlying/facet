# Facet Phase 1 总计划

日期：2026-10-03

状态：用户于 2026-10-02 批准 G0，绑定
`caba7c73895a303d329cf3eba1c89557530c38c5`；总计划 PR #2 已 merged，执行基础开始推进。
用户于 2026-10-03 要求取消 VS-1/手动 thread 切片，将第一条可用产品能力改为自动
discovery/backfill、History 增量、readonly action-label 规则和可恢复投影。M1-M6 与
生产 CLI 均未实现；当前工作包状态见 [进度台账](phase-1-progress.md)。
技术 review 和 CI 见 [review record](reviews/phase-1-plan-review.md) 与
[merged PR #2](https://github.com/GhostFlying/facet/pull/2)，推进入口为
[Phase 1 Epic #1](https://github.com/GhostFlying/facet/issues/1)。

本计划汇总 [产品契约](product-contract.md)、[项目计划](project-plan.md)、
[投影规格](gmail-projection-spec.md)、[Dashboard 规格](dashboard-spec.md) 和
[完整 CLI 契约](cli-spec.md) 的既有要求。下文是目标、必需证据和执行安排，不是
已测结果；当前能力以 [开发状态](development-status.md) 为准。Phase 0 只证明其
采样范围内的 Gmail 可行性，不能代替生产验收。

## 整体目标

交付一个单用户、可长期自托管的 Gmail 选择性投影服务。Source 是唯一事实来源；
用户通过明确规则和 action labels 授权完整 thread，由 Facet 将授权内容写入另一个 Gmail
target，AI agents 只连接 target。Facet 自身的 source OAuth 仍是邮箱级读取权限，
选择性由 Facet 执行逻辑实现，不是 OAuth 对 sender 的访问隔离。

需要交付的结果是：

- 披露选择可理解且持续有效：一封 message 获准即授权完整可用 non-draft thread，
  包括较早历史、附件、其他参与者与 own replies；tracked thread 的未来消息继续
  投影，即使 sender 改变。Preview 解释持续授权，不承诺冻结会话。
- Target 是用户可通过 Gmail API/UI 检查的披露视图，生产必须使用全新专用账号，
  由操作者声明并配置 Facet 为唯一应用写入者，AI connector 仅只读。Facet 对自己
  写入内容的范围、保真、日期、thread、附件和映射状态负责；发现 unexpected/
  unmanaged 内容时阻止新的投影写入并报告，不能自动删除、认领或清理。
- 服务在既有一致性边界内持续运行和恢复：选中工作持久可解释，限流、断网、
  restart 或授权失效不静默丢失 jobs；最终成功、review、取消或明确失败。不承诺
  Gmail 与 SQLite 的 exactly once，也不承诺恢复已无法取得的 source 内容。
- 自托管可观察、可维护：只读 Dashboard 显示可信汇总，全套 CLI 处理配置、授权、
  规则、进度、异常及维护；Compose、公开可追溯镜像、备份恢复和升级回滚形成完整
  交付，而不只是可启动源码或 help 骨架。

## 用户使用闭环

以下描述交付后的实际路径；当前尚不能执行生产 `facet` 命令。

1. 安装和检查：选择明确镜像版本/digest 与本地持久 volume，准备私密配置；CLI
   validate/init/doctor 检查本地 schema、文件权限及待核验 binding，不声称已检查
   live profiles/target 内容。初始化不复制邮件、不导入 spike 状态；Web 默认无公网暴露。
2. 授权与绑定：OAuth 前由操作者声明 target 为全新专用账号且 Facet 为唯一应用
   写入者；经 CLI Desktop loopback/SSH OAuth 分别绑定不同 source/target，核对
   live profiles/实际 scope。Target OAuth 后、首次 projection/insert 前只读检查
   普通邮件、草稿、Spam、Trash 和 account binding；unexpected/unmanaged 内容或
   mismatch 时 blocked/report-only，不删除、认领或清理。Gmail/OAuth 无法证明
   唯一写入者，声明和可观察检查是独立证据。OAuth 是一次
   安装准备，不由 Compose up 替代，也不自动授权
   任意 backfill、额外 scope 或未选择账号。
3. 预览和明确开始：配置规则，preview 解释固定六个月 discovery、thread 全历史与
   持续披露；setup/preview 零 insert。用户显式 start 后自动 backfill，不要求逐个
   选择 thread；真实范围仍需具体 live 许可。
4. 增量使用：单个 Docker 前台进程消费 History，投影 tracked thread 的新消息与 own replies；
   Dashboard 看汇总进度、队列、异常和 snapshot freshness，CLI 查本地状态；
   target Gmail API/UI 是内容验收入口。
5. 调整选择：用户在 source Gmail 手工添加 `AI/AddSender`、`AI/AddDomain` 或
   `AI/BlackList`；History 事件持久化、去重并更新规则/jobs。便利清理后移；
   新规则默认按 effective_at 生效，历史扩展不隐式扩大披露；
   remove allow rule 或移除 blacklist 不暗中停止/恢复已有 tracking。
6. 处理异常：CLI queue/review/recovery/audit 解释 blocked、unknown insert、
   source_missing、target missing 和 History gap；按受限 preview/approve/repair
   处理实际范围，不盲 retry、认领旧副本、重置 cursor 或删除 target。Auth 失效时
   offline status/doctor/maintenance 仍可用，reauth 后 pending work 继续。
7. 长期维护：一次配置/OAuth 后用 `docker compose up -d` 启动；容器重建保留 DB、
   binding、credentials 和 jobs。用镜像 CLI 停机持锁备份、离线验证/恢复/迁移，
   按明确 digest 升级与支持的 schema 路径回滚，无 host Python 安装要求。

## 整体验收

下列八类是 Phase 1 必须证明的结果，沿用现有契约和 gate，不是已通过的结果。
每项需要测试/实测记录及适用范围；源码完成、PR merge、build/help 成功或容器
启动不能替代验收。公开证据只用合成数据、受控汇总和 review/CI/artifact 引用，
真实邮箱内容、IDs、凭据和私人主机路径保持私密。

| 类别 | 必须达到的结果 | 必需证明证据 | 已有 gate / CLI / 工作包 |
| --- | --- | --- | --- |
| A1 披露与授权 | 完整 thread 持续授权、固定六个月 discovery、未来规则/显式历史扩展、metadata/rule admission、stop/BlackList 正确；全新专用 target、操作者 sole-writer 声明，unexpected/unmanaged target fail closed | 域名/effective_at/legacy/stop 反例；认证 header 不改变匹配 candidate；OAuth 后只读 target 检查、首次 insert 前阻止 unexpected 内容；preview→start 与零隐式 insert；获准范围的真实 admission/action 结果 | G1/G2/G4；CLI-01/03/05；M1-06、M2、M4 |
| A2 Gmail 保真和可见性 | 原 raw 不重序列化；内容/MIME/附件、有效 Date/可解释降级、实际 target thread 集合正确；默认 All Mail，不镜像读/星/Inbox/Sent 状态 | 版本化 semantic/MIME/附件 digest 与 Date/thread 合成测试；限定 live Gmail API 回读和 UI 检查；fallback 只处理确认 threading 错误 | G2/G6；CLI-02；M2-02/05、M6-08 |
| A3 连续同步与恢复 | H0/discovery/History 全分页接续，gap/reconcile 不扩大授权；intent/unknown、restart、取消/故障可恢复或明确 attention，选中工作不静默消失 | Cursor/intent/insert/map/stop/restart/disk 故障注入；初始化交错、History expiry 与归属反例；范围内 live 恢复、未知 gap 显式 range 决定 | G2/G3/G4；CLI-02/03/04；M2、M3、M4 |
| A4 隐私和输出边界 | DB 仅必要 metadata，raw 仅内存、不落文件；logs/CI/images 无邮件内容或凭据，许可的私密 state/backup owner-only；HTTP/DOM/frontend/URL/export 无邮件与内部私密字段 | DB/journal/log/files 和 CLI private/public 分层 sentinels；Web network/DOM/浏览器检查；image/context/layers/artifacts 扫描与 owner-only 文件检查 | G1/G4/G6；CLI-08；P1-02、M1-05、M4-04/05、M6-03 至 M6-06 |
| A5 可观察和可维护 | Dashboard 数量/单位/unknown/stale/部分失败真实；完整 CLI 完成 setup、控制、规则、queue/review/recovery/audit/维护 | 桌面/手机 UI 和 GET 零 Gmail/写副作用；CLI subprocess/fake E2E、JSON/退出码/确认/preview；invalid_grant 下 offline 诊断和维护 | G1/G3/G6；CLI-01 至 CLI-08；M1、M3、M5/M6 |
| A6 部署、备份和升级恢复 | 非 root 单 sync owner、local WAL volume、安全 HTTP/Nginx 边界；Compose 一键启动；公开镜像、容器 CLI、备份/恢复/迁移/rollback 可用 | 干净环境按双语 runbook 操作；匿名 digest pull、双架构 runtime/SBOM/provenance；容器重建 state 保留、DB+credential 锁竞争和实际运维演练 | G6；CLI-06/07；M6-01 至 M6-07 |
| A7 最终交付和 72h 运行 | G1-G6 全过；指定主机至少 72h，覆盖 restart/refresh/受控故障/backup/restore 与真实失效→重新 OAuth→pending jobs 继续；不包含延迟目标 | 实际起止、状态/异常运行记录及许可 scope；live Gmail API/UI、部署/CLI/恢复证据；candidate SHA/digest 和 reviews/CI/gates 索引，license/正式 release 决定按台账关闭 | G1 至 G6；CLI-07/08；M6-06/07/08 |

产品不承诺同步延迟，不设置 P95、轮询间隔、队列年龄或端到端时间门槛；这些字段如
出现在 Dashboard/CLI，只是观察到的状态事实。A7 的 72 小时是必需最低窗口，不是计时到点自动验收；仍有失败 gate
就继续整改。真实 Gmail、re-auth/撤权故障和主机演练需对应权限/用户参与，合成
测试不能代替。M4 alpha 或 AI 产品索引/检索效果都不等于 Phase 1 完成。

## 范围与非目标

本期只支持一个用户、一个 projection、两个不同 Gmail 账号。Python/SQLite WAL
运行在 local filesystem，Docker image 内单个前台进程 owns sync/HTTP；不实现独立
daemon、IPC、request-receipt broker 或容器外 runtime/native/read-bootstrap 保证。
静态 Dashboard 只读，无邮件详情/写控制。完整 CLI、Docker Compose、
Actions 的 public `ghcr.io/ghostflying/facet` 双架构镜像、双语运维文档与备份/恢复/
升级路径是必交付范围。

Source 默认 `gmail.readonly`，第一阶段观察用户手工 action labels 并处理规则；便利 `gmail.modify`、
target label 创建和可选 Inbox 按额外 scope/选择启用，不自动扩大权限。Target 默认
`gmail.insert` + `gmail.readonly`、All Mail 可见，仅 insert 不 send/forward。
Target 必须全新且专用，操作者声明并配置 Facet 为唯一应用写入者；AI connector
只读。Target OAuth 后的只读检查覆盖普通邮件、草稿、Spam、Trash 与账号 binding；
首次 projection/insert 前 unexpected/unmanaged 内容或 mismatch 必须 fail closed。
既有部署缺声明/检查时 blocked/report-only，保留 mappings/jobs/audit，不自动清理
或迁移。Gmail API 无法证明唯一写入者；当前文档不声称新增 runtime enforcement。

Phase 1 不做 send、purge/retention/target 自动删除、双向同步、全量状态镜像、
多租户、其他 provider、LLM 分类、通用 MCP、Web OAuth/邮件浏览/规则编辑或应用
自建 HTTPS/login。未来撤回也不保证清除第三方索引/缓存。AI connector 的授权、
索引、搜索、附件读取与回答准确性由各 AI 产品负责，不是 Facet 发布 gate 或同步
产品没有同步延迟承诺；这些外部 connector 行为不属于 Facet 的验收范围。

G0 是开发阶段对具体总计划版本的批准，不是安装后的 CLI runtime flag。D1 工程
自主 merge 与 D2 GHCR/main full-SHA scope 已授权，只在 G0/phase 开始后生效；
live Gmail/规则、host、额外 scopes、license/正式发布和持续唤醒按权限台账处理。
本轮重排不启动这些外部动作。

## 里程碑

M1-M6 是验收顺序，不强制所有工程串行；已冻结工程输入齐备时，后阶段独立离线
模块可以提前。Live/部署 gate 另记录，不能据此宣布前阶段完成。

| 里程碑 | 用户得到的阶段结果 | 关闭条件 |
| --- | --- | --- |
| M1 工程和身份基础 | 可校验配置/绑定/状态，安全持久化与正式 CLI 基础 | G1：身份/锁/隐私/认证设计证据齐备 |
| M2 自动 discovery/backfill 与增量投影核心 | 规则驱动固定六个月 discovery/backfill、History polling、readonly action-label 规则更新、完整投影、mapping 和 unknown recovery | G2：保真、归属、H0/cursor/事件去重、队列/故障及限定 live 证据 |
| M3 连续运行恢复与 Dashboard alpha | History 404/gap、reconcile/audit、聚合状态和只读 Dashboard | G3：增量交错、恢复、浏览器/隐私与运行证据 |
| M4 完整维护 CLI 与高级规则维护 | queue/review/recovery/repair、BlackList 竞争、offline maintenance、便利 label cleanup | G4：CLI、幂等、legacy/mode/cancellation 与范围内 live 证据 |
| M5 自托管交付 | Compose、GHCR Actions 镜像、双架构、SBOM/provenance 和运维文档 | G5：镜像、容器 CLI、部署前离线交付证据 |
| M6 真实部署和 v0.1 | 备份恢复、真实 Gmail、指定主机和 72h dogfood | G6：对应全部 gate、部署/恢复及实际 72h 证据 |

### 依赖图和里程碑门槛

```text
整体计划技术 review + 用户明确批准 G0（2026-10-02 已完成）
    |
    v
P1-00 协作/权限台账 ──┬── P1-01 核心接口/ADR ──┬── M1 基础 ── G1
                     └── P1-02 故障/隐私测试 ─┘       │
                                                       ├── M2 自动 discovery/backfill + History + projection ── G2
                                                       │               │
                                                       └───────────────┴── M3 gap/reconcile/Dashboard ── G3
                                                                            │
                      M4 CLI/action maintenance ───────────────────────────┴── G4
                                      │                                          │
                                      └── M5 Compose/image/docs ──────────────────┤
                                                                                v
                            M6 备份/真实授权/host → 部署 → 72h dogfood → G6 v0.1
```

G1→G2→G3→G4→G5→G6 的验收顺序保持不变。后阶段的 ADR、合成测试、独立模块和
交付配置可以在接口依赖满足时提前实施，但不能提前宣告阶段完成。M2 的离线 discovery、
History 和 backfill 测试可以先运行；真实范围仍需授权。M2 live 测试按已批准规则/窗口
执行，不以手动选定 thread 作为产品入口。

| Gate | 最小完成证据 | 不能替代的证据 |
| --- | --- | --- |
| G0 | 用户对 reviewable 整体计划版本的明确批准；记录版本/SHA、决定与范围 | 技术 review、CI 或 D1/D2 内部权限不代表整体计划批准 |
| G1 | 正式包/配置/DB/锁/绑定/私密文件/公共 DTO；认证 ADR 通过设计 review | Spike 能运行不能证明正式身份与隐私边界 |
| G2 | 自动 discovery/backfill、History 全分页/cursor、事件/规则去重、串行 thread 投影、保真、intent/recovery、generation 与基本内存安全；限定 live API/UI 保真 | 唯一搜索候选不等于本次 insert 的归属证明 |
| G3 | History gap/reconcile/audit、只读 Dashboard、初始化交错实测和浏览器隐私 | 离线 backfill 完成不等于增量无缝衔接 |
| G4 | 完整 CLI、三种 readonly action、legacy、effective_at/generation、BlackList 竞争、便利模式与受限修复 | 当前 label 快照不能复原过期 add/remove 命令 |
| G5 | 镜像/Compose/Nginx、Actions、双架构、SBOM/provenance、容器 CLI 和双语文档 | Build/help 成功不能证明完整维护 CLI、真实部署或长期稳定 |
| G6 | 备份恢复、真实 Gmail、授权部署、升级回滚和 72h dogfood | 任一前置 gate 失败不能用时间或吞吐声明替代 |

## 工作包与推进机制

以下 36 个包保留已审 ID 以避免 tracking 重写；本次重排只改变 milestone grouping 和
关键路径。第一条产品交付包含 M2-01..05、M3-01..04、M4-01 的 normal History polling，
以及 M5-01/M5-03 的 readonly action semantics；这些工作包的旧 ID 不等于新的 milestone
编号。原卡片中的 package ID 不等于新的 milestone gate。先列工作包，再给 CLI 归属、协作规则、
就绪波次和权限台账；实际派工以 frozen interfaces 与对应 gate/evidence 为准。
卡片中的规划轮说明属于总计划编制时的范围，不是实时完成状态；当前派工和证据以
[进度台账](phase-1-progress.md) 为准，不把依赖条件或未来交付描述当成已验收。

### P1：开工基础和测试基座

**P1-00 执行台账和协作基线**

依赖：本轮规划文档可先准备；phase 开工台账/派工等待 G0 和独立技术 review。
Owner：文档/协调实施 agent，S；review：独立 A。
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
insert result、public snapshot 等接口和 schema ownership。选择 Docker 前台运行时的
CLI 变更协议，明确执行、重放、锁及停机维护的责任；可评估本地 command 入口或停机
持锁，但先通过 ADR，不能让两个未协调 DB writer 并存。

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

### M1：正式工程、身份、持久状态与隐私

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

交付：Docker 前台单进程的写入所有权、停机 one-off 维护模式与受控错误。
验收：第二 sync owner 被拒；one-off CLI 不形成未协调第二 writer；网络等待不持 DB
事务；锁丢失/进程异常可解释而非悄悄开新库。不实现独立 daemon、IPC 或 request receipt broker。

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

**M1-06 规则基础与 G1 集成（source attestation gate 已按 2026-10-05 用户决定移除）**

依赖：M1-01 至 M1-05、P1-02。Owner：安全设计 A + 集成 S；review：独立 A。
文件：`projection/rules.py`、`projection/admission.py`、`cli/init.py`、`doctor.py`、metadata admission tests。

交付：sender/domain 规范化、点边界、公共后缀拒绝、PSL/IDNA 版本，以及 Gmail
负责 SMTP 认证/分类、Facet 不独立声明 sender authenticity 的边界。Doctor/init 检查
profile、scope、权限、schema、target 普通邮件/草稿/Spam/Trash 和 missing action
labels；target OAuth 后、首次 insert 前发现 unexpected/unmanaged 内容或 binding
mismatch 时阻止部署/投影并报告，不自动认领、删除或清理；OAuth 前另有操作者的
全新专用 target/唯一应用写入者声明。不复制邮件。

验收：认证 headers、DKIM/SPF/DMARC 文本和其缺失都不改变匹配 metadata candidate 的
规则决策；格式歧义、账号/权限不匹配和 provider 故障仍进入 attention。G1 关闭基础与
设计 gate；不建立 Facet 侧 sender-authentication evidence gate。用户不需要先确认银行
名单才能继续 M1。

### M2：thread 投影、保真和未知结果恢复

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

交付：同 thread prepare/insert/map 串行、claim generation guards、raw 仅内存和基本
上限、target 长期失败释放 raw。第一期不实现默认跨 thread 并发 4、实时优先、公平
调度或复杂 raw budget。验收：oversize 有可解释状态；stop 后未开始工作不写入，在途
结果仍入库；DB 事务不跨网络；全程无 spool/`.eml` 临时文件。

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

**M2-05 自动 projection integration 与 G2**

依赖：M2-01 至 M2-04、M1-06、M3-01 至 M3-04、M4-01、M5-01 和 M5-03 的离线工程
输出；G2 最终 live 验收依赖 D3。M3/M4/M5 的这些旧包 ID 属于 M2 首条产品交付，
不是后置 one-shot 或手动 thread 路径。
Owner：集成 agent，S；review：A。
文件：`cli/track.py`（仅保留内部兼容/状态接线，不作为产品入口）、`review.py`、
`tests/integration/`、G2 验收记录。

交付：规则驱动 discovery/backfill 与 History 事件产生 projection jobs，完整 thread
投影、target 实际 thread 集合/anchor/fallback、restart continuation 和 unknown recovery。
Preview 只确认规则范围与持续披露语义，不要求逐个选择 thread。验收：旧历史、附件、own
replies、其他参与者、tracked 后 sender 变化被正确解释；只对确认 threading 错误 fallback，
其他 400 不重写；source_missing 有明确状态。合成 crash evidence 与限定真实 Gmail
API/UI 日期、会话、附件证据分开记录。

### 第一交付组成：规则、生效时间和六个月发现（工作包 ID M3-01..04，归入 M2/G2）

**M3-01 Admission policy 与 review（metadata/rule admission）**

依赖：M2-01、M1-06、M2-04。Owner：规则 agent，S；review：A。
文件：`projection/admission.py`、`rules.py`、policy tests。

交付：blacklist→allow match→metadata eligibility→admit/review 的决策、规则 effective_at 和
action-label 触发的当前/未来 admission，
规则 effective_at。验收：公共后缀/相似恶意域名/多 From/未知 auth 不能 admission；
Spam/Trash/drafts 不引起新自动纳入；动态新增仅未来与 action-label/规则命中的当前
thread；删除 allow
不停止已 tracked thread。认证 header 不参与 admission；不再把逐个 explicit thread
approval 作为第一期入口。

**M3-02 固定六个月 discovery、H0 与 durable backfill**

依赖：M3-01、M2-03、M1-02。Owner：发现 agent，S；review：A。
文件：`projection/backfill.py`、checkpoint/epoch repos、discovery tests。

交付：UTC 日历月 cutoff、epoch、先持久 H0 后分页扫描、本地复核、durable thread
jobs、去重与可重扫。验收：三个月内命中且首封九个月前复制完整 thread；仅九个月前
命中不纳入；边界日期/月末有测试；page token 失效或 crash 可重扫；H0 持久失败不开始
扫描；resultSizeEstimate 不充当确定总量。该 durable backfill 由 M2 projection worker
消费，不另造 one-shot 复制路径。

**M3-03 Rules/backfill/review CLI 与授权 preview**

依赖：M3-01、M3-02、M1-03。Owner：CLI agent，S；review：A。
文件：`cli/rules.py`、`backfill.py`、`review.py`、CLI tests。

交付：preview/start/pause/resume、规则变更和显式历史扩展 epoch。验收：init/preview
零 insert；preview 解释 thread 持续授权、旧历史及可能 Spam/Trash；暂停只影响历史 jobs，
实时 tracking 继续；resume 沿用固定 epoch/cutoff；CLI 不绕过 writer 协议或 queue；新
domain 规则和 reconcile 不构成隐式历史 backfill。当前目标既有内容必须提示。

**M3-04 G3 集成与 disclosure 验收**

依赖：M3-01 至 M3-03；可信认证启用依赖 D3 和 AUTH 证据；History polling 已由 M2
核心接入，M3 不再阻塞初始 bulk。
Owner：验收 agent，S；review：A。文件：M3 integration tests、G3 evidence、文档。

交付：六个月、rule effective time、认证反例、停止状态、disclosure preview 的完整
测试矩阵。验收：所有选中工作可解释为 queued/success/review/cancelled/failure；认证
样本与声明覆盖对应；未确认银行 domains 不成为默认 allowlist。G3 可记录离线实现完成，
缺少 live 认证证据时 live gate 保持未闭合，不把结果包装为全部验收通过。

### M3：History gap、恢复、校对与 Dashboard alpha（工作包 ID M4-01..06）

**M4-01 History ingestion 和无缝初始化**

依赖：M3-02、M1-02、M2-01；可提前设计/离线实施。Owner：History agent，S；review：A。
文件：`projection/history.py`、typed event repos、pagination/crash tests。

交付：History polling（无延迟承诺）、typed events、稳定去重、每页 events/jobs 先落盘、全页完成
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

**M4-06 Dashboard alpha 与 G3 集成验收**

依赖：M4-01 至 M4-05、M3-04 的离线已验证工程输出。
Owner：集成 agent，S；review：A。
文件：`runtime.py`、scheduler/shutdown tests、G4 evidence、runbook。

G3 最终验收另依赖 D3 live 范围；Docker runtime/Compose 的离线实现不等待
G3 live gate。真实范围仍须明确 D3 授权。

交付：单 Docker sync/HTTP 前台进程、graceful SIGTERM、snapshot 刷新和各周期任务集成。
不实现独立 daemon/IPC、实时优先/backfill 公平或复杂 raw budget。验收：初始化/增量/backfill/
gap 交错不漏；target 故障不丢 jobs；关机未知 insert 保 recovery；Web 刷新不触发 Gmail；G3 alpha
包含实际 CLI + Dashboard 路径和授权初始化交错实测。

### 第一交付组成：readonly action labels（M5-01）与 M4 高级维护（M5-02/03）

**M5-01 Durable action commands 和学习**

依赖：M2 History/action event 输入、M3-01；readonly synthetic/production consumer 属于
第一条自动 projection 交付。Owner：动作 agent，S；review：A。
文件：`projection/actions.py`、action repos、action replay tests。

交付：`AI/AddSender`/`AI/AddDomain`/`AI/BlackList` 按 projection/history record/
label/thread 聚合；最新合法 external sender、own-address 排除、PSL 学习。
验收：多个 message entries 仅一个 command；最新 own reply 能找到较早 external；
不能学习 primary domain；格式歧义 review；command/rule/tracking/jobs 原子且重放
不重复效果；action 当前 thread approval 与 future rule 认证策略有独立状态。

**M5-02 Readonly、legacy 与便利清理**

依赖：M5-01、M1-04、M1-03。Owner：Gmail/CLI agent，S；review：A。
文件：`gmail/labels.py`、CLI mode/legacy/review、label cleanup tests。

交付：legacy labels 仅报告、remove/re-add 激活、readonly 无 source mutation；显式便利
模式/可选状态标签与 durable 后 cleanup 后移。验收：旧 label snapshots 不执行新命令；
cleanup crash 只重试清理不重复业务；缺少标签时 readonly CLI 可用；scope 不足不自动
扩大；status labels 默认关闭。Live 便利 mode 需 D3 中独立 scope 许可。

**M5-03 BlackList 竞争、停止/恢复和 G5**

依赖：M5-01、M5-02、M2-03/04 的离线已验证工程输出。M5-03 的基础 action semantics
属于 M2 首条交付；M4-02/03 的 gap/reconcile 仍是后续 M3 增强。
Owner：验收 agent，S；review：A。
文件：generation/cancellation fault tests、CLI stop/track、G5 evidence。

交付：exact sender blacklist + 选定 thread stop、取消 unstarted work、记录 in-flight
事实、显式恢复。验收：同域其他 sender/其他 tracked thread 不批停；移除 blacklist
不复活；reconcile/gap/restore/recovery 不绕过 generation；在途 insert 完成被记录；
target 历史保留。范围内 label live evidence 与合成 race evidence 分开。

### M5/M6：Compose、Actions 镜像、真实部署和自托管 v0.1（工作包 ID M6-01..09）

**M6-01 停机备份**

依赖：M1-02、M1-03、稳定 schema；可与后续模块并行。Owner：持久化 agent，S；review：A。
文件：`db/backup.py`、`cli/backup.py`、backup tests、运维文档。

交付：停止 sync container、持 writer lock、SQLite backup API、配置/binding/credential 成套
owner-only 备份和完整性 metadata。验收：有 WAL 的库可恢复；不复制 live 主 DB 代替
备份；backup 失败不破坏当前库；备份不含 raw；public logs 不含路径或凭据；备份和
artifact/镜像隔离。迁移使用此机制或已评审的同等 SQLite backup API 流程。

**M6-02 Restore、迁移和 rollback 状态验证**

依赖：M6-01、M2-04、M4-02、M5-03 的离线工程输出，不等待 G5 live gate。
Owner：恢复 agent，S；review：A。
文件：`cli/restore.py`、`db/migrations/`、restore/restart fault tests、rollback runbook。

交付：停止持锁恢复、schema/账号绑定核验、unknown insert 优先恢复，再恢复写入；
升级记录原 image digest/schema/备份。不支持 DB 降级时按旧镜像+整套备份回滚。
验收：错误账号、损坏/不兼容备份被拒，不能静默新建空库；stopped 状态保留；pending
jobs 和 unknown outcomes 不丢；中断迁移有明确恢复路径；凭据 owner-only。

**M6-03 非 root image、Compose 和 Nginx 示例**

依赖：M1-01、M4-06、M6-01 的离线工程输出，不等待 G4 的 Gmail gate；配置可先设计。
Owner：交付 agent，S；review：A。
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

依赖：M4-06、M5-03、M6-01 至 M6-04 的离线工程输出；docs 可随接口更新，不等待
G4/G5 最终 live gate。文档对应真实流程的验证保留为 M6 live/deployment 验收。
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

交付：至少 72 小时连续使用窗口，覆盖 restart、token refresh、一次受控故障恢复、
backup/restore，以及一次真实授权失效→CLI 重新 OAuth→pending jobs 继续的 re-auth
演练；token refresh 不能替代重新授权。演练的账号、授权失效/撤销操作及故障范围需
D3/D4 中明确许可，OAuth 需要用户参与，不能擅自 revoke 现有权限。缺许可/用户参与
时保留 gate pending，不能伪造通过。有效 source/target 绑定和规则范围保持一致。
验收：没有 selected work
静默消失；失败/review/取消明确；真实 Gmail API/UI 的日期、thread、附件符合契约；
队列/资源/Dashboard 与实际状态一致。72 小时到时仍有 gate 失败则继续整改，不能按时
钟自动通过；如需后台持续观察，应单独取得 automation/跨 turn 唤醒授权。

产品没有同步延迟承诺。可以记录 polling、queue、processing 的实际时间用于诊断，
但不得将其解释为 P95/SLA，也不得把样本量或时间阈值作为 gate。

**M6-09 G6 与 v0.1 release candidate**

依赖：G1-G5、M6-01 至 M6-08、D5 license 和版本 release 决定。
Owner：发布验收 agent，S；review：独立 A。
文件：release checklist、版本 metadata、公开已知限制、`development-status.md`。

交付：候选 commit/image digest 与所有 review/CI/offline/live/deployment/dogfood
证据的索引，支持的升级/回滚方式和已知外部限制。验收：所有 gate 有实际证据，无
未解释 selected work；public artifacts 不含私密 mailbox identities/IDs/evidence；
许可证和首次 release 决定完成；未满足的项保持阻塞。实际 tag/release/publication
遵守用户决定，工程 agent 执行，协调 agent 只调度与验收。

### 完整 CLI 与现有工作包

[CLI 契约](cli-spec.md) 是必需交付，不能以 skeleton/help-only 验收；命令/ownership/
JSON/退出码/confirmation/故障与 privacy 细节集中于该规格，36 个工作包 ID 不变。
共享 command registry/types/请求键/preview 与输出规则由 foundation/integration
owner 管理，各 feature handler 归对应包。以下 CLI acceptance 增加到包的现有 gate：

| Gate / CLI acceptance | 已有包 owner | 必需实际操作 |
| --- | --- | --- |
| G1 / CLI-01/08 | M1-01/03/04/05/06，P1-02 | config/init、auth-status、offline status/doctor/inspect、JSON/退出码/非 TTY/privacy；稳定请求键及首次应答丢失 lookup |
| G2 / CLI-02/08 | M2-01..05、M3-01/02/03/04、M4-01、M5-01/03 | rules/discovery/backfill/history/projection/recovery，queue/operations；unknown insert 不绕过 recovery |
| G3 / CLI-03/04 | M4-02/03/04/05/06 | preview/start/backfill pause/resume、gap/reconcile/audit、Dashboard；用途/范围/过期 preview guards |
| G4 / CLI-05 | M3-03、M5-01/02/03 | readonly action labels、legacy report、blacklist/stop，不复活 stopped generation |
| G5 / CLI-06/08 | M5-01/02/03、M6-03/04/05/06 | 最终 image 完整 CLI，无 host Python；容器 E2E 和隐私 |
| G6 / CLI-07/08 | M6-01/02/07/08/09 | offline backup/restore/migrate/inspect、re-auth、升级回滚、真实部署和 72h |

M1-03/M1-04 的 writer/auth ADR 同时定义成套维护与 auth/refresh 的 DB+credential
ownership/锁层次，防止 backup/restore 跨版本。离线读命令不因 invalid_grant 失效；
CLI 私密 metadata 与公共 aggregate DTO 分开，所有模式都禁止正文/raw/凭据/原始
provider errors。实际 Gmail/re-auth/repair 仍须独立范围许可；G0 已批准，不替代这些许可。

### 完成定义和调度原则

G0 是顶层启动 gate：用户 review 并明确批准具体 Phase 1 计划版本；本次已明确批准
精确 `caba7c7`，总计划 PR #2 已合入。技术 review 和 CI 没有替代该批准。
协调 agent 现在按本计划和实际依赖自主派工，内部普通复杂工作包只需要独立 agent
plan/code/acceptance review，不逐包再问用户。重要产品、隐私、scope 或 authority
改变重新提交用户 review。

Phase 1 完成必须满足 G1-G6 全部 gate，完成授权范围内的 Gmail API/UI 实测、
指定主机部署、备份恢复、restart/re-auth 恢复，以及至少 72 小时 dogfood。
M4 只是 alpha。未经验证的能力保持明确状态，失败的 gate 不能被缩小范围代替。

每个复杂包先形成文件化 plan 和必要 ADR，再由独立 reviewer 审核；通过后实施，
随后进行独立代码 review 和验收 review。Review 绑定明确的 plan 版本、base SHA
和候选 commit SHA。变更后只继承仍适用的结论，受影响证据重新验证。

下文 owner 是角色，不是固定 agent。协调 agent 派工时在对应 Issue 中绑定实际
agent、worktree、branch 和 reviewer。卡片中的 `S` 保留实施、测试、文档和集成
角色，`A` 保留复杂设计与高风险 review 角色；它们不是新的 Astra 派工许可。
2026-10-02 用户最新指示：后续任务仅使用 `gpt-6.1-sol` high/xhigh 或
`gpt-6-luna`，禁止新派工或 reactivate Astra。复杂设计、高风险独立 review 由
Sol xhigh 承担；简单有界低风险任务可用 Luna，其余按复杂度用 Sol high/xhigh。
独立 reviewer 不能审核自己负责设计或编写的同一变更；历史审查保留实际模型、
reviewer 与 SHA。36 卡片、依赖和 gate 不变，协调 agent 在允许模型内按风险调度。

当前总并发槽为 4：协调 agent 加 3 个执行槽。设计期可为 3 个独立设计/检查任务；
实施期默认 2 个 worker 加 1 个 reviewer。Review 是共享服务，不用让所有 worker
都等待同一串行大 PR。若只有两个依赖就绪的包，其余槽用于 review 或测试，不制造
无依赖价值的并行工作。

工作包中的“依赖”指实施所需的已冻结接口/输出；G1-G6 是集成验收依赖，另由 gate
表和就绪记录控制。前阶段已 offline-verified、live gate 待授权时，可继续拥有稳定
工程输入的后续离线实施，不能把前阶段全部宣告通过。派工记录需同时注明这两类依赖。

### 可并行波次和关键路径

下表保留历史工作包 ID 和波次名称以便追踪；它们不代表新的 milestone 顺序。M2/G2
首条自动产品路径必须拉齐 M3-01..04、M4-01 normal History polling 以及 M5-01/
M5-03 action semantics，不能等到表中的 W3/W5 才开始这些输入。

| 波次 | 可调度的包 | 关键约束 |
| --- | --- | --- |
| W0 当前规划 | 总计划文档/独立技术 review→用户 review/明确批准 G0 | 批准前不 merge 总计划 PR、不开始产品实现 |
| W0a 开工 | P1-00 派工台账→P1-01 接口/ADR plan-review | G0 后执行；先冻结共享接口 |
| W0b 基座 | P1-02 测试基座实现 + M1-01 package/config 实现 | 两者均依赖已冻结 P1-01；测试基座不能只停留在设计 |
| W1a DB | M1-02 实现；并行可做 M1-04 OAuth 设计 | 等 P1-02/M1-01 输出；OAuth 实现仍等 DB |
| W1b 身份/锁 | M1-03 + M1-04 实现 | M1-01/02 和 writer ADR 就绪；最后接入命令协议 |
| W1c 基础集成 | M1-05 实现→M1-06 集成；空余槽可做 M6-01 backup 设计 | 先完成 M1-03/04/05 输出再聚合 G1；后阶段设计不宣告通过 |
| W2a adapters | M2-01 实现；并行 M2-04 recovery ADR 设计 | M2-02 此时只可设计/测试设计，不能提前实现依赖 adapter 的逻辑 |
| W2b projection | M2-02→M2-03→M2-04 实现→M2-05 离线集成 | 每步等前项输出；空余槽做后项 plan/反例测试设计与 review；G2 live 另等 D3 |
| W3a admission | M3-01→M3-02 实现；并行 M4-01 History normal polling 实现 | 这些旧包是 M2/G2 首条路径输入；History 等固定 epoch/H0 工程输出 |
| W3b discovery/History | M3-03 + M3-04 实现；M4-01 接入 M2 projection | 两实现都等 M3-02；认证 live gate 不阻塞已有稳定输入的 History 逻辑 |
| W4a gap/API | M4-02 + M4-04 实现 | 两者等 M4-01 工程输出；尚待 G3 live 不阻塞离线代码 |
| W4b alpha 工程 | M4-03 + M4-05 实现→M4-06 离线整合 | 两者各自依赖 gap/API；G3 最终验收另等 live |
| W5a labels/backup | M5-01 + M5-03 action semantics；并行 M6-01 backup 设计 | M5-01/M5-03 属于 M2/G2 首条路径；M6-01 等稳定 DB/lock |
| W5b modes/Compose | M5-02 + M6-03 实现 | M5-02 是后续便利/legacy maintenance；Compose 等 M6-01 与 M4-06 离线输出 |
| W5c cancellation/image | M6-04 实现；M5-03 基础 semantics 已在 W5a | G5 live 另等 scope，main 发布遵守已批准 D2 |
| W6a 完整交付 | M6-02 + M6-05；随后 M6-06 | Restore 等停止/恢复离线输出；镜像验证等实际批准的发布；docs 等工程接口 |
| W6b 实际验收 | M6-07→M6-08→M6-09 | G5 与所有实测/host/license 所需决定齐备后推进；发布/部署不能虚构 |

表中 `+` 表示依赖已满足时可同时派两个 worker，`→` 表示必须先完成前项工程输出。
“设计”不包含依赖未满足的产品实现；review 槽始终保留。派工者以工作包卡片和当轮
就绪记录为准，不能因为同属一个大波次就同时启动存在依赖的实现。

工作量按 gate 和 review-ready 包管理，不在证据不足时承诺日期。关键路径主要是
AUTH/insert 归属 ADR→M2/G2 自动 discovery/backfill + History/action semantics→
M3 gap/reconcile/Dashboard→M4 maintenance→真实部署/dogfood。只有 M6-08 有固定最低
72 小时；认证证据、OAuth 和主机决策可能影响
等待时长，协调 agent 会报告下一就绪包而非伪造 ETA。

### 风险、决策和外部动作台账

| ID | 状态与责任 | 影响/触发点 | 提交用户的内容或工程处理 |
| --- | --- | --- | --- |
| D0 整体计划批准/启动 | 2026-10-02 用户已明确批准精确 `caba7c7`，PR #2 已 merged | Phase 执行已开始，依赖与各包 review/gates 保留 | 完整批准 SHA/CI/当前派工见进度台账；技术 review/CI 没有替代用户批准 |
| D1 Phase 内自主合并 | 2026-10-02 用户已授权；G0 通过后生效 | Phase 内工程/工作包计划 PR，经独立 plan/implementation review + CI | 协调 agent 核证并调度集成 agent 自主合并；总计划 PR 排除，GitHub required approval 仍须满足，不包含 live/deploy/release |
| D2 镜像位置/触发 | 2026-10-02 scope 已授权；G0/phase 启动后实施 | M6-04 publish、M6-05 拉取 | 仅 public `ghcr.io/ghostflying/facet`；main 合并后 full-SHA 自动发布；PR 不 publish；正式版本 tag/GitHub Release 另确认 |
| D3 Live Gmail/规则范围 | 生产 live 未授权，spike 授权不沿用 | G2/G3/G4/G5 live、bulk、M6 dogfood | 私下配置 source/target、限定 thread/rules/test scope、允许操作、OAuth mode 与退出策略；不把账号放 GitHub |
| D4 Dogfood host/volume/Nginx | 待用户选定 | M6-07/08 | 推荐部署形态、确切 host 与 local FS 检查、backup/digest/rollback；部署前呈现可 review 的交付物 |
| D5 License/版本 release | 待用户决定 | 首次 v0.1 release；不阻塞普通实现 | 给具体 license 选项和 version/artifact 清单；不凭公开仓库推断许可 |
| D6 银行 allow domains | 未确认；不是默认 allowlist | 对应 domain 自动 admission | 根据获授权私密实样提出精确 domains 和认证覆盖；未确认关闭/review，其他功能继续 |
| D7 不可归因 insert/未知 gap | 按真实运行触发；用户负责披露/重复风险决定 | 对应 work 恢复 | 只呈现受限 CLI 内的候选/范围/风险，推荐保 attention；不盲 retry/全历史披露/删除重复 |
| D8 长期唤醒/monitor | 本轮未授权 automation 或新 chat | 跨 turn 72h 观察 | 在部署方案具体后提交观察频率/通知条件/终止条件；等待不等于已有自动调度 |
| D9 显式 target-cleanup | 2026-10-07 用户批准 CLI 维护删除例外和独立临时完整 Gmail OAuth | 停机、锁、固定 target message IDs preview/确认/逐项 receipt；常驻 sync scopes 不变 | 工程实现/离线验收获准；真实删除仍单独批准实际 preview，不重置映射/unknown insert、不自动清理、不调整 M1-M6 gates |

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

### 本轮与首次实施 handoff

总计划编制轮交付了完整计划与独立 review/CI；用户随后明确批准精确 `caba7c7`，
PR #2 正常 fast-forward 合入 main。当前推进 P1-00 执行台账，再按依赖推进 P1-01
接口/ADR 与 P1-02 测试基础。总计划批准不替代 live Gmail、host、scope、版本发布
或 automation 决定；当前没有生产 daemon、Gmail 操作、镜像或部署。

G0 通过后首次实施 dispatch 从 P1-01 接口/ADR plan-review 开始，再并行完成 P1-02
测试基座实现与 M1-01，之后派 M1-02；
每包 Issue 写入当轮实际 branch/base/owner/reviewer 和计划链接。协调 agent 的正常
汇报说明“已完成且有证据 / 进行中 / 下一依赖 / 需用户决定”；生产能力继续用
implemented、offline-verified、Gmail-verified、deployment-verified 区分，不以 Issue
关闭、PR merge 或模型 review 自动等同产品验收。

### 发布实施参考

实施 agent 核对官方文档中的当前发布行为，再选已核验 action commit/base-image
digest；示例 action 版本不直接作为 pin：

- [GitHub Actions 发布 Docker images](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)：发布 job/token 和 artifact 证据。
- [GHCR container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)：package visibility、Actions token 和匿名拉取。
- [Docker multi-platform GitHub Actions](https://docs.docker.com/build/ci/github-actions/multi-platform/)：双架构 manifest 和构建流程。
- [Compose production deployment](https://docs.docker.com/compose/how-tos/production/)：部署与重建流程。
