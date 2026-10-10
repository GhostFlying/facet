# Facet 同步状态 Dashboard 规格

日期：2026-10-02

状态：Phase 1 必需功能，随 M4 alpha 交付，M6 完成部署验收。

Dashboard 展示同步是否正常、历史复制进度、成功数量、异常和可操作的诊断信息。页面和 HTTP API 只提供运行状态与汇总统计，不提供任何邮件细节。HTTPS、用户认证和外部访问控制由前置 Nginx 负责，Facet 仅提供 HTTP 服务。

本规格是 [项目计划](project-plan.md) 与 [产品契约](product-contract.md) 的补充。生产 runtime 已提供六类只读汇总快照（状态、进度、异常、当前规则、规则匹配活动、诊断）与静态页面；页面消费现有字段，未实现的采集指标须明确显示未知或未提供，不得据此宣称最终 M4/M6 验收完成。

## 页面内容

第一期提供一个自适应的只读页面，按以下区域组织：

| 区域 | 展示内容 |
| --- | --- |
| 同步概览 | 初始化、backfill、增量或恢复阶段；正常、积压、降级、需重新授权等状态；最后成功 poll 与插入时间 |
| 数量和队列 | 已验证投影消息数、tracked thread 数、已发现待处理消息数、进行中、重试中、待人工处理、缺失与取消数量 |
| 历史进度 | Discovery 是否完成、已扫描数量、已发现和已完成的 backfill threads、已知消息总量、处理速率 |
| 增量同步 | 最近成功 poll 距今多久、最老 job 年龄、最近一小时和一天的成功数量、可用的端到端延迟统计 |
| 校对状态 | 最近 source reconcile、target audit 的时间、状态、补齐与异常汇总 |
| 异常汇总 | 按错误类别和 source/target 角色分组的数量、首次与最近发生时间、是否自动恢复、下一次重试时间、固定处理建议 |
| 规则匹配活动 | 按服务器本地时间倒序展示最近新增投影消息批次对应的 sender/domain 规则和数量；每条记录保持单行，时间展示到秒；不展示邮件细节或 ID |
| 诊断 | OAuth 健康状态和权限模式、DB 可读写与迁移状态、运行版本和当前 commit SHA、调度 heartbeat、磁盘与内存压力、诊断快照时间 |

仅用 Source 和 Target 标识账号角色，不显示完整或遮掩后的绑定账号地址。按 2026-10-09 用户明确要求，规则区域可显示当前 sender/domain 值和 action-label 文本；这些是私密部署配置，不进入其他公共 DTO、日志或导出。邮件标题、正文、附件、邮件 IDs 和原始错误仍禁止。

页面默认每十秒刷新，允许手动重新获取状态。浏览器刷新只读快照，不触发 Gmail 请求、reconcile、重试、规则变更或暂停操作。OAuth setup、规则编辑、手动 admission 和服务控制在第一期仍由 CLI 完成。

运营时间由同步服务器按其本地时区格式化；数据库和内部排序仍使用 UTC 瞬时值，浏览器本地时区不参与显示转换。

## 数量和进度定义

成功消息数来自本 projection 已持久确认的唯一 source message 映射，正常重放、重试或重复的 History 事件不重复计数。总成功数不等同于 target 邮箱当前的全部消息数量，未映射的既有邮件不算成功投影。按产品契约允许的外部 agent source 身份 SENT/DRAFT 也不计投影成功，不能仅因未映射而显示为异常；分类信息只允许必要聚合，不暴露 From、To/Cc 或其他邮件细节。本条不新增 Dashboard 字段或声称运行时分类已实现。

历史进度以当前 backfill epoch 为范围。Discovery 未结束时总量未知，只显示已扫描、已发现和已完成的数量，不能从 Gmail `resultSizeEstimate` 生成确定的百分比或剩余时间。

Discovery 完成后的 `known_message_total` 是搜索候选消息数，不是完整 thread 历史展开后的最终复制总量，也不包含后续增量。页面不以它为成功数的分母，不显示百分比或 ETA；缺失、取消、失败和待处理分别列出。计数必须明确是 thread 还是 message。当前 epoch 的已发现/完成 thread 数不能冒充全局 tracked thread 数。所有 work 已处理但存在终止异常时显示“已处理完成，存在异常”，不能显示为全部成功。

