# Facet Gmail 产品契约

日期：2026-10-02

适用范围：单用户 Gmail projection，Phase 1。

Facet 将用户选定的主 Gmail 内容投影到另一个 Gmail，供 AI agents 授权读取。Source 是唯一事实来源，target 是用户可检查的披露视图。本文约定用户授权了什么、规则如何生效，以及服务遇到故障时提供什么保证。

## 数据访问和披露范围

AI agents 只连接 target。Facet 本身需要 source 读取权限；Gmail OAuth 不能将该权限限制为单独几个 sender。选择性由 Facet 规则和执行逻辑实现，物理隔离存在于 source 与 agent 所连接的 target 之间。

Target 应专用于投影。其既有邮件、草稿或直接收到的新邮件也可能被 AI connector 读取，Facet 只控制自己写入的内容。初始化提示未由本 projection 管理的内容，用户可以清理或明确接受；服务不自动删除或认领这些邮件。

一封 message 被允许后，整个 source thread 的全部可用邮件被投影，包括早于六个月的历史、用户自己的回复、其他参与者、附件和原始 headers。已跟踪 thread 的后续消息继续投影，即使 sender 不再匹配最初的 allow rule。

这是一项 thread 范围的持续披露授权。Facet 不独立验证发件人真实性，也不声明正文、附件或后续参与者可信。邮件中的指令仍是外部数据，AI 产品需要自行处理其内容风险。

首次 backfill 和手动 admission 提供范围预览。预览说明完整 thread 的披露语义；邮件仍可能在预览后新增，因此它不承诺冻结未来会话。

## 规则和学习

只支持规范化的精确 sender、域名及其子域匹配。公共后缀不可以作为 allow domain；不支持 `hsbc.` substring 或任意 shell glob。银行域名需经过确认后加入。

自动 admission 基于 Gmail source mailbox metadata 和配置的精确 sender/domain 规则。Gmail 负责 SMTP 认证与邮件分类，Facet 不重新验证 DKIM/SPF/DMARC，也不把认证 headers 作为 admission gate。Gmail 接收邮件不等于发件人真实或内容安全；规则匹配的正常非草稿邮件可以触发 thread 披露。格式歧义、账号不匹配和 provider 故障仍不放行。此边界由用户于 2026-10-05 明确确认，取代此前 source-path attestation 要求。

新增 sender 或 domain rule 默认只对未来事件生效。通过 action label 学习时，当前 thread 立即纳入；不会自动回扫相同域名的所有旧 thread。历史范围扩展必须显式启动 backfill。

移除 allow rule 停止该规则带来的新 admission，已经纳入的 thread 保持跟踪。需要停止既有 thread 时，执行明确的 stop 或 BlackList 操作。

## 默认只读和便利模式

默认 source 使用 `gmail.readonly`。Facet 读取用户手工添加的 action labels，但不创建、清除或添加 source labels。标签留在 Gmail 中不代表命令尚未执行；SQLite 记录执行状态。移除再添加可以产生新的命令。

便利模式显式申请 `gmail.modify`，自动创建和清理 action labels，并可开启可视化状态标签。该 scope 也允许 compose 和 send，Facet 实现中不提供这些操作；用户应理解 token 实际权限。[Google Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)

Target 使用 `gmail.insert` 和 `gmail.readonly`。默认投影到 All Mail，保留原 sender 和日期；Inbox 或专用投影标签按配置启用。Facet 不复制 source 的已读、星标、archive、Inbox 或 Sent 状态。

## BlackList 和未来撤回

BlackList 将当前选定的 external sender 加入精确 blacklist，并停止操作所针对的 thread。该 sender 的新 thread 不再自动 admission；同域其他 sender 不受影响。其他已经 tracked 的 thread 不因这次操作自动批量停止。

停止操作取消尚未开始的相关 jobs。已经发出、结果尚未返回的 Gmail insert 可能仍然完成，服务会记录它；不能承诺撤销在途请求。

已投影邮件保留在 target。Phase 1 没有 purge、retention 或删除权限。未来从 target 删除内容，也无法保证第三方 AI 产品删除其已有索引和缓存。

## 故障和一致性承诺

服务持久保存发现的工作，在正常权限、source 内容仍可读取、target 可写入的条件下持续恢复，直到成功或形成明确的异常状态。限流、断网、重启和 target 授权失效不导致 jobs 被丢弃。

Gmail 和 SQLite 无法共同提交事务。常规重启通过 source message ID 和本地映射去重；insert 成功后本地记录丢失时，通过 target 搜索及内容核验尽量恢复。Message-ID 缺失、重复或索引延迟可能导致重复或待人工处理，不承诺 exactly once。

定期校对补齐 source 中的遗漏，恢复可确认的映射，报告 target 缺失和重复。用户手工删除 target 内容后，默认报告缺失；显式修复才重新插入。自动校对不清理重复，也不重新激活已经停止的 thread。

Source 已删除且尚未取得内容的邮件无法恢复，应显示 `source_missing`。数据库丢失会降低可靠去重能力；备份是部署的一部分，不能把 target 存在等同于全部本地状态可重建。

## Dashboard 和内容存储

第一期提供只读 Dashboard，展示同步状态、进度、完成数量、异常和诊断。HTTPS 与 Web 用户认证由前置 Nginx 负责，Facet 提供 HTTP。Gmail OAuth 仍负责服务访问邮箱的授权，不由 Nginx 代替。

Web 页面、API 和诊断只返回运行状态和汇总，不展示邮件标题、地址、正文、附件、邮件 IDs、规则值或原始错误。内部 metadata 不直接序列化到浏览器，DEBUG 不扩大公开输出范围。

数据库存必要的映射、IDs、规则、时间、hash、队列、checkpoint 和受控错误码，不存邮件完整内容、正文、snippet、HTML、附件或完整 headers。默认 raw 只在处理中驻留内存，不建立磁盘 spool；重启后重新读取 source。若 source 此时已删除，优先核对是否已经投影到 target，无法恢复时明确记录缺失。

## 验收边界

Facet 负责规则、同步、保真、恢复、审计和 Gmail 可见性。完成条件是 target Gmail 可以通过 API 和 UI 回读内容、日期、会话和附件，并且未完成工作有持久、可解释的状态。

AI connector 的索引、搜索、附件处理和回答准确性由各 AI 产品负责。兼容性和索引延迟不构成 Facet 的发布门槛或性能承诺。
