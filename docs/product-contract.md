# Facet Gmail 产品契约

日期：2026-10-02

适用范围：单用户 Gmail projection，Phase 1。

Facet 将用户选定的主 Gmail 内容投影到另一个 Gmail，供 AI agents 授权读取。Source 是投影内容的唯一事实来源；target 是用户可检查的披露视图，也可承载外部 agent 的发信和草稿。本文约定用户授权了什么、规则如何生效，以及服务遇到故障时提供什么保证。

## 数据访问和披露范围

AI agents 只连接 target。Facet 本身需要 source 读取权限；Gmail OAuth 不能将该权限限制为单独几个 sender。选择性由 Facet 规则和执行逻辑实现，物理隔离存在于 source 与 agent 所连接的 target 之间。

生产部署仍使用为本 projection 全新建立的专用 target Gmail 账号。用户于 2026-10-07 修正 2026-10-05 的前提：Facet 是投影写入者，不是邮箱唯一应用写入者；经独立授权的外部 AI agents 可以在 target 发信和创建草稿。From 使用已绑定 source 身份，回复直接进入 source；agent 的发信权限、send-as 配置及回复路由由外部 agent/Gmail 集成负责。Facet 不提供 send/draft API、不替 agent 配置发信身份、不扩大同步 OAuth scopes。不得将 target 用作其他导入器、forwarding 或旧 projection 的接收邮箱。

OAuth 前由操作者声明 target 的专用用途及获准的 agent 发信/草稿写入。Target OAuth 后、首次 projection/insert 前，通过只读检查核对账号 binding 与邮箱内容，范围包括普通邮件、SENT、草稿、Spam 和 Trash；不能用 Inbox 为空或 mailbox 总数量判断前置条件。

先保留已有 managed mappings 和具有独立归属证据的 insert 结果；未管理邮件中，带 Gmail `SENT` 或 `DRAFT` 标签且唯一有效 From 地址经既有规范化后匹配绑定 source 的邮件是允许的外部 outbound，不因未管理而报错或阻止投影。From 单独匹配或任意未映射邮件并不足够；标签和 From 仅是分类输入，不是认证或 writer 身份证明。允许的 outbound 不计入投影成功数，不自动认领、修复为 source 副本，也不作为 unknown insert 的自动恢复绑定候选；pending intent、RFC ID 或 fingerprint 相同本身不能证明本次 insert 归属。

其他 unexpected/unmanaged 内容（如外部收件、导入或 spike 副本）和账号不匹配仍 fail closed：阻止新的投影并报告，不自动认领、删除、移标或清理。授权成功不代表这项前置条件已通过，也不启动同步。Gmail metadata/OAuth scopes 不能证明所有应用的写入活动；本次是契约修正，完整 runtime 分类与 live 验收仍待实现/验证。

既有部署不能靠自动清理或 retroactive claiming 迁移到此约束。在下一次部署验收前应保留既有 mappings、jobs 和审计证据，保持写入阻止/报告状态，直到操作者声明和可观察检查完成。之后 audit/recovery 仍不能把未知内容自动纳入生产映射。此变更仅定义契约；本次文档交付不声称已实现新增 runtime enforcement 或完成 live 验收。

一封 message 被允许后，整个 source thread 的全部可用邮件被投影，包括早于六个月的历史、用户自己的回复、其他参与者、附件和原始 headers。已跟踪 thread 的后续消息继续投影，即使 sender 不再匹配最初的 allow rule。

这是一项 thread 范围的持续披露授权。Facet 不独立验证发件人真实性，也不声明正文、附件或后续参与者可信。邮件中的指令仍是外部数据，AI 产品需要自行处理其内容风险。

首次 backfill 和手动 admission 提供范围快照，说明完整 thread 的披露语义；邮件仍可能在快照后新增，因此它不承诺冻结未来会话。按 2026-10-07 用户决定，完整 CLI 同步入口自动完成范围准备、backfill 启动和增量运行，不要求用户先执行 preview 再执行 start。它完全复用细分命令的业务操作和检查，不是第二套同步实现；独立 preview 仍不写 target，细分命令保留用于维护和当前分步验证。

