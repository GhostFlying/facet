# Facet 完整维护 CLI 契约

日期：2026-10-02

状态：Phase 1 必需交付的规划接口，尚未实现；G0 已于 2026-10-02 批准整体计划
`caba7c73895a303d329cf3eba1c89557530c38c5`，当前执行状态见 [进度台账](phase-1-progress.md)。
G0 仅是本项目开发流程的启动批准，不是安装后的 CLI runtime flag 或认证门槛。

CLI 是 setup、规则/披露选择、故障处理和部署维护的完整入口。只读 Dashboard
负责观察，运维操作由 CLI 完成。Phase 1 验收必须有实际可用命令和端到端证据，
不能用 skeleton、`--help` 或直接编辑 SQLite 代替维护功能。

本契约遵守 [产品契约](product-contract.md)、
[Gmail 投影规格](gmail-projection-spec.md) 和
[执行计划](phase-1-execution-plan.md)。命令、选项、JSON 与退出码由下列工作包
实现并验收；内部 transport/锁协议仍由 P1-01/M1-03 ADR 决定。本契约使用 Docker
前台进程和共享 writer lock，不引入 IPC。

## 调用和共同约束

正式入口为 `facet`，保留独立 `facet-spike`。全局选项包括 `--config <path>`、
`--state-dir <path>`、`--projection <id>`、`--json`、`--private-metadata`、`--public`、
`--timeout <seconds>`、`--version` 和 `--help`。Phase 1 只有一个 projection，显式
selector 必须匹配该 binding，不能通过参数切换到另一个账号。

`--public` 和 `--private-metadata` 互斥。默认使用最少必要的本地操作状态；列出
账号、rule values、邮件 IDs 或私密路径需明确 `--private-metadata`。`--public`
仅用于已定义的 aggregate status/doctor 输出，使用独立 Dashboard allowlist DTO，
不让 mutation 命令或任意内部结果套上 public 标志就成为公开导出。

持久 mutation 使用稳定 `--request-id <id>` 作为本地幂等键：同键同 payload 不重复
业务效果，同键不同 payload 拒绝。键、命令类别、payload digest 和状态只保存在
owner-only 的 SQLite metadata 中，不保存邮件内容、credentials 或 provider JSON。
命令可由前台 `facet run` 或 Docker one-off container 执行；不引入独立 daemon、IPC、
request-receipt broker 或跨进程的 accepted/pending 协议。命令中断时重新使用同一个
request key 查询本地状态，不能盲目创建第二个业务效果。

扩大披露、重新插入、恢复 tracking、改变权限 mode、停止/恢复或替换维护状态的
命令需显示具体 binding/范围、操作影响与 preview。TTY 可交互确认；非 TTY 不提示、
不默认同意，必须显式 `--yes` 和必要 scope/preview selector。完整同步入口在一次
选定范围/确认后自动生成并引用内部 preview，不要求用户另交 preview ID 或逐步骤
确认；独立维修/recovery/cleanup 的确认方式不变。`--yes` 不绕过
绑定、scope、generation、归属、preview freshness 或产品权限检查。

初始 backfill 固定六个月；历史扩张用单独明确的 epoch。省略 scope 时不推断为
全部 mailbox，也不把 `--all` 当通用维修许可。Input paths、IDs、rule values 和
request keys 不进入日志或公开诊断；配置、凭据、backup 都是 owner-only 私密文件。

## 效果分类与 writer ownership

| 类别 | 作用与所有权 | Gmail 依赖 |
| --- | --- | --- |
| O：离线读取 | 读 SQLite/config/cached snapshot；不取 DB writer 所有权 | 无；未知/stale profile 状态如实标注 |
| C：持久命令 | 前台 sync 运行时或 one-off container 取得唯一 writer lock；不经 IPC | 按命令分类，不因等待 token 丢请求 |
| R：显式远端读取 | `--live`、preview、audit/recovery 检查；经绑定与 transport/refresh 协调 | 需要对应只读 scope；不 send/insert/delete |
| W：受限业务写入 | durable jobs 经 worker、intent/generation/归属与授权检查后执行 | 仅获授权 insert 或便利 label mutation |
| M：停机维护 | 必须停止 sync container 并取得 writer lock；迁移/恢复/显式 target-cleanup 不与服务同时写 | inspect/backup/restore/migrate 不要求 Gmail 可用；cleanup preview/execute 需要 target Gmail |
| A：OAuth 凭据操作 | 单账号 refresh/replacement 所有权；原子私密文件替换 | Desktop OAuth 用户交互；不调用任意邮箱 mutation |

