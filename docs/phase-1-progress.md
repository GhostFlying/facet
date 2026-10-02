# Phase 1 执行进度台账

日期：2026-10-02

本候选交付快照；最新 SHA/review/CI/集成结果记录在各 Issue/PR。此台账不把 plan、
PR merge、offline、Gmail 或 deployment 证据混为完成。Package 状态沿用
[agent workflow](agent-workflow.md)，工程 readiness 和最终 milestone gate 分开。

## 已批准基线和边界

用户于 2026-10-02 明确批准 G0，绑定整体计划
`caba7c73895a303d329cf3eba1c89557530c38c5`。[PR #2](https://github.com/GhostFlying/facet/pull/2)
实际 MERGED 在同一 SHA，normal fast-forward 保留原子用户/noreply commits；
[candidate CI](https://github.com/GhostFlying/facet/actions/runs/36968387054) 与
[main CI](https://github.com/GhostFlying/facet/actions/runs/36969107636) 成功。
G1-G6 均未通过；package/config/CLI foundation 和 P1-02 已集成，SQL 仍是部分切片，
本候选交付 M1-05 pure/logging early unit。真实 DB/auth/runtime consumers、
Gmail/Compose/Dashboard 和完整维护 CLI 均未完成。

D1 phase 内合格工程 PR 集成与 D2 限定 GHCR/main-SHA scope 已随 phase 启动生效，
仍按各包 dependencies/review/CI/gates 执行，不提前实现 image workflow。D3 live
账号/规则/操作、D4 host、额外 scopes、license、正式 tag/release 和 automation
决定没有因此获批。完整权限以 [D0-D8 台账](phase-1-execution-plan.md) 为准。

## Ownership、派工与证据

Root 只调度/review 核证/汇报；shared current-state/coordination 文档由 P1-00 的
delegated `phase1_plan_author` integration/docs owner 单独维护，直到 root 显式转交。
当前 SQL owner 的 worktree/branch 为 sibling `m1-02-persistence` /
`feat/m1-02-persistence`；本次独占 M1-05 分支的两份 shared docs 作 coherent handoff。
M1-01/P1-00 已集成，旧 worktrees 保留。其他 workers
维护自己的 plan/ADR/source，通过 Issue/handoff 提交共享文档建议，不并行覆写
AGENTS/README/status/workflow/全局计划/本台账。GitHub 不自动 assign/mention 外人。

P1-00 r2 [plan](implementation-plans/p1-00-execution-baseline.md) 独立 approved，
SHA-256 `b77d4f90d44ea61aad286851454e9db7d98cef0e1c703ad5968470e4d7242bae`；
implementation/acceptance review、CI 均实际通过，PR #6 集成 exact `2618eaf`。
P1-01 修订 ADR 候选独立 approved，PR #8 集成 exact `09031e7`，candidate/main CI 成功；
core-v1/writer-v1 设计已 freeze，未实现相应 runtime。M1-01 PR #11 实际集成 exact
`b1e4ae0`，287 offline tests、独立 whole/closure review、3.12/3.13 candidate/main CI
通过。P1-02 provider-slice PR #10 exact `c18bfbe` 后，mandatory CT PR #12 实际集成
exact `1b7cd58`，92 CT/379 full tests、独立 review、candidate/main CI 通过；Issue5
关闭，仅满足测试基础工程包及 M1-02 的该项依赖，不证明后续 feature consumers。
M1-02 r3 design 独立 approved 后已派实际 SQL；PR #15 values/schema exact `56eaac6`
独审/450 full/CI 通过，new repo slice `bf0bf0b` 504 local tests passed、review/CI 待验，
整包 DB-01..28 未完成。M1-03 wire extension 设计局部 changes requested、无 source；
M1-04 credential design approved、实际 owner/schema 仍 pending。M1-05 early library
source `c455f71` 独立 accepted，488 full/33 logging subprocess/wheel/3.12+3.13 CI
通过；本候选两份 docs 的 exact-head review/CI、实际 integration receipt 在 PR #16。
Issue14 保持 open，真实 DB/auth/runtime/HTTP/DOM/Compose 消费验收未完成。
未为后续全部工作包建 Issue。

每次 dispatch 仍需 canonical deps、exact base/interface version、owned files、
owner/model、独立 reviewer、plan/revision、acceptance 和 external gates。
`ready` 表示本包 plan gate 已通过，不自动表示工程输入齐备；只有 readiness 栏
和实际 dispatch 同时满足才能实施。Accepted 不等于 integrated，integrated 不等于
milestone/live verified。按现有 workflow 记录 blocker 原因/下游/解除条件和继续任务。

## 36 包与就绪波次

[Epic #1](https://github.com/GhostFlying/facet/issues/1) 是父跟踪项。下表只保存稳定 IDs
与状态/原波次，依赖、outputs、owned paths、验收和 gate 来自 canonical cards，
不在此重写 DAG。包拆 PR 时 Issue 保持统一交付；仅 readiness 到达时物化 Issue。

| Package | Wave | State | Engineering readiness / next gate | Owner / independent reviewer | Tracking |
| --- | --- | --- | --- | --- | --- |
| [P1-00](phase-1-execution-plan.md) | W0a | integrated | PR #6 exact2618；review/candidate+main CI passed，非 G1 | 集成/docs S / 独立 A | [#3](https://github.com/GhostFlying/facet/issues/3) |
| [P1-01](phase-1-execution-plan.md) | W0a | integrated | PR #8 exact09031；core/writer freeze+review/CI passed，非 runtime | 架构设计 A / 独立 A | [#4](https://github.com/GhostFlying/facet/issues/4) |
| [P1-02](phase-1-execution-plan.md) | W0b | integrated | PR #12 exact1b7 mandatory CT/379 full/review/candidate+main CI passed；后续 feature consumers 另验 | 测试 worker / 独立 reviewer | [#5](https://github.com/GhostFlying/facet/issues/5) closed |
| [M1-01](phase-1-execution-plan.md) | W0b | integrated | PR #11 exactb1e revised whole/closure review、287 full/candidate+main CI passed；仅 foundation，非完整 CLI/G1 | package/config S / 独立 reviewer | [#7](https://github.com/GhostFlying/facet/issues/7) closed |
| [M1-02](phase-1-execution-plan.md) | W1a | implementing | r3 design approved；PR15 values/schema exact56eaac 独审+450full+CI pass，repo bf0bf0b 504 local pass 待审；History/insert/backup/crash/whole DB01–28 pending | SQL/shared docs S / 非作者独立 A | [#9](https://github.com/GhostFlying/facet/issues/9), [PR15](https://github.com/GhostFlying/facet/pull/15) |
| [M1-03](phase-1-execution-plan.md) | W1b | plan_review | plan approved；wire/storage extension 局部 changes requested、无 source，等实际 storage input | writer design A / 非作者独立 A | [#13](https://github.com/GhostFlying/facet/issues/13) |
| [M1-04](phase-1-execution-plan.md) | W1b | ready_for_implementation | credential design approved；actual writer/schema input 未齐、未派 source，无 live OAuth | credential design A / 非作者独立 A | 未物化 |
| [M1-05](phase-1-execution-plan.md) | W1c | implementation_review | pure/logging early source c455 独审/488full/33 loggingproc/wheel/CI pass；本交付 docs/head gate 待验，未 merge；真实 consumers/完整包 pending | models/logging A + shared docs S / 非作者独立 reviewer | [#14](https://github.com/GhostFlying/facet/issues/14), [PR16](https://github.com/GhostFlying/facet/pull/16) |
| [M1-06](phase-1-execution-plan.md) | W1c | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M2-01](phase-1-execution-plan.md) | W2a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M2-02](phase-1-execution-plan.md) | W2b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M2-03](phase-1-execution-plan.md) | W2b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M2-04](phase-1-execution-plan.md) | W2b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M2-05](phase-1-execution-plan.md) | W2b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M3-01](phase-1-execution-plan.md) | W3a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M3-02](phase-1-execution-plan.md) | W3a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M3-03](phase-1-execution-plan.md) | W3b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M3-04](phase-1-execution-plan.md) | W3b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M4-01](phase-1-execution-plan.md) | W3b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M4-02](phase-1-execution-plan.md) | W4a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M4-03](phase-1-execution-plan.md) | W4b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M4-04](phase-1-execution-plan.md) | W4a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M4-05](phase-1-execution-plan.md) | W4b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M4-06](phase-1-execution-plan.md) | W4b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M5-01](phase-1-execution-plan.md) | W5a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M5-02](phase-1-execution-plan.md) | W5b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M5-03](phase-1-execution-plan.md) | W5c | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-01](phase-1-execution-plan.md) | W5a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-02](phase-1-execution-plan.md) | W6a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-03](phase-1-execution-plan.md) | W5b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-04](phase-1-execution-plan.md) | W5c | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-05](phase-1-execution-plan.md) | W6a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-06](phase-1-execution-plan.md) | W6a | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-07](phase-1-execution-plan.md) | W6b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-08](phase-1-execution-plan.md) | W6b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |
| [M6-09](phase-1-execution-plan.md) | W6b | planned | 按 canonical deps 等 frozen 工程输入；未派实施 | 未派工 / reviewer 待派 | 未物化 |

## Durable handoff

重用 [workflow 的 dispatch、review、handoff 和 decision packet](agent-workflow.md)
模板：记录 reviewed plan hash/revision、base/head SHA、checks/result/evidence scope、
已知 limits、pending external gates、当前 worktree ownership 和下一 observable
交付。验收证据放 Issue/PR，避免为自引用 SHA 反复补 metadata commit。Root 核证后才
调度正常集成，并由文档 owner 在下次 coherent handoff 同步台账快照。公开 tracking
只能包含合成/受控汇总，不能上传私密 mailbox IDs、raw、credentials 或 host paths。