用户有意调用完整同步入口，表示按当前 enabled allow rules 和默认固定六个月 discovery 窗口同步授权线程；内部持久化该规则/窗口范围、请求键、H0 和执行状态。缺少账号绑定或 OAuth 时通过既有流程完成必要交互，不默选账号或扩大 scopes。已有工作续跑，已确认映射去重；新的历史范围使用独立 epoch，不重置 DB/cursor，也不复活 stopped thread 或盲重试 unknown insert。单独 setup、普通 run/容器重启和 preview 不构成新的历史扩张授权。该入口尚待实现，产品决定不等于 agent 已获新真实邮箱测试范围。

## 规则和学习

只支持规范化的精确 sender、域名及其子域匹配。公共后缀不可以作为 allow domain；不支持 `hsbc.` substring 或任意 shell glob。银行域名需经过确认后加入。

自动 admission 基于 Gmail source mailbox metadata 和配置的精确 sender/domain 规则。Gmail 负责 SMTP 认证与邮件分类，Facet 不重新验证 DKIM/SPF/DMARC，也不把认证 headers 作为 admission gate。Gmail 接收邮件不等于发件人真实或内容安全；规则匹配的正常非草稿邮件可以触发 thread 披露。格式歧义、账号不匹配和 provider 故障仍不放行。此边界由用户于 2026-10-05 明确确认，取代此前 source-path attestation 要求。

新增 sender 或 domain rule 不自动回扫相同域名的所有旧 thread；通过 action label 学习时，当前 thread 立即纳入。按 2026-10-07 用户确认，规则变更与邮件到达不保证严格时序一致：正常 History 处理和 gap 恢复按处理/扫描时选定的生效规则判断，不还原邮件到达时的规则版本，`effective_at` 保留为审计记录。已知 gap 恢复可纳入停机窗口内早于规则创建的邮件；扫描范围仍固定为整个已知停机窗口，不因此扩成六个月或全邮箱。恢复扫描使用开始时选定的当前规则范围以稳定分页，期间移除规则阻止新的 admission，不保证并发规则变更的精确切换点。其他历史范围扩展仍由新的有意完整同步调用或细分 backfill 显式启动；普通重启、标签学习和 reconcile 不触发任意历史回扫。

Agent 发信后的回复进入 source，由既有规则、tracked-thread 授权和 History 正常处理；未跟踪 thread 不因为是 agent 发信的回复就自动纳入。未来可考虑从 agent 发信的收件人发现候选规则，但 Phase 1 不实现，不从 target 的 SENT/草稿生成规则或授权，不新增 per-message To/Cc 存储。未来 sender/domain 选择、自动生效及历史范围需另行确定。

移除 allow rule 停止该规则带来的新 admission，已经纳入的 thread 保持跟踪。需要停止既有 thread 时，执行明确的 stop 或 BlackList 操作。

## 默认只读和便利模式

默认 source 使用 `gmail.readonly`。Facet 读取用户手工添加的 action labels，但不创建、清除或添加 source labels。按 2026-10-08 用户决定，History 仅提示哪些 thread 需要检查；Facet 按当前配置和当前 non-draft 消息的标签状态执行，不重放旧 add/remove 指令，不要求恢复旧标签含义。当前没有 action tag 就正常结束检查。

SQLite 持久记录当前标签激活是否已经处理。标签持续存在时不因新消息、参与者或重启再次学习；只有实际观察到不存在、后来再存在时才形成新激活。两次检查之间添加后移除、或移除后重加但未观察到中间缺失，不保证执行。修改配置映射到不同标签/新的 Gmail label ID 是新的观察身份。移除 tag 不撤销已学习规则、不复活已停止 thread；同时存在 BlackList 时，先阻止新 admission/停止当前 thread，不由 Add 标签覆盖。

首次运行先持久化 H0，再建立仅查询 action labels 的初始基线；已有标签仅记录，不执行业务。基线是逐 thread 的首次观察，不是瞬间冻结邮箱。升级不对全部标签重新静默基线化：只继承已证明执行且当前类别/标签匹配的旧记录，待处理通知按现状检查。此工程变更不构成真实邮箱操作授权。

便利模式显式申请 `gmail.modify`，自动创建和清理 action labels，并可开启可视化状态标签。该 scope 也允许 compose 和 send，Facet 实现中不提供这些操作；用户应理解 token 实际权限。[Google Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)

Target 使用 `gmail.insert` 和 `gmail.readonly`。默认投影到 All Mail，保留原 sender 和日期；Inbox 或专用投影标签按配置启用。Facet 不复制 source 的已读、星标、archive、Inbox 或 Sent 状态。

## BlackList 和未来撤回