Running sync process 拒绝第二 writer；maintenance one-off container 也不能绕过锁。只读
offline status/doctor 可以在 sync 停止、token 失效或 Gmail 不可用时查看 pending
work。`doctor --live` 额外执行受控远端检查，token refresh 仍经账号 manager/锁串行化；
不能把其 Gmail 不可用误报成 DB 不可读。网络等待不持 DB 事务。

成套 backup/restore/migration 不仅取得 DB writer ownership，还在读取/替换 config、
binding 与 credentials 时取得协调的 credential ownership；并发 auth/reauth/
refresh 必须等待或受控拒绝，不能使 DB snapshot 与 token/binding 跨版本，也不能
restore 覆盖刚完成的 reauth。锁层次、取得顺序和 cache/reload 协议由 writer/auth
ADR 统一规定并验证，不能由维护容器和 sync container 各自设计。运行中 A 类凭据替换经
同一账号 manager 协调或明确要求停机，不直接旁路写 token 文件。

Offline restore/migration 验证 backup、schema 和已存 binding；缺少 live profile
核验时记录 `binding_verification_pending`，可以完成停机恢复，但禁止开始新 Gmail
写入。之后 startup/live verify 核实两账号、处理 unknown insert，再恢复允许工作。
不能为让 restore 离线成功而声称账号已验证，也不能要求 Gmail 可用才备份本地状态。

## 命令族与交付归属

下表为规范 command families。每个子命令都有 text/JSON 结果、必要的确认、
bounded pagination 和受控失败；涉及对象的 `list/show` 只显示持久 metadata。
`--private-metadata` 不开放完整邮件读取。

