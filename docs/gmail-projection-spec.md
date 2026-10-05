# Facet Gmail 投影实现规格

日期：2026-10-02

状态：Phase 1 实施基线

关联文档：[项目计划](project-plan.md)、[产品契约](product-contract.md)、[Dashboard 规格](dashboard-spec.md)、[Spike 实测](phase-0-gmail-spike-results.md)。

本文将已讨论的 Gmail 行为收敛为可实现的配置、数据库、队列、恢复和 CLI 契约。所有 CLI 和正式包路径均为计划中的接口；当前已经可运行的工具仍为 `facet-spike`。

## 配置和账号

正式运行环境使用 Python 3.12 及以上、Google API Python 客户端、PSL 库和 SQLite。建议配置以 YAML 保存，初始规则首次导入数据库，之后通过 CLI 或 action 更新；再次启动不覆盖用户已学习或删除的规则。

```yaml
projection:
  id: gmail-default
  source_email: primary@example.com
  target_email: agents@example.net
  source_mode: readonly
  own_addresses:
    - primary@example.com

sync:
  backfill_lookback_months: 6

rules:
  allow_domains:
    - ihg.com
    - hyatt.com
    - email-marriott.com
  allow_senders: []
  blacklist_senders: []

target:
  inbox: false
  projected_label: null

web:
  enabled: true
  host: 0.0.0.0
  port: 8080
  refresh_interval_seconds: 10
```

这些域名是候选 seed，不代表已验证所有 provider 的认证和别名。HSBC 不使用模糊模式，待实际 sender domains 确认后枚举加入。初始化按 UTC 和日历月计算并持久化六个月截止时间，Gmail query 使用明确时间边界，最终由本地规则复核。

Source 默认 `gmail.readonly`，便利模式 `gmail.modify`。Action label metakinds 固定为
`add_sender`、`add_domain`、`blacklist`；默认读取 `AI/AddSender`、`AI/AddDomain`、
`AI/BlackList`，私有 CLI 可为每类设置一个精确名称并在 remove 时回退默认。Facet
只读查找 source labels，不创建或修改 Gmail label，不扩大 scope，已有绑定无需 reauth；
旧 provider label ID 的 pending event 转为 typed attention/unknown，不重写历史或静默重放。
Target 固定 `gmail.insert` 和 `gmail.readonly`；后者用于搜索、回读和 audit，insert scope 本身不提供这些能力。[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)、[messages.list scopes](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)

若用户指定已存在的 target label，读取其 label ID 并在 insert 时附带。自动创建 target label 是可选 setup 能力，需要单独核对并申请 `gmail.labels`；默认配置不需要。便利模式中的 `AI/Tracked` 和 `AI/Learned` 默认关闭，action labels 的创建和清理可启用。

每次启动先回读两个 profiles，与持久绑定核对，拒绝相同账号、角色互换或未经初始化的身份变化。Own-addresses 使用明确地址列表，不额外申请 settings scope，也不擅自合并所有 plus 或 dot 地址。

正式初始化创建新的 DB 与 source checkpoint，不沿用 `.facet-spike/` 中的 cursor、实验映射或旧 target IDs。生产 target 必须是全新、专用于本 projection 的 Gmail 账号，由操作者在 OAuth 前声明并配置 Facet 为唯一应用写入者；不得配置其他应用、forwarding、legacy projection 或人工导入/发信写入。AI connector 只能读取。Gmail metadata/OAuth scopes 不能证明该声明，也不能识别所有第三方写入者。

Target OAuth 后、首次 projection/insert 前，部署验收必须通过只读 Gmail 检查核对 target 账号/binding，并覆盖普通邮件、草稿、Spam 和 Trash；收件箱为空不代表 All Mail 或整个 mailbox 为空。发现 unexpected/unmanaged 邮件、旧 forwarding/spike 副本或 binding mismatch 时 fail closed：保持投影写入阻止并报告/进入 attention，不自动认领、删除、移标或清理。OAuth consent 不是 Gmail mailbox write，授权成功本身不完成邮箱前置检查；当前 setup 仅授权和读取 profile，本次文档修改不新增该 runtime 检查。

既有部署不得自动迁移或清理以满足新约束。在下一次部署验收前保留 mappings/jobs/audit，缺少操作者声明或可观察检查时保持 blocked/report-only；未知旧邮件不能作为新 mappings。Source action labels 不存在时，只读模式继续提供 CLI 管理并说明如何手工创建；便利模式才自动创建。