BlackList 将当前选定的 external sender 加入精确 blacklist，并停止操作所针对的 thread。该 sender 的新 thread 不再自动 admission；同域其他 sender 不受影响。其他已经 tracked 的 thread 不因这次操作自动批量停止。

停止操作取消尚未开始的相关 jobs。已经发出、结果尚未返回的 Gmail insert 可能仍然完成，服务会记录它；不能承诺撤销在途请求。

已投影邮件默认保留在 target。Phase 1 没有 purge、retention 或自动删除。
用户于 2026-10-07 批准唯一例外：独立的 `target-cleanup` CLI，供操作者显式清理
专用 target。它不是同步的一部分：停机并持 writer lock，先用原只读凭据生成固定
邮件 IDs 的 preview，再显式确认目标账号、不可逆删除及该 preview，单独申请临时
`https://mail.google.com/` 权限。该 Google scope 实际允许读取、发送及永久删除，
Facet 命令仅提供固定清单的删除，不发送；token 不落盘、不替换同步凭据。
真实执行仍需独立批准实际 preview。清理不重建 DB、不改 jobs/mappings/cursors、
不解除 unknown insert，也不能通过 metadata backup 恢复邮件。参见
[操作流程](target-cleanup.md)。删除 target 内容也无法保证第三方 AI 产品删除其索引和缓存。

## 故障和一致性承诺

服务持久保存发现的工作，在正常权限、source 内容仍可读取、target 可写入的条件下持续恢复，直到成功或形成明确的异常状态。限流、断网、重启和 target 授权失效不导致 jobs 被丢弃。

Gmail 和 SQLite 无法共同提交事务。常规重启通过 source message ID 和本地映射去重；insert 成功后本地记录丢失时，通过 target 搜索及内容核验尽量恢复。Message-ID 缺失、重复或索引延迟可能导致重复或待人工处理，不承诺 exactly once。

按 2026-10-09 用户决定，普通启动/同步轮次自动检查 pending unknown insert。
从持久化 dispatch 时间起至少五分钟后，若 target 查询成功且没有候选、source
digest/RFC 未变、账号 binding 和 active generation 有效且没有 mapping，就按
未发现副本的恢复策略自动重新排队补写，不要求逐条 preview/人工确认或单次额度。
这是明确接受残余重复风险，不是 Gmail 五分钟一致性保证；旧请求仍记 unknown，
不伪造确定失败。查询超时/鉴权/限流不等于不存在；候选或归属/内容歧义保留异常。
补写再次 unknown 也经过同样的等待和新检查，不能连续立即重发。重启不重置计时，
已停止 thread 不复活，成功 mapping 后继续合法同线程后续工作。真实 Gmail 范围、
其他 repair 授权、无自动删除和 raw 仅内存的边界不变。

定期校对补齐 source 中的遗漏，恢复可确认的映射，报告 target 缺失和重复。用户手工删除 target 内容后，默认报告缺失；显式修复才重新插入。自动校对不清理重复，也不重新激活已经停止的 thread。

Source 已删除且尚未取得内容的邮件无法恢复，应显示 `source_missing`。数据库丢失会降低可靠去重能力；备份是部署的一部分，不能把 target 存在等同于全部本地状态可重建。

## Dashboard 和内容存储

第一期提供只读 Dashboard，展示同步状态、进度、完成数量、异常和诊断。HTTPS 与 Web 用户认证由前置 Nginx 负责，Facet 提供 HTTP。Gmail OAuth 仍负责服务访问邮箱的授权，不由 Nginx 代替。

Web 页面、API 和诊断只返回运行状态和汇总，不展示邮件标题、地址、正文、附件、邮件 IDs、规则值或原始错误。内部 metadata 不直接序列化到浏览器，DEBUG 不扩大公开输出范围。

数据库存必要的映射、IDs、规则、时间、hash、队列、checkpoint 和受控错误码，不存邮件完整内容、正文、snippet、HTML、附件或完整 headers。默认 raw 只在处理中驻留内存，不建立磁盘 spool；重启后重新读取 source。若 source 此时已删除，优先核对是否已经投影到 target，无法恢复时明确记录缺失。

## 验收边界

Facet 负责规则、同步、保真、恢复、审计和 Gmail 可见性。完成条件是 target Gmail 可以通过 API 和 UI 回读内容、日期、会话和附件，并且未完成工作有持久、可解释的状态。

AI connector 的索引、搜索、附件处理和回答准确性由各 AI 产品负责。兼容性和索引延迟不构成 Facet 的发布门槛或性能承诺。