| 命令 | 关键行为/效果 | 工作包 owner 与 gate |
| --- | --- | --- |
| `facet init`；`facet config init/validate/show` | 创建新私密配置/DB；拒绝覆盖 existing state；校验配置与存储；show 默认概览，私密值需 opt-in；O/C | M1-01、M1-02、M1-06；G1 |
| `facet config apply --file <path>` | 有明确 diff/确认，只改变可变运行项；不可交换 binding、隐式重导 rules 或扩大 OAuth scope；C | M1-01、M1-03，M4-06 接入；G1/G4 |
| `facet gmail auth/reauth <source|target> --port <port>`；`facet gmail auth-status` | 独立 Desktop flow、固定角色/scope、原子替换；reauth 保 binding/jobs，auth-status 默认离线；A/O | M1-04、M1-06；G1，真实 re-auth G6 |
| `facet status`；`facet doctor [--live]` | 本地汇总和诊断；默认 offline；O/R | M1-03/05/06、M3/M4；G1/G4 |
| `facet run` | Docker image 内前台唯一 sync/HTTP owner；由 Docker/Compose 负责生命周期；O/C | M1-03、M3；G1/G4 |
| 完整同步入口（拟 `facet sync [--once]`，未实现） | 自动检查配置/绑定/授权，按当前规则和固定六个月范围准备/启动或续跑 backfill，执行 History/投影；完全复用细分操作；C/R/W | M2/M3；CLI-02/03，最终 G6 |
| `facet rules list/show/add-sender/add-domain/remove`；`facet rules action-label set/remove/list --kind ...`；`facet rules blacklist --sender <address> --thread <id>` | exact 规则、处理时生效状态，effective_at 作审计；blacklist + 所选 thread stop，typed audit；action-label mapping is private, single-writer, exact-name, and source-readonly；O/C | M1-02/06、M3-01/03、M5-03；G3/G5 |
| `facet backfill preview/start/status/pause/resume` | 固定 cutoff/H0/epoch、明确 start、自动 discovery/backfill、暂停/恢复与进度；R/C→W/O | M2、M3；G2/G3 |
| `facet queue list/show`；`facet queue retry --job <id>` | 看互斥 job 状态、next attempt/error code；仅安全可重试 job 重新调度；O/C | M2-03/04/05、M4-06；G2/G4 |
| `facet review list/show/preview --item <id>`；`facet review approve --item <id> --preview <id>`；`facet review reject --item <id>` | 仅处理认证未知、归属未知等异常 admission item；不作为常规逐 thread 入口；O/C→W | M2/M3/M4；G2/G3/G4 |
| `facet reconcile --source/--target`；`facet reconcile status` | Durable source 补漏/target 存在性报告与进度；不删除或默认 reinsert；C/R | M4-03、M4-06；G4 |
| `facet audit target --full`；`facet audit list/show` | 可恢复的全 target 检查、异常/未映射内容报告；metadata 输出；C/R/O | M4-03；G4 |
| `facet repair preview/start/status --audit <id>` | 只修指定、已管理且确认 missing 的消息；不含 unmanaged/spike；R/C→W/O | M4-03、M2-04、M5-03；G4/G5，部署流程 G6 |
| `facet recovery list/show/check/preview --job <id>` | Check 核验归属；preview 生成受限 retry 的 scope/risk ID，禁止分支则返回拒绝而不生成许可；默认不 insert；O/C/R | M2、M3；G2/G4 |
| `facet recovery gap preview --gap <id> --since <UTC> --until <UTC>`；`facet recovery gap approve --gap <id> --preview <id>` | 无可信 coverage time 时，用户明确选择恢复 range，保存 typed decision；H1/fence、范围/generation 不绕过，规则不按邮件时间重建；R/C | M4-02、M3-03；G4，决定 D7 |
| `facet recovery retry --job <id> --preview <id> --acknowledge-duplicate-risk` | 仅 ADR 允许、预算未超且范围明确的受限 retry；不可 force-bind；C→W | M2-04、M3-03；G2/G3，实际许可 D7 |
| `facet gmail mode show/set`；`facet gmail labels status/setup` | 实际 scopes 校验、readonly/便利 mode；legacy 仅报告，便利 setup 需明确许可；O/C/R/W | M1-04、M5-02；G5 |
| `facet maintenance inspect/check`；`facet migrate plan/apply/status` | 离线 metadata/schema/迁移兼容性检查；apply 先 backup、停机持锁；O/M | M1-02/03、M6-01/02；G1/G6 |
| `facet backup create/verify/list`；`facet restore plan/apply` | SQLite backup API + config/binding/credentials 成套保存；离线验证/恢复；M/O | M6-01/02；G6 |

Existing planned aliases `backfill stop`→`backfill pause`、`backup <destination>`→
`backup create --destination` 可保留明确 deprecation 信息。旧
`reconcile --target --repair-missing` 只能作为 bounded repair 的 alias，缺 audit/
selected scope/preview 时拒绝；不能继续接受一个 `--yes` 就重插整个 target。

## 初始化、配置和 OAuth

首次安装可使用交互式 `facet setup --oauth-client <private-desktop-client>
--port <loopback-port> --request-id <rq1_uuid_uuid>`。它只适用于不存在的
production state root：按 source、target 顺序授权，通过 `users.getProfile`
发现地址，在同一个 controlling TTY 显示实际两角色并要求明确确认，然后才创建
配置、binding 和 credential files。setup 与显式 target-cleanup consent 是允许 OAuth URL/实际账号地址
出现在 controlling terminal 的命令；它拒绝 `--json`、`--public`、private
metadata 输出和 non-TTY，`--yes` 也不能跳过发现后的确认。setup 不列邮件、读取
raw、insert、写 labels、创建规则、开始 preview/backfill 或启动 sync。