增量同步持续运行。“已追平”表示最近一轮 History 已完整消费、可执行队列没有积压；页面同时列出被阻塞或待人工处理的 work。它不意味着同步服务永久完成，也不保证下一秒没有新邮件。

各 job 状态汇总采用互斥分类，同一个 job 不同时算作 pending、retry 和 failed。新消息导致已知总量增加时更新说明，避免把进度变化误报为回退。

日期仅展示运行事件的时间，不展示任何单封邮件的原始 Date；运营时间由服务器按本地时区格式化，内部仍以 UTC 瞬时值排序。活动流不插入“每轮同步”分隔线，因为当前快照不持久化精确轮次边界；时间仅用于近似判断先后。角色 `auth_state` 为持久化账号绑定状态；`last_verified_at` 标为绑定验证时间，不是最近 profile 请求、凭据刷新时间或 token 健康保证。聚合延迟没有样本时返回不可用与样本数，不能用零代替未知。当前未采集的全局 tracked thread、reconcile/audit、速率/延迟及资源压力不得伪造；六类快照任一过期、不可用或刷新失败时，页面清除健康、零积压和零异常的当前结论。同步周期进行中时，页面用 `cycle_in_progress` 显示中性的 Running/Backfill，不把尚未完成本轮检查误报为 Healthy；周期成功完成后才显示 Healthy，降级、阻塞和过期状态优先保留。刷新有界、不重叠，失败后恢复正常快照才恢复显示。

## HTTP 接口

建议 FastAPI 提供 API 和打包静态页面，与 scheduler 在同一进程运行，ASGI server 使用一个进程，避免启动多个 sync daemon。接口通过状态聚合层读取 DB 和缓存诊断快照，不访问 Gmail，也不读取 raw payload。

| 方法和路径 | 返回内容 |
| --- | --- |
| `GET /` | Dashboard 页面 |
| `GET /api/v1/status` | 同步阶段、健康状态、角色状态和 operational timestamps |
| `GET /api/v1/progress` | 当前 epoch、message 与 thread 汇总、队列和速率 |
| `GET /api/v1/issues` | 按错误类别分组的汇总与固定处理建议 |
| `GET /api/v1/rules` | 当前 sender/domain 规则和 action-label 文本、启用状态；仅限私有部署 Dashboard |
| `GET /api/v1/activity` | 最近首次验证投影批次的 sender/domain 规则、Other authorized thread 归类、数量和服务器本地时间；仅限私有部署 Dashboard |
| `GET /api/v1/diagnostics` | 已脱敏的组件检查、版本与资源状态 |
| `GET /healthz` | Web 进程存活状态 |
| `GET /readyz` | Dashboard 状态数据是否可读 |

各响应携带采样时间、快照新鲜程度和必要的统计范围。组件无法获取时明确标记 unknown、stale 或 unavailable；不能继续显示上次的绿色状态却不标记过期。Gmail 暂时失败不使存活检查失败，避免容器重启掩盖业务故障。

第一期不提供 HTTP 写接口、逐邮件或逐 thread 查询、日志下载、DB 下载、配置导出、附件路由或 raw 调试路由。所有静态资源随应用提供，不依赖外部 CDN。

## 隐私和诊断边界

页面、API、DOM、前端状态、URL 和诊断导出均不得包含以下内容：

- 邮件标题、正文、snippet、HTML、raw MIME 和完整 headers。
- 发件人、收件人、Cc、邮箱地址；规则快照是唯一例外，仅显示当前配置的 sender/domain 值和 action-label 文本。
- 附件名称、内容、Content-ID、邮件链接。
- Gmail message/thread/history IDs、RFC Message-ID 和用于内容恢复的 fingerprint。
- OAuth client secret、access/refresh token、授权链接和授权响应。
- 原始 Gmail 错误响应、任意异常字符串、堆栈、SQL、主机名、完整本地路径或代理凭据。

这是 API 的输出契约，不能依赖前端隐藏字段。聚合层显式构造独立 DTO，所有 endpoint 使用严格白名单 schema；不将数据库 row、内部 event payload 或 exception 对象直接序列化。FastAPI 的 response model 可约束返回字段，但不能代替对字段来源和字符串内容的校验。[FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/)

异常以受控 error code 和固定文案显示，例如 `source_auth_required`、`target_rate_limited`、`insert_result_unknown`、`source_missing`、`target_missing`、`duplicate_candidates`、`database_unavailable`。可提供“在部署主机重新授权 Target”“等待自动重试”“运行受限的 CLI 诊断”等建议，不插入 Gmail 返回的 message 或 URL。