OAuth 使用 Desktop loopback helper 和独立 token 文件，支持本机浏览器或 SSH 转发。Refresh 写入由单一账号管理器序列化并原子替换；不让多个 worker 竞争覆盖 token。External Testing 的 Gmail refresh token 有七天到期条件，长期运行文档必须说明发布状态与重新授权，而不是保证 token 永不失效。[Google OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)

## 模块边界

```text
src/facet/
  config.py
  runtime.py
  gmail/          OAuth、source、target、labels、retry
  db/             schema、migrations、repositories、backup
  projection/     rules、admission、worker、fidelity
                  backfill、history、actions、recovery、reconcile
  cli/            auth、status、rules、backfill、review、audit
  status/         运行快照、聚合计数、公开诊断
  web/            只读 HTTP API 和打包静态 Dashboard
tests/
  unit/
  integration/    显式开启的真实 Gmail 测试
```

Docker image 内的一个前台进程负责 History、backfill、投影和 SQLite 写入；Docker/Compose
负责启动、重启和持久 volume。第一期采用单 writer、按 thread 串行的简单运行模型。若以后
增加 worker，每个 worker 必须使用自己的 HTTP transport；官方 Python 客户端所用的
`httplib2.Http` 不可在线程间共享。[Google Python client thread safety](https://googleapis.github.io/google-api-python-client/docs/thread_safety.html)

CLI one-off 命令与前台进程共用 state directory，并取得同一个 writer lock；不引入独立
daemon、IPC 或 request-receipt broker。容器外的 service manager 只负责容器生命周期，
不属于 Facet 的运行时契约。

同一 source thread 的 prepare、insert 和映射更新串行化；第一期按 discovered jobs
顺序处理，不把跨 thread 并发、实时优先或公平调度作为交付前置。数据库事务不跨网络等待，
单个异常 thread 保留在可解释状态，不使其他持久 jobs 静默消失。

## 数据库和持久状态

使用 SQLite WAL、foreign keys、busy timeout 和迁移版本；关键事务使用可靠落盘设置。数据库位于 NAS 本地磁盘的 bind mount，不能假定 NFS 或 SMB volume 满足 WAL 条件。[SQLite WAL limitations](https://www.sqlite.org/wal.html)

| 表 | 关键键和字段 | 职责 |
| --- | --- | --- |
| `projections` | ID、source 和 target binding、mode、状态、初始化 epoch | 运行身份和隔离 |
| `rules` | projection、kind、规范化 value、effective_at、来源、enabled、auth policy | 规则权威状态 |
| `tracked_threads` | projection 和 source thread 复合主键、active、reason、generation、停止时间 | Thread 持续授权和取消 |
| `thread_targets` | projection、source thread、target thread、anchor 标记 | 保存正常和 fallback 的实际 thread 集合 |
| `mirrored_messages` | projection 和 source message 复合主键、source thread、target IDs、RFC ID、日期、hash、fingerprint version、状态 | 逐消息 provenance 和去重 |
| `source_events` | projection 和稳定 event key 唯一、history ID、typed payload、观察时间 | 可重放的 History 输入 |
| `sync_jobs` | 稳定 job key 唯一、message 或 thread、generation、priority、attempts、next_attempt_at、状态 | Durable 工作队列 |
| `action_commands` | projection、history record、label、thread 唯一，执行与清理状态 | 学习命令聚合和重放 |
| `insert_attempts` | message key、attempt ID、intent 时间、结果是否确定、恢复检查 | Gmail 写入危险窗口 |
| `checkpoints` | projection、source cursor、last covered time、discovery cutoff、各 reconcile 进度 | 分阶段恢复 |
| `audit_events` | projection、事件、对象、reason、before 和 after、时间 | 规则、授权、停止和异常审计 |
| `runtime_metrics` | projection、时间桶、已确认成功数和错误分类计数 | 聚合运行状态，不存邮件细节；不构成延迟承诺 |

Event key 使用 typed event 的 message、label 和 history record 等字段；message jobs 按 source message 去重，thread jobs 按实际任务 epoch 去重，不使用一个 `UNIQUE(job_type, source_message_id)` 表达所有场景。

DB 不存 raw MIME、正文、HTML、snippet、附件 bytes、完整 headers 或每封邮件的 Subject/From/To/Cc 副本。必要的账号 binding 和规则地址为内部私密配置。Typed event payload 仅保存所需 IDs 和状态，错误保存标准化 code、role、attempt 和时间，不保存任意 exception 或 Gmail response；fingerprint 仅保存 digest 和版本，不保存用于计算它的完整头部。

History ID 保持字符串，不能推测连续或执行加一。Target IDs 在每封 message 上保存；source thread 到 target thread 可能因 fallback 变为一对多，也不能假定 target 会永远隔离所有 source threads。

Action、规则变更、thread active 状态和对应 jobs 尽可能在同一 SQLite 事务完成。所有 work claim 包含 generation；执行前重新检查 active 和 generation，停止后旧队列不会重新投影。

## Admission 和规则

先解析唯一有效的 From address，规范化 domain 和 IDNA，再做 exact sender 与带点边界的 domain 匹配。`hyatt.com` 可匹配 `mail.hyatt.com`，不能匹配 `evil-hyatt.com` 或 `hyatt.com.attacker.example`。PSL 用于学习 registrable domain 和拒绝公共后缀；其版本可审计，更新不隐式改写已有 rule。

新 thread 的自动决策顺序为 mailbox eligibility、blacklist、allow sender 或 domain，再决定 admission 或 review。没有匹配为忽略；格式歧义、账号不匹配或 provider 故障不放行。初始 backfill 的规则可在六个月窗口内应用；动态规则保存生效时间，自动 discovery 和 reconcile 不越过该时间向历史扩张。

用户于 2026-10-05 正式删除 source-path attestation 和 sender authentication gate。Gmail 负责 SMTP 认证与邮件分类；Facet 只读取 metadata 并执行披露规则，不调用 DNS/DKIM、不为 admission 获取 raw、不使用 `Authentication-Results` 决策，也不声明发件人真实或内容安全。旧配置中的 `rules.authenticity: require_trusted_auth` 仅兼容读取、无行为效果，新配置不再写出该字段。持久化的 `auth-v1` 保持为兼容的规则策略 token，不再表示认证证明，无 DB migration。

Review 是 metadata/provider 等异常处理，不是第一期的常规 thread 选择入口。Action 学习可以更新规则；future rule 仍遵守精确匹配和 effective_at。已 tracked thread 继承 thread 授权，其未来消息不再逐封要求 sender 匹配；这一披露范围必须在 preview 和文档中说明。

Source `SPAM`、`TRASH`、草稿默认不触发新 admission。Tracked thread 复制可用且非草稿的完整消息；其中包含 Spam 或 Trash 状态的历史应在 preview 提示。Source 删除和 mailbox 状态不会同步为 target 删除。

## 投影和保真

获取 source raw，保持原始 bytes，不做 MIME parse 再 serialize，不注入 marker headers。通过 `messages.insert` 写入 target；该方法不发送邮件。[Gmail messages.insert](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/insert)

Source raw SHA 用于本地完整性。跨邮箱 fingerprint 包括稳定的 From、To、Cc、Subject、Date、Message-ID、References、In-Reply-To，以及 MIME multipart 层级、按原顺序的 leaf 类型与参数、disposition、文件名、Content-ID 和 decoded payload hashes；版本化规范化规则，不把 Gmail 新增的 transport headers 算入等值比较。原始 transport headers 的保留在保真测试中单独核对。

按 source internalDate 排序，同日期用 source message ID 稳定排序。首封建立 target anchor；后续带 anchor thread ID 和原始 reply headers。Gmail thread 合并依赖指定 thread ID、References、In-Reply-To 和 subject 条件，不能只依赖 thread ID。[Gmail thread requirements](https://developers.google.com/workspace/gmail/api/guides/threads)

确认是 threading mismatch 的错误才可 fallback 不带 thread ID；不对任何 400 一律 fallback。记录实际返回的 target thread，不覆盖或丢失原 anchor；正常误合并或分裂均在 audit 中显示。

合法 Date 使用 `internalDateSource=dateHeader`。Original Date 与 source internalDate 可能不同，不能将二者必须相等设为所有邮件的硬条件。Date 缺失或非法时使用 `receivedTime`，记录目标排序可能落在导入时刻，在 M2 验证降级行为；原始 Date 不改写。Target 回读保真失败进入 review，不自动再 insert 一次。[Gmail InternalDateSource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/InternalDateSource)

Raw 只在读取、插入和目标核验期间驻留内存，计算 hash 与 fingerprint 后只持久化 digest、必要 IDs 和 insert intent。不建立磁盘 spool，也不存入 DB、日志或 report。重启后重新读取 source；source 缺失时先检查是否已有成功的 target 插入，无法恢复则保留 `source_missing` 状态。只保留基本单消息内存上限，不实现跨 thread 的复杂 raw budget 调度。

单消息内存上限用于避免异常大附件导致进程失控；超限 job 保留可解释状态。磁盘无法落盘
metadata 时停止推进 cursor，状态显示 backpressure；Web 接口不持有 raw 引用。

## Insert 状态机和恢复

```text
queued -> prepared -> inserting -> inserted
                       |
                       +-> pending_recovery -> inserted
                       |         |
                       |         +-> needs_attention
                       |         +-> retry_wait -> prepared
                       +-> retry_wait

任意尚未发出的状态 -> cancelled 或 source_missing
```

在调用 target 前持久记录 intent。明确未写入的限流或认证拒绝可以重试；timeout、断连、进程退出以及无法确认结果的服务端错误进入 `pending_recovery`。禁用客户端对 insert 的无条件自动重试。

恢复检查的重试节奏由实现决定，只用于诊断和恢复，不构成同步延迟承诺。按 RFC Message-ID 查询时包含 Spam 和 Trash；候选还要与 fingerprint、既有映射及账号 binding 核对。

此外必须核验“候选属于本次生产 insert”的归属证据。唯一内容匹配可能是此前存在的
unmanaged 或 spike 副本，fingerprint/account/mapping 检查本身不足以证明来源；旧
Date/internalDate 也不是 target 创建时间。M2-04 insert-attribution ADR 应设计并
验证候选排除或 fence 等证据机制，包含竞争、分页/过期和其他写者反例；方案未验证
或归属未知时保持待处理，不自动认领。

- 唯一内容匹配、未被不兼容 source 映射占用且通过已评审的 insert 归属核验：绑定
  target IDs；候选在 Spam 或 Trash 时额外报告可见性异常，不重复插入或宣称正常可见。
- 多候选、相同 Message-ID 但内容不匹配、映射冲突：`needs_attention`。
- 多次搜索为空不能证明未插入：默认保留待处理；只有经 ADR 明确的受限重试策略及
  对应范围/风险决定允许时才重试，保留可能重复的风险和恢复预算，不盲目重复 insert。
- 无有效 Message-ID：有限时间和 metadata 候选筛选，加内容核验；不能唯一识别则待处理，不以 From 和 Subject 相同直接认领。

结果未知期间暂停同 thread 的后续 insert，其他 threads 正常运行。查到多个 message 不自动删除。全 target audit 发现 RFC ID 相同也不能立即认定它们是重复，需比较内容与 source mappings。

## 初始化和 backfill

首次启动可授权和 preview，不自动复制历史；显式 `backfill start` 创建初始化 epoch。

1. 在任何 discovery 前获取并持久保存 H0 和固定时间 cutoff。
2. 候选分页发现后本地复核规则与 admission，持续写入持久 thread jobs。
3. 从 H0 开始消费 History，与 backfill 共享 message 去重和 thread 调度。
4. Discovery 完成且 History 追到一个明确边界后，标记发现阶段完成；backfill queue 清空后才标记初始投影完成。

Page token 仅为短期扫描提示；过期或进程重启后可重新扫描同一个固定时间窗口，依赖唯一键去重。`backfill stop` 暂停领取历史 jobs，不取消实时跟踪；resume 延续原 epoch，不重算不断移动的六个月 cutoff。

新增规则只处理当前明确选择的 thread 和未来事件。历史扩张通过新的显式 backfill epoch，并记录规则与窗口；每天校对不隐式变成全历史 admission。

## History 和过期恢复

只处理 `messagesAdded`、所需的 labels events 和删除标记，避免把通用 `messages` 与 typed events 重复执行。每页先持久化 events 和 jobs；完整消费该轮所有分页后才保存最终 historyId。中途中断可以从旧 cursor 重读，唯一键消除重复。无事件的成功 poll 同样记录覆盖边界。

History polling、分页、cursor、事件持久化/去重和 `messagesAdded`/action-label 规则更新
属于第一期交付，与初始六个月 discovery/backfill 共用 projection jobs。产品不承诺 poll
间隔、队列年龄或端到端延迟；这些时间只作为状态事实记录。

Gmail History 可能过期并返回 404，不能假定固定保留时间。[Gmail synchronization](https://developers.google.com/workspace/gmail/api/guides/sync)、[history.list pagination](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list)

恢复步骤为记录新的 H1，再对全部 active tracked threads 比较 source message 集合，并按上次可靠覆盖时间减 safety margin 到恢复开始时间重新 discovery。窗口覆盖整个停机期，即使超过原六个月；动态规则仍受 effective_at 限制。恢复工作持久入队后，从 H1 消费扫描期间新增事件。

若没有可信的上次覆盖时间，报告未知 gap 并要求明确恢复范围，不自行披露全历史。History 已过期且 action label 在 gap 中添加后又移除时，单凭当前快照无法重建该命令；如实报告这一限制，保留现有规则，不虚构成功处理。

## Label 命令和 BlackList

支持 `AI/AddSender`、`AI/AddDomain`、`AI/BlackList`。按 `(projection_id, history_record_id, label_id, source_thread_id)` 聚合，一次 UI thread 操作只执行一次。

倒序寻找最近 From 不属于 own-addresses 的消息；无法找到或 sender 格式有歧义时进入 review。AddDomain 使用 PSL，不学习用户 primary domain。Command、rule 和 thread jobs 先落盘，便利模式随后清理 label；清理失败只重试清理，不重放业务效果。

只读模式保留标签，并记录已观察的 activation；移除再添加为新命令。首次初始化枚举 legacy labels 仅报告，不当作新命令，避免执行之前 Apps Script 遗留的标签。Current label snapshots 不能代替 History event 去重。

Blacklist 精确 sender 优先于新 thread allow。当前 thread 变 inactive、generation 增加，取消未开始的旧 work；在途 insert 返回后仍保存事实。删除 blacklist 不自动恢复已停止 thread；恢复通过显式 track 操作，并留下新的审计记录。

## 定期 reconciliation

| 时机 | 范围 | 自动行为 |
| --- | --- | --- |
| 启动 | Stale insert intents 和未完成 jobs | 恢复可确认映射，继续安全 work |
| 每天 | 全部 active tracked source threads；增量候选窗口 | 按 ID 比较补漏，规则生效边界不变 |
| 每周 | DB 中已保存的 target message IDs | 校验存在性，缺失、Trash、异常分类报告 |
| 按需 | 全 target metadata 与待确认候选 | 检测重复和未映射内容，按需读取 raw 核验 |

校对保存 epoch 和进度，限流、可恢复。Target 人工删除默认报告，显式 `--repair-missing` 才重新投影；人工放入 Trash 的内容不被自动认领为正常可见。未知旧邮件、此前 forwarding 和 spike 的副本不自动纳入生产映射，也不清理。

全 target audit 发现 unexpected/unmanaged 内容时，专用 target 的部署前置条件不再满足，应停止新的投影写入并报告；不能用 audit/recovery 或内容相同绕过唯一写入者声明和 insert 归属核验。已记录的 mappings、pending intents 和审计证据保留，已有在途 insert 的未知结果仍按恢复协议处理，不宣称能撤销在途请求。

## 运行故障和备份

403 要按 Gmail reason 分类：rate limit 退避，权限不足报 scope 问题，storage full 暂停 target；不可把所有 403 作为同一种 retry。429 尊重 Retry-After，5xx 和网络结果未知走恢复策略。401 或 `invalid_grant` 暂停相关方向，队列保留并提示重新授权。

Source 暂停读取不妨碍处理当前进程已读取的内存 payload；target 长期暂停时释放 raw 内存，source 仍可将事件入库，恢复后重新读取。磁盘无法持久化 events 时不能推进 cursor；恢复后按 gap 协议处理。超过 retry 预算的单个 job 显示明确 error 或 review，不静默删除。

SIGTERM 停止领取 work，在有限时间内提交结果；未确定的 insert 留待恢复。单进程写入锁
阻止两个 sync owner 操作相同 projection，status 和 doctor 允许只读查看。

Phase 1 备份要求先停止前台 sync container，并持有写入锁；用 SQLite backup API 生成数据库副本，再保存配置、binding 和凭据。备份不包含邮件完整内容或 pending raw；恢复 jobs 时重新读取 source。不能只在运行中复制主 `.db` 文件而忽略 WAL。Restore 在停止服务后核对账号并恢复 pending recovery，再恢复工作。迁移先备份，失败不自动重建空数据库；不支持降级的 schema 必须明确说明回滚办法。

Compose 将本地数据目录挂载到 `/data`，计划布局如下；初始化时将私密运行目录加入 Git ignore，并校验非 root 进程的读写权限。

```text
/data/
  config.yaml
  facet.db
  credentials/
    source-token.json
    target-token.json
```

发布镜像和 Compose 使用明确版本或 digest。镜像不包含账号配置、token、raw payload 或 spike evidence。Web HTTP 端口默认仅发布到宿主机 loopback，或只在与前置 Nginx 共用的 Docker 网络中暴露；HTTPS 与用户认证由 Nginx 负责。升级前保存旧版本与状态备份，schema 不兼容时恢复成套备份再运行旧版本。

Phase 1 要求首次私密配置/OAuth 完成后 `docker compose up -d` 一命令启动，容器
重建无需重新交互授权且保留 binding/schema/checkpoint/jobs。Startup 不自动开始
初始 backfill；由 CLI 明确 `backfill start` 作为一次披露确认。镜像由 Actions 构建/发布；PR 不 push，发布使用 approved registry/
trigger、full source SHA/digest、amd64/arm64、SBOM/provenance 和匿名拉取验收，
具体权限及工作包见 [执行计划](phase-1-execution-plan.md)。

## Web Dashboard

同一进程提供只读 Dashboard 和聚合 API，不启动额外 sync worker 进程。页面展示状态、backfill 与增量进度、唯一成功数量、异常分类和诊断快照，完整字段和验收见 [Dashboard 规格](dashboard-spec.md)。

公开响应使用独立白名单模型，不返回邮件内容、账号地址、规则值、message/thread/history IDs、RFC Message-ID、原始 provider 错误或本地路径。Dashboard 的诊断读取已脱敏快照；页面刷新不调用 Gmail，不提供规则编辑、OAuth 或同步控制接口。应用只提供 HTTP，不内置 HTTPS 和 Web 用户认证。

## 计划中的 CLI

完整命令、幂等 request key、JSON/退出码、确认、
private/public DTO 和分阶段验收以 [完整维护 CLI 契约](cli-spec.md) 为准；这些是
必交付接口，不是 help-only 骨架。以下仅展示默认 offline 诊断路径：

```text
facet config validate --json
facet gmail auth-status --json
facet status --json
facet doctor --json
facet maintenance inspect --json
```

CLI 规则变更通过事务/audit 和唯一 writer，不直接绕过 queue insert。Backfill/recovery/
repair/start 都有对应 scoped preview 入口；queue retry 不绕 unknown intent。
需要扩大披露或维修状态的操作明确范围/确认；稳定 request key 用于本地幂等，不提供
跨进程 receipt broker。Status/doctor 默认 offline；live check 显式选择，不因 invalid_grant
失去本地 pending 诊断能力。Private metadata 需 opt-in，public DTO 遵守 Dashboard
边界；所有模式禁止正文/raw/凭据/provider response。

CLI 的实际 writer 协作使用共享 lock 和 SQLite 幂等键，mutation 的 crash/replay 不能
重复规则效果；read-only status/doctor 不申请写入所有权。

Offline inspect/backup/restore/migrate 不要求 Gmail 可用，恢复后先保
`binding_verification_pending` 写入禁止，再在 startup 核验 live profiles/unknown
outcomes。成套维护同时协调 DB 与 credential ownership，避免并发 auth/refresh
跨版本；one-off container 与前台 sync container 共用 state/锁，无 host Python 要求。

## 交付和实施顺序

按项目计划 M1 至 M6 实施，每阶段先更新具体改动记录再编码。当前阶段仅完成计划和规格，不启动生产 backfill、不切换 OAuth scopes、不修改 Gmail 内容。发布验证使用明确选定的 sandbox 数据，真实账号长期使用安排在基础恢复能力完成之后。

整体 Phase 1 计划需用户 review/明确批准 G0 才开始产品实施；总计划技术 review 不
替代该批准。Phase 内独立 agent plan/code review 和已批准的 merge/image scope
在 G0 后执行，真实 Gmail/deployment gate 仍需各自范围决定。