`--request-id` 必须使用 `rq1_<uuid4-hex>_<uuid4-hex>`；caller 在启动前建立并
私下保存该稳定键。source/target role key 由 setup nonce 和 role
确定性派生，必须原样用于现有 `auth authorize --role ... --request-id ...` 的
中断续办。确认前崩溃不留 state；确认后中断保留 pending state，重跑 setup 拒绝
该 root，用户用现有 role auth 命令继续，不能重建空 DB 或手工宣称 ready。

setup 的 OAuth adapter 使用严格首次授权模式：不请求 incremental scope union，
且仅接受 token response 的 actual `granted_scopes` 证据；缺少该字段即
`scope_required`，不能用 `credentials.scopes` 或配置 requested scopes 填补。已有
role auth/reauth 路径保持其既有兼容行为。source 默认 `gmail.readonly`，target
默认 `gmail.insert` + `gmail.readonly`；没有新增 provider scope。

`init` 只建新本地状态、schema 和待核验 binding；不读取/导入 spike token、cursor
或旧 target mappings，不复制邮件。`config init` 不覆盖文件；已存在时返回冲突。
`config validate` 和 `maintenance inspect` 都能 offline 运行。配置内 initial rules
只在首次初始化导入；config apply 不覆盖后续学习/删除的 DB 规则。

Mutable operational options 的支持范围由 config ADR 列明；需要重启的变更返回
`restart_required`，不能悄悄启动第二 sync process。Source/target identity 的变更、state
目录迁移或不兼容 schema 不提供 `--force-rebind`/重建空库捷径，走受 review 的维护流程。

Auth/reauth 使用 Desktop loopback，支持浏览器与 SSH 同端口转发。令牌 JSON、
authorization response/code、refresh token 和 client secret 不接收为聊天输入，
也不进入 CLI JSON/stdout、日志或 report。必要的单次授权 URL 只经显式 auth 流程的
交互终端显示，不进入 diagnostics/public DTO；无法提供交互终端时返回需要授权的
受控状态并引导受支持的 SSH/loopback 流程，不能退回粘贴 token。

Reauth 只能保留已批准的 role/scopes/binding；扩大 `gmail.modify`/`gmail.labels`
需单独明确选择与同意，不能为修 `invalid_grant` 自动请求更多权限。重新选错账号
拒绝替换原 binding，并保留 pending jobs。Auth-status 离线返回 last verified time、
expiry/unknown、mode 和 role，不把 token 文件存在当作 live OAuth 健康证明。

## 服务、规则、thread 和 backfill

### 完整入口和细分命令（2026-10-07 用户决定）

最终产品提供完整同步入口与细分维护命令。完整入口的拟定拼写为 `facet sync`：
不带 `--once` 持续运行，带 `--once` 执行一轮后退出，不承诺一轮耗尽全部任务。
该命令尚未实现，也不改变当前 Docker/Compose 默认 `run`。它检查现有配置、账号
binding 和 scopes，缺授权时引导既有 OAuth 交互，不默选账号、覆盖状态或扩权。

一次有意调用选择当前 enabled allow rules 与默认固定六个月窗口，自动完成范围
快照和 guarded start，然后执行 discovery/backfill、History、insert/readback/map。
不要求用户分别 preview/start、传 preview ID 或管理各子操作的请求键；内部稳定键
和操作进度必须先持久化，以便中断/首应答丢失后续跑。TTY 在入口确认选定范围，
非 TTY 显式 `--yes` 接受已说明的默认/选定范围，不增加逐步骤确认。Scope 过期或
规则/stop generation 改变仍重新检查，不能借自动编排绕过已有 guards。

完整入口调用细分命令背后的同一业务操作，不另造同步引擎、shell 子命令链或 IPC。
已有规则/窗口工作继续、mapping 去重；新增历史范围创建独立 epoch，不清空旧
discovery/cursor/intents。容器重启/普通 run 续跑已有范围；连续运行中的新规则和
action 学习仍 prospective，不把重启、每日 reconcile 当作新的历史披露意图。
单独 init/setup/preview/status 保持原有无复制行为，维修/恢复许可不随 sync 扩张。

当前真实验证继续用细分命令，按具体已批准范围执行。产品入口可自动编排不代表
agent 可以在当前测试中自动开始新历史补齐、retry unknown 或启动长期服务。