Dashboard 诊断与 CLI doctor 共享检查逻辑，但使用单独的公开输出模型；CLI 的本地账号绑定、路径和对象 IDs 不进入 Web 响应。Debug 开关不能绕过 Web 白名单。

## 数据持久化

SQLite 保存同步所需的 IDs、source 到 target 映射、RFC Message-ID、时间、hash、规则、checkpoint、job 状态、重试计划、标准化 error code 和汇总运行指标。

不保存邮件完整内容，也不保存正文、HTML、snippet、附件 bytes、完整 header dump、每封邮件的 Subject 或 From/To/Cc 副本。Rules 中的明确 sender/domain 和账号 binding 是必要的私密配置，保存在内部 DB 或配置中；当前规则快照按明确批准的私有 Dashboard 例外只读展示 sender/domain 值和 action-label 文本，不进入其他公共 DTO、日志或导出。

`source_events` 和 jobs 的 payload 仅包含必要的类型、IDs、label ID 与调度信息；`last_error` 使用受控字段，不能成为任意 provider response 的存储容器。审计记录保存操作和状态变化，不复制邮件字段。规则匹配活动由已有 mapping verified 时间、thread admission 和规则元数据聚合，不新增邮件内容或公开 ID。

默认 raw 只在 source 读取、target 插入和保真回读期间驻留内存，不存 SQLite、不建立磁盘 spool，也不写日志。重启后重新读取 source；已经插入但结果未知时先恢复 target 映射。Source 已删除且 target 也无法恢复的情况明确记录 `source_missing`。

## Nginx 和部署

Facet 提供内部 HTTP listener，建议端口 8080，不内置 HTTPS、用户登录、session、Basic Auth 或 JWT。Gmail OAuth 是服务访问 source/target 的授权，仍由 CLI 完成，与 Dashboard 用户认证不同。

Nginx 负责外部 HTTPS 和用户认证，代理页面、静态资源及 `/api/` 请求到 Facet。部署文档说明这个边界，提供 proxy 示例，不要求 Facet 读取或验证 Nginx 的登录身份。[Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)

若 Nginx 在宿主机运行，Compose 默认发布到 `127.0.0.1:8080`；若 Nginx 在同一 Docker 网络中，使用 `facet:8080`，无需宿主机端口。容器内 listener 可绑定 `0.0.0.0`，默认不直接暴露到公网。HTTP 刷新读缓存快照，不为每个浏览器访问重复消耗 Gmail quota。

## 实施和验收

M1 定义状态聚合和白名单 schema。M2 与 M3 提供真实计数和 backfill epoch 状态，M4 同步交付 Dashboard 与 alpha，M6 完成 Nginx、Compose 和浏览器验收。

计划文件范围为 `src/facet/status/`、`src/facet/web/`、打包的 HTML/CSS/JS 和相关测试。第一期使用轻量静态前端，不建立独立 Node 常驻服务或大型前端平台。

验收必须覆盖：

1. Discovery 总量未知、正常 backfill、追平、积压、断网、重新授权、History 恢复及部分失败等状态真实显示。
2. 重放和重试不重复计数，message 与 thread 单位明确，未知总量不显示伪造百分比。
3. GET 请求不改变队列或规则，不触发 Gmail I/O；多个页面刷新不阻塞 sync worker。
4. 对 DB、内部 event 和 exception 注入敏感测试值，检查所有 HTTP 响应、DOM、网络请求与导出中均无这些内容。
5. 正式 DB、journal、运行文件和日志不保存 raw MIME、正文和附件，重启恢复仅依赖持久 metadata 与邮箱内容。
6. 手机和桌面均可查看关键状态，刷新失败显示 stale，恢复后更新；资源状态未知时不伪报健康。
7. HTTP 经前置 Nginx 可访问，应用内不要求 HTTPS 或用户认证，Compose 不额外启动多个同步进程。
8. 规则匹配活动按时间倒序显示 sender/domain 规则和数量，时间显示到秒且每条记录单行；缺少规则归属的 action-label/manual admission 显示为明确的 Other authorized thread；不暗示时间间隔代表完整同步轮次；commit SHA 仅接受镜像构建时烘焙的完整 40-hex 值。
