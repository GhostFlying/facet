# Facet agent 执行和 review 工作流

日期：2026-10-02

适用：Phase 1，关联 [执行计划](phase-1-execution-plan.md)、
[Epic #1](https://github.com/GhostFlying/facet/issues/1) 和
[仓库指令](../AGENTS.md)。G0 已批准，正在推进执行基础；没有生产 daemon 或已发布镜像。
[完整维护 CLI](cli-spec.md) 是必需交付，按对应工作包逐步实现，不能以 help 骨架
代替最终维护能力；规格有独立技术 review，实际命令仍须逐包实施/验收，不能继承旧
候选的 review 以替代新实现证据。

## 职责、模型和并发

用户后续明确简化了职责：root 直接负责 plan、实现、测试、文档、原子提交和集成，
仅独立 review 使用 subagent。变更前在研 worker 按原流程完成后再适用新规则；
不再为新单元默认派多个工程 worker。Reviewer 独立审核 plan、代码和验收证据；
作者不能 self-approve 同一单元。此规则取代下面历史波次中的默认工程并行配置。

| 工作 | 默认模型/努力 | 切换依据 |
| --- | --- | --- |
| 复杂架构、状态机、AUTH/insert 归属/writer ADR | `gpt-6.1-sol` / xhigh | 影响披露、恢复或跨模块事务边界 |
| 工程实现、离线测试、CLI、UI、CI、文档和集成 | `gpt-6.1-sol` / high 或 xhigh | 已有通过 review 的 plan 与稳定输入，按复杂度选努力级别 |
| 安全、并发、恢复、迁移、HTTP 隐私和发布 review | 独立 `gpt-6.1-sol` / xhigh | 必须独立于同一变更设计/实现作者 |
| 普通聚焦变更 review、机械验证 | 独立 Sol high/xhigh；简单有界低风险任务可用 `gpt-6-luna` | 复杂度和风险上升时使用独立 Sol xhigh |

2026-10-02 用户最新指示将后续任务限定为 Sol high/xhigh 或 Luna，禁止新派工或
reactivate Astra。模型不会改变权限、独立 review 或 gate；历史合法 review 保留
实际模型、reviewer 与 SHA，不改写为 Sol。协调 agent 按复杂度和槽位选允许的模型。
当前有 4 个总槽：协调加 3 个执行槽。默认 2 个 worker + 1 个 reviewer；前期设计可
暂用 3 个 worker。只派依赖就绪且文件所有权清晰的工作，不用大量任务抢同一 shared
schema 或同一 review 槽。已有任务阻塞时释放执行槽，安排独立离线工作。

## 权限和决定来源

2026-10-02 用户授权了 Phase 1 的 agent 推进方式、多 worktree、按需子 agent、
依赖图并行、GitHub Issue/PR 和原子提交，并要求 Compose 和 Actions
image 发布。同日用户明确批准 G0/D0，绑定
`caba7c73895a303d329cf3eba1c89557530c38c5`；总计划 PR #2 已实际合入 main。
技术 review/CI 没有替代该用户决定。同日较晚的模型指示以本文件的最新 routing 为准；
早期已获授权的实际审查证据保留。当前推进 reviewed 工作包，详细状态在执行计划
D0-D8 与 [进度台账](phase-1-progress.md)；未来重要边界改变仍须用户决定。

同日用户明确授权：满足独立 plan review、implementation review 和 CI 门槛后，自主
合并用户批准的 Phase 1 内工程/工作包计划 PR；总计划 PR 不属于这项自主合并权限。
采用 public `ghcr.io/ghostflying/facet`，phase 启动后 main 合并触发 Actions
自动发布 full commit-SHA image，PR 只构建。正式版本 tag、GitHub Release、真实
Gmail 操作和未指定主机部署不包含在这两项授权中。

| 操作 | 当前边界 |
| --- | --- |
| Plan、read-only 检查、review、文档修改 | 本轮已授权 |
| Phase worktree、Issue、focused PR、原子提交 | 已授权；提交/推送/集成由工程 agent 执行，仍经过 review/CI |
| 整体 Phase 1 计划 approval/start | G0/D0 已于 2026-10-02 明确批准精确 `caba7c7`，总计划 PR #2 已 merged；不扩大其他权限 |
| 产品实现、synthetic tests、依赖锁定与 CI 修复 | G0 通过后按 reviewed 工作包 plan 自主推进 |
| Phase 内工程/工作包计划 PR 合并 | D1 已授权，G0 后生效；独立 plan/implementation review + CI，通过实际 GitHub rules 后由集成 agent 执行 |
| Actions image 发布 | D2 scope 已授权，G0/phase 启动后实施；仅 public `ghcr.io/ghostflying/facet` main full-SHA；PR 不 publish，正式版本 tag 另确认 |
| Live Gmail、真实 bulk、便利 scope、repair | 仅明确授权的账号/thread/rules/test scope；D3 |
| 部署、dogfood host、真实 upgrade/rollback | 指定目标和范围获授权后；D4 |
| License、版本 tag、正式 release | D5 单独决定 |
| 新 chat、recurring automation、其他人联系 | 需另有明确授权，不因推进任务自动创建 |

允许范围内的普通编辑、诊断、review 和测试持续推进，不每步向用户请求确认。需要
权限/产品选择时，先把方案做到可 review，再提交具体 decision packet。授权等待只
阻塞有关分支；没有回复不视为同意。私密授权信息在受控本地状态中保留，不写公开 Issue。
G0 已通过；依赖就绪的 phase 内普通复杂包由独立 agent review，不重复要求用户逐包
批准。未冻结接口与其他外部 gate 仍按依赖等待。重要产品/隐私/权限改变
需重新提交用户 review，不能用 routine ADR 消化。

## 工作包生命周期

工作包 ID 固定，例如 `M2-04`。一个包可以拆多个聚焦 PR，但 Issue 保留统一交付和
gate 关联。状态分别记录工作进度与验证范围，避免“PR merged”误被解释为全部 live
验收通过。

```text
planned → plan_drafting → plan_review → ready → implementing
                                                |
                                                v
                         changes_requested ← implementation_review
                                                |
                                                v
                          evidence_review → ready_to_integrate → integrated

任一阶段可标 blocked(reason, dependency, owner, next action)
验证范围独立记录：implemented / offline_verified / gmail_verified / deployment_verified
```

包的本地实施完成和外部 acceptance 分开；例如 recovery 离线测试完成后，可以派
admission 的逻辑实施，G2 的 Gmail API/UI gate 尚待 live 权限时仍不得关闭 G2。
G1-G6 的最终验收保持顺序，后阶段设计/合成测试按实际输入并行。遇到失败 gate，
保留失败证据、修复和重测，不删测试、弱化契约或把 blocker 写成成功。

每次派工需指定：ID、目标、implementation dependencies、integration gate、
base SHA、文件 scope、接口版本、worktree/branch、owner/reviewer、模型、验收、
外部 authority 和 stop gate。文件 scope 有交叉时先确定一个 owner，其他任务以
接口/fixture 为输入，不能靠并行覆写相同文件解决。

## 复杂任务：Plan → Review → Implementation → Review

1. 作者在 `docs/implementation-plans/<package-id>-<topic>.md` 写 plan，包含具体
   文件、状态/事务边界、测试、风险、外部动作和 stop gate。共享或高风险选择先写
   `docs/implementation-plans/adrs/` ADR；原 raw、私密实样和账号不进入文档。
2. 协调 agent 指派独立 plan reviewer。Reviewer 对比产品契约、依赖和反例，给出
   `approved`、`changes_requested` 或 `blocked`，注明审查的 plan revision/base SHA。
   Plan 过审前可以继续 read-only 诊断或独立测试设计，不能按未审方案写该产品实现。
3. 工程 agent 在自己的 worktree 实施，完成必要 tests/docs/status。改换状态机、
   authority 或共享接口时先更新 plan 并重审，不能实施后用文档追认重大变化。
4. Worker 提交候选 SHA 和证据，由独立 reviewer 做代码与验收 review。高风险包
   Reviewer 必须不是该包 ADR 的作者；协调 agent可核验 gate，但不替代独立 review。
5. 修正后产生新候选 SHA。Review 的 findings 与证据应说明哪些保留、哪些已失效；
   影响代码或契约的改动必须重新 review，不能仅依据前一个 commit 的结论。
6. 在 G0 已通过的 phase 内，当前 PR 的 CI、review、隐私和针对性验收通过后标
   `ready_to_integrate`。只实现离线逻辑的 PR 可以保留不属于该 PR 的 milestone live
   gate 为 pending，不必等待它才整合工程输出；真正执行 Gmail/部署或声称 gate
   完成的 PR 必须有相应 authority/实测证据。总计划 PR 另须用户明确批准，不能自主
   merge。Merge 由集成 agent 执行，遵守 D1 与实际 GitHub rules。合并后基于实际
   main 做必要集成检查，更新 Epic/development-status 和下一就绪任务。

GitHub 上由同一用户账号运行的 agent review 是工程审查证据，不自动等于 required
approval。不能冒用他人账号、伪造 reviewer、加 agent co-author 或绕过 branch
protection。遇到 GitHub 需要独立账号审批，向用户报告确切 rule 和 PR；不主动联系人。

## Worktree 和 GitHub 执行

Shared current-state/coordination 文档只有一个集成/docs owner，详见
[进度台账](phase-1-progress.md)。其他 worker 通过 Issue/handoff 提交证据和修改建议，
不在各自 worktree 并行重写 status/全局计划；局部 package plan/ADR 由该包 owner 维护。

工作目录建议为 repository 同级的 `../facet-worktrees/<package-id>-<topic>`，
分支为 `feat/<id>-<topic>`、`fix/<id>-<topic>` 或 `docs/<id>-<topic>`。当前 planning
worktree 为 `phase1-plan`，分支 `docs/phase1-execution-plan`。不把 worktree 建在
tracked tree 内，不复制 ignored 凭据或 spike 状态。

新任务先核对 current `origin/main`、branch/status、remote 与 applicable AGENTS。
记录 base SHA，在指定 worktree 工作；已有 dirty 改动属于其 owner，不能覆盖。
依赖未合并时推荐独立设计/测试后等待 main；必要的 stacked PR 要在 Issue 声明 base
和父 PR，并在父项合并后 rebase/review。尽量通过小 PR 减少 stack 和冲突。

GitHub 采用一个 Epic、每就绪工作包一个 Issue、一项聚焦变更一个 PR。Issue 包含
依赖 ID、plan、scope、acceptance 和 external gate；PR 链接 Issue，说明最终行为、
验证与限制。Review findings、CI run 和 reviewed SHA 可公开，私密 Gmail evidence
只记录脱敏汇总和本地证据是否存在。不给其他用户自动 assign/mention，不发无授权评论。

原子提交是一个可解释、可验证、可单独 review 的行为变化；不可用一次巨型 milestone
提交掩盖不同状态机和权限选择。Tests/docs 跟随对应行为。提交前只 stage 明确 scope，
review `git diff --cached`，执行 `git diff --cached --check` 和
`bash scripts/check-repo-safety.sh`。提交、push 前都检查 safety；忽略文件不等于扫描证明。

Commit subject 使用 `type: action summary` 的英文原子主题：feature 为
`feat: impl ...`，fix 为 `fix: fix ...`；`docs/test/refactor/ci/chore` 使用清楚的
动作动词，例如 `docs: add maintenance CLI contract`、`ci: verify image provenance`。
不使用含糊的 change/update-only subject，不加 agent co-author。用户授权的一次性
main 历史规范化单独按
[受 review 的实施计划](implementation-plans/commit-history-normalization.md)
执行；由单一 Git writer 操作，保留内容树/用户 identity/日期与可恢复引用，不能把它
扩成其他 rewrite 许可。新 CLI 需求必须获得自己的 review，不继承重 parent 前的旧结论。

Git 使用现有正确用户 identity，必要时只在 commit 命令临时使用用户已授权的
`4019569+GhostFlying@users.noreply.github.com`，保持 configured name，不写 saved
`user.name`/`user.email`。检查 author 与 committer，避免私密 email 历史进入 public
branch。不得 agent/bot/tool identity 或 agent co-author。

冲突由集成 agent 分析，更新 plan/接口 ownership；不要让协调 agent直接修产品代码。
Merge 产生的实质行为变化要重新独立 review 与验证。PR merge 后若 Issue 存在尚待
live gate，保留 gate 子项/独立 Issue，不用自动 closes 隐藏未完成验收。

## Evidence、报告和恢复

所有 evidence 有范围与身份：工作包、候选 SHA、test command/结果、offline/live
类型、操作范围、时间、reviewer。公开结果可以写计数与受控类别；真实邮箱地址、
Gmail/RFC IDs、sender/subject/body/raw、附件名、token、provider response、私密路径
不进入 Git/Issue/PR/CI/image/截图。Browser evidence 用合成数据。

本地 baseline 使用锁定环境：`uv sync --locked --extra dev`、Ruff lint/format、pytest、
spike help 和 repository safety；生产包新增后加入 `facet --help`。对变更进行必要
targeted checks，再完成对应 gate 要求。Docs-only 变更用 links/whitespace/privacy/
consistency review，不为不可测 prose 添加镜像实现的假测试。

CLI gate 按 `CLI-01` 至 `CLI-08` 与 package/gate 关联：subprocess/fake Gmail 测试
实际调用命令，覆盖 preview producer、稳定 client request key、首应答丢失、单 writer/
credential ownership、offline 故障维护、JSON/退出码、非 TTY guards 与 private/public
sentinels。M6 用最终 image/非 root volume 执行完整容器 CLI，不要求 host Python。
Live/OAuth/re-auth 和真实 repair 仍受各自授权，不能用假数据宣布实际运维验收通过。

每个 coherent unit 更新 `docs/development-status.md`。短期关键状态可在工作包
Issue 中更新，repo handoff 汇总到实际合并单元；不同 worker 的 status 改动由 owner
集成。不得把计划、实现、离线测试、Gmail 实测或真实部署混在“完成”一栏。

协调 agent 在持续工作中约每 60 秒内给有内容的进展说明；以新证据、下一依赖、风险
或 blocker 为主，不重复没有变化的轮询。对用户只报告总体进度、可 review 结果和需要
决定的事项，工程细节持久保留在文档/Issue/PR。不能承诺在没有产品唤醒机制时跨 turn
自动工作，72h monitor 的建立遵守 D8。

若发生 context handoff、worker 退出或进程中断，后续 agent 先读 status、package
plan、Issue/PR、worktree dirty state 和 evidence。核验 base/current SHA、自己的
ownership 与外部 authority 后续做；不能假定 previous review/live authorization
适用于新 scope，也不能沿用 spike 的生产身份/状态。

## 可直接使用的记录模板

### 工作包/派工记录

```text
ID / title:
Goal and product contract references:
Implementation dependencies / stable interfaces:
Integration gate and verification still pending:
Owner / model / reviewer:
Worktree / branch / base SHA:
File scope / plan / ADR:
Outputs and acceptance tests:
External actions and authorization source:
Stop gates:
State / next action:
```

### Plan 和实施 review

```text
Package / plan version / base SHA / reviewed candidate SHA:
Reviewer and independence from design/implementation authors:
Contract, state/transaction, privacy, recovery and authority checks:
Findings: severity / evidence / required correction / owner
Verification examined and what remains unverified:
Result: approved / changes_requested / blocked
Affected conclusions to re-review after changes:
```

### 完成/handoff

```text
Package / PR / candidate or merged SHA / base:
Implemented behavior and file scope:
Actual offline commands and results:
Live/API/UI/deployment evidence scope, or pending external gate:
Review result / reviewer / reviewed SHA:
Known limits and selected-work states:
Worktree ownership / outstanding changes:
Next dependency-ready package:
```

### Blocker/用户决策包

```text
Decision ID and concrete affected package/gate:
Observed evidence and current safe state:
Why existing authority/contract is insufficient:
Recommended option and alternatives with disclosure/cost/recovery impact:
Exact action, target and scope if approved:
Reviewable plan/PR/artifact and verification already completed:
Independent work continuing while pending:
Decision received / date / scope / expiry if any:
```

### 协调 agent 汇报

```text
Completed with evidence:
In progress and next dependency:
Gate status and verified scope:
Blocker or requested user decision, if any:
Links to plan / Issue / PR / report:
```