`facet run` 前台运行，Compose/Docker 负责进程启动和 restart；CLI 不安装 systemd、
修改宿主网络或拉取/替换容器。停止容器等效安全 SIGTERM：停领取、提交已知结果、
unknown insert 留 recovery。`backfill pause` 只暂停历史 jobs，History ingestion 仍
可持久化；重启不重置 cursor 或复活 stopped generations。

Rules add 默认 prospectively effective；第一期通过 source History 读取用户手工 action
labels 更新规则，不把逐个手动 track 作为常规入口。Rules remove 不停止已 tracked
thread。Blacklist 用 exact sender + 当前 thread，取消 unstarted generation，不停止
同域所有 thread、不删除历史；去掉 blacklist 不自动恢复 tracking。

Preview 是可解释的范围快照：projection binding、rule/stop generation、epoch/window、
message/thread 已知计数、旧历史/附件/参与者/own replies/Spam/Trash 的披露语义和
持续授权。它不返回邮件细节，也不冻结未来 thread 内容。Start/approve 引用具体 preview；
规则或 generation 改变、scope 不匹配时需重新 preview，不复用过期选择。Preview
可以保存必要 metadata/H0，但不 insert；bulk start 还需 H0 可消费/gap 能力与真实许可。

`backfill preview`、`repair preview --audit` 和 `recovery preview --job` 都是明确的
producer；输出本地 scoped preview ID 和固定用途。一个用途的 ID 不能用于另一命令，
IDs/范围不一致或过期时 guard 拒绝。自动 discovery 的 preview 解释规则、六个月窗口、
完整 thread 持续披露与 start 范围，不暴露邮件细节。完整同步入口内部生成并引用
这一快照；下面的独立命令仍适用于维护和分步测试。

```text
facet recovery preview --job <job-id> --request-id <recovery-preview-key> --json
facet backfill start --preview-id <preview-id> --request-id <backfill-key> --yes --json
```

## Queue、review、recovery 与 repair

Queue retry 只改变当前 generation 的合法 retry schedule，不删除 attempts、不提升
scope、不复活 inactive thread。`pending_recovery` 或曾发出但结果 unknown 的 job
转 recovery check，而不是直接 insert；过时 generation 返回 controlled refusal。
Auth/network/rate-limit 的 blocked jobs 保留，service 恢复后可续。

Review approve 只适用于可明确手动 admission 的类别，必须解释完整 thread 授权。
Fidelity mismatch、多 recovery candidates 或归属未知不能用通用 approve 绕过核验；
操作返回该类别的处理指引。Reject 留 typed decision，不能删掉未完成 work 以造成
all-success，也不改变无关 tracking。CLI 不提供“认领 unmanaged”或任意 target-ID
force-bind。

Recovery check 搜索/回读和比较受限候选，只有已评审归属证据成立才写 mapping；
存在内容相同旧副本、Message-ID 复用、多个候选、索引不确定或冲突时保 attention。
Recovery retry 先 preview 当前 job、budget、generation 和仍可能重复的风险，再做
已批准的 scope/风险决定；`--acknowledge-duplicate-risk` 不能使本来禁止的 ADR 分支
变为允许。候选 Spam/Trash 不是正常可见；任何命令都不清理重复。

当前已接入的恢复检查单元只实现 `recovery list/show/check` 的证据读取：`show` 通过
typed `recover_insert` job lineage 读取私有 metadata，`check` 按 RFC Message-ID 搜索
target 并做 readback/fidelity 比较。它不 insert、不写 SQLite、不授权 retry；recovery
preview/retry、gap 恢复、repair 与 backup/restore 仍是后续门槛。

Unknown History gap 通过 `recovery gap preview/approve` 显式选择 UTC range，approve
引用同 gap/范围 preview、稳定请求键与确认。执行仍先持久 H1/fence，遵守 rule
有边界的停机窗口和 stopped generation；按处理/扫描时规则判断，不保证邮件与
规则变更的严格时序，effective_at 作审计；不 reset cursor、默认披露全历史、认领当前 labels
或声称复原已过期 add/remove。CLI-04 测试未知起点的 range 选择与这些 guard。

Repair 必须引用一个已完成或明确部分完成的 audit，以及明确选择的 source message/
thread 集合；不能默认修整个邮箱。Preview 构造固定 repair operation，start 再检查
mapping missing、active generation、账号与新异常；只修 production-managed mail。
Read-only target audit 不自动 repair。处理途中 source_missing/unknown outcome 仍用
原队列/recovery 状态机，不能因 repair 名称盲插。

## Offline 备份、恢复和升级维护

`backup create --destination <path>` 先确认 sync container 已停止并取得 writer lock，再用
SQLite backup API 保存 DB 与配置/binding/credentials；不复制 raw，不仅复制 live
主 DB。Destination 必须新建/空的指定备份位置，不覆盖任意已有目录。`backup verify`
离线检查完整性、schema、成套文件与私密权限，不要求 Gmail 可用。

`setup` 的 target 前置条件是操作者声明新建专用 target 及允许的外部 agent 发信/草稿用途；agent 以绑定 source 为 From，回复直接进入 source。Facet 不提供发送/草稿创建、send-as 配置或额外 scope。Target OAuth 后、首次 projection/insert 前只读检查账号 binding 及普通邮件、SENT、草稿、Spam、Trash。按产品契约分类的未管理 source 身份 SENT/DRAFT 不阻塞、不计投影成功、不自动认领 unknown insert；既有映射/独立证实的本系统 insert 结果优先，标签/From 不证明真实性或应用写入者。其他 unexpected/unmanaged 内容或账号不匹配仍 fail closed，保持 blocked/report-only。当前 setup 只核对 profile，内容分类与 recovery 排除仍待运行时验收，不因本轮文档修改宣称完成。CLI 不提供认领、自动清理或同步删除路径；唯一显式维护删除例外见下节。

### 显式专用 target 清理（2026-10-07 用户授权例外）

`target-cleanup preview --request-id <uuid4-hex>` 是持锁的只读 Gmail 操作，完整分页
普通邮件/Spam/Trash/草稿，私密 journal 仅保存固定邮件 IDs 和进度，无内容。
`target-cleanup status --preview <id>` 为 O 类 query-only，不取 writer lock、不读
凭据或调用 Gmail。`target-cleanup execute --preview <id> --request-id <uuid4-hex>
--yes --confirm-target <address> --oauth-client <path> [--port 18082]` 为 M 类；实际
删除前核对 binding、profile、manifest 和临时完整 scope。只有交互终端能显示 OAuth
URL；新执行拒绝 `--json`/非 TTY，已完成 receipt 可离线重放。正常 sync scopes/凭据不变。
Expiry 限制首次 start（30 分钟），已开始任务以原 key/清单恢复；未知删除先 get
核对同一 ID，网络不确定不继续。草稿编辑产生的新邮件 ID 不纳入旧清单。
不提供 source 删除、DB reset、unknown insert retry 或隐式 resume。CLI 输出仅固定
汇总和本地 preview ID，不支持 `--public` 导出；真实删除需另批准实际 preview。
完整风险、备份和容器调用见 [target-cleanup runbook](target-cleanup.md)。

清理 preview 的固定清单可能包含合法的外部 agent 已发送邮件/草稿；它们不是必须清除的同步异常。批准清单意味着批准删除其中这些内容，操作者必须单独确认，既有清理授权不覆盖新清单；本轮不新增筛选选项或任何真实删除权限。

`restore plan --backup <path>` 和 `maintenance inspect/check` 默认 offline、metadata
only；`restore apply` 需明确 destination/backup、停机锁和确认，保留 recoverable 旧
状态或按 runbook 的成套备份，不删除用户其他目录。恢复 stopped/paused/generation、
pending jobs/intents；live 核验未完成时保持写入禁止。Restore 不依赖 Gmail 正常才能
将本地库恢复为可诊断状态，也不承诺 DB 丢失后可从 target 全部重建。

`migrate plan/status` 离线检查当前 DB 与所运行 image 的 migration path；`migrate
apply` 停机持锁、先 backup、事务/版本检查，失败保原库和明确恢复状态。普通首次
startup 自动完成受支持、安全的初始化/迁移，不要求每次 Compose up 手工迁移；
复杂升级和不兼容 schema 按 maintenance plan/runbook 执行，不自动重建空库。

Upgrade 是 host Compose + image 内 CLI 的完整操作路径：选择明确 target image
digest→停止 sync container→旧版本 backup/verify→用新 image 的 maintenance check 和
migrate plan/apply→Compose 启动→status/doctor/health/provenance/state 检查。
若 schema 无降级路径，rollback 使用旧 image + 成套备份；禁止只换旧 image 并忽略
schema。CLI 不实现在线自更新、不自动执行 Docker daemon API；部署脚本和文档应
让每一步可直接从镜像运行，无 host Python/uv 安装要求。

镜像提供已安装的 `facet` entrypoint（默认 command 为 `run`），容器 CLI 的标准
路径如下；auth 的单次 loopback port/SSH 转发另按 OAuth helper runbook 配置，不
增加常驻公开端口。One-off 的状态挂载与运行服务一致，不能改用空 volume 绕锁：

```text
docker compose exec -T facet facet status --json
docker compose exec -T facet facet queue list --json
docker compose stop facet
docker compose run --rm --no-deps facet maintenance inspect --json
docker compose run --rm --no-deps facet backup create --destination /data/backups/upgrade --request-id <backup-key> --yes --json
docker compose run --rm --no-deps facet backup verify --backup /data/backups/upgrade --json
docker compose run --rm --no-deps facet restore plan --backup /data/backups/upgrade --json
docker compose run --rm --no-deps facet migrate plan --json
```

## JSON、错误与退出码

`--json` 的 stdout 恰好一个 versioned JSON document；不混 banner、progress、trace
或 OAuth URL。Stderr 只放受控固定错误/进度码，DEBUG 也不能泄漏输入或 provider
response。List 有 bounded `limit`/opaque continuation，稳定单位与 sampled_at；不
把 provider 原始 page token 或 raw row 直接返回。

结果 envelope 包含 `schema_version`、固定 command name、`status`（completed /
blocked / needs_attention）、受控 `code`、allowlisted `data`、typed warnings。长任务
进度从本地聚合 status 查询，不引入异步 operation receipt 协议。Empty queue 和 unknown
metrics 不混淆；unknown/stale 不用零/green 代替。

| Exit code | 语义 | 自动化应做的事 |
| --- | --- | --- |
| 0 | 请求成功：结果 completed，或本地 mutation 已持久化 | 读取 status；业务投影仍以 mapping/job 状态为准 |
| 2 | 参数/config/schema 或请求格式错误 | 修正输入；不要重试 mailbox mutation |
| 3 | 未确认/未授权、scope/binding/generation/preview guard 拒绝 | 提交缺失决定或新 preview；`--yes` 不能绕过 |
| 4 | 锁冲突、sync owner 不可用或运行方式冲突 | 查看本地 status；不要创建第二 writer 或盲重发 |
| 5 | Auth/network/rate-limit 等可恢复依赖不可用 | 保留 jobs，reauth/等待恢复；offline status/backup 仍应可用 |
| 6 | 具体 work/检查需要 attention 或存在部分/终止失败 | 读取受控类别和 scope，按 review/recovery 处理 |
| 7 | 持久化/内部一致性失败 | 停止相关写入/advance，按维护 runbook 恢复；不初始化空库 |

`status/queue list` 成功展示 blocked work 时可退出 0，`doctor` 验证发现故障按上述
类别返回非零。Mutating command 在结果未知时保本地 unknown 状态；不能用 exit
5 就让客户端重新发 insert。stderr 不回显未过滤 exception；local details 仍不输出
raw、body、subject、per-message addresses/headers、attachment names 或 credentials。

## CLI output 隐私

Local private metadata 可包含必要的 binding addresses、normalized rule values、
source/target object IDs、generation/attempt/epoch、digests 和必要路径，按命令
allowlist 与 `--private-metadata` 提供，用于人工定位/处理。它不是公共 telemetry，
不能上传 GitHub、CI、镜像、截图或 PR。Mail bodies/raw/snippets/HTML/完整 headers/
附件内容和名称/凭据/unfiltered provider errors 在任何 CLI 输出模式都禁止。

Public status/doctor JSON 使用独立 aggregate DTO，没有地址（含 masked）、规则值、
custom labels、Gmail/RFC IDs、fingerprints、paths、hostnames、OAuth URLs 或内部
receipt。JSON 不是自动脱敏保证；DTO field sources、typed errors 和行为 sentinels
都需验收。操作临时使用 MIME 只在 bounded memory 内，不产生 CLI `.eml`、report
spool 或内容缓存。Backup 私密 credential 文件是成套备份的一部分，不成为 console
输出、诊断导出或公共 artifact。

## CLI 验收矩阵

| ID / gate | 实际端到端验收 | Owner |
| --- | --- | --- |
| CLI-01 / G1 | 新环境 init/config validate、绑定拒绝、auth-status/offline doctor、schema inspect；已有状态不覆盖，JSON/退出码与非 TTY guards 可测；spike 独立 | M1-01/03/04/05/06 |
| CLI-02 / G2 | 完整同步入口复用细分操作自动完成当前规则的非空历史 discovery/backfill 和 History/action ingestion；细分 preview/start 也可独立完成；真实 CLI subprocess、insert/readback/映射、unknown recovery 和重启去重，不直接填 DB 绕命令；source_missing 可解释 | M2 |
| CLI-03 / G3 | 规则按处理时生效状态，effective_at 作审计，不保证邮件/规则严格时序；规则新增后新的有意 sync/细分 start 可通过新 epoch 补齐指定历史；普通 run/restart/action/reconcile 不回扫任意历史，已知 gap 可覆盖整个停机窗口；pause/resume/History gap range guards、无 scope/过期 preview 拒绝、init/setup/独立 preview 零 insert | M3 |
| CLI-04 / G4 | 前台 sync/one-off 命令共享唯一 writer lock，status offline/Gmail down；reconcile/audit 可续、bounded repair；pause ingestion 和 mutation 边界正确 | M1-03、M3/M4 |
| CLI-05 / G5 | mode/实际 scope 检查、legacy report、readonly 零 source mutation、blacklist/stop generation、cleanup 重放；resume 不复活 stopped | M4 |
| CLI-06 / G6 | 全套 CLI 可从 Compose image 执行；stop/one-off DB+credential 协调锁；backup/restore 与 auth/refresh 并发不跨版本；verify/migrate/check offline，invalid_grant 时仍能看 pending；无 host Python | M6-01/02/03/06 |
| CLI-07 / G6 | 明确 target digest 的 upgrade/rollback、容器重建状态保留；真实 re-auth 后 jobs 继续，unknown intents 先恢复，再恢复写入 | M6-02/07/08 |
| CLI-08 / 全阶段 | 注入 body/token/provider error、ID/address/path sentinels，分别检查 private/public CLI、stdout/stderr、logs/files；非 TTY 不隐式确认、request key 不能被不同 payload 复用 | P1-02、M1-05、各命令 owner |

CLI-01 至 CLI-06 的逻辑先用 subprocess/fake Gmail 和合成 metadata 做 offline E2E，
包含容器停止、授权失效、DB 锁冲突、unknown insert、分页与磁盘故障；不只测试
parser/help 或直接调用内部 handler。Compose E2E 使用最终 image、非 root UID 和
持久 volume，证明与本地 CLI 的 JSON/退出码/锁一致；不额外启动多个 sync owner。
所有命令需要完整 help、参数错误与支持/拒绝状态的测试。

Real auth/re-auth、Gmail API/UI、repair 或故障撤销权限演练另需 D3/D4/D7，按选定
账号/thread/rule/scope 执行并记录实际证据；offline fake 成功不替代这些 live gates。
G6 只有完整 CLI 功能、容器流程和运维 E2E 全部通过才关闭。当前文档不宣称任何
生产 CLI 已可用。
