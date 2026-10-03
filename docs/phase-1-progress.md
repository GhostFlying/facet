# Phase 1 执行进度台账

日期：2026-10-03（PRC；历史 UTC receipts 保留原日期）

本候选交付快照；最新 SHA/review/CI/集成结果记录在各 Issue/PR。此台账不把 plan、
PR merge、offline、Gmail 或 deployment 证据混为完成。Package 状态沿用
[agent workflow](agent-workflow.md)，工程 readiness 和最终 milestone gate 分开。

## 已批准基线和边界

用户于 2026-10-02 明确批准 G0，绑定整体计划
`caba7c73895a303d329cf3eba1c89557530c38c5`。[PR #2](https://github.com/GhostFlying/facet/pull/2)
实际 MERGED 在同一 SHA，normal fast-forward 保留原子用户/noreply commits；
[candidate CI](https://github.com/GhostFlying/facet/actions/runs/36968387054) 与
[main CI](https://github.com/GhostFlying/facet/actions/runs/36969107636) 成功。
G1-G6 均未通过；package/config/CLI foundation、P1-02 和 M1-05 pure/logging early
unit 已实际集成。有限 SQL/action、migration entry、no-state read foundation 和
supplied-connection Source A 已通过 PR28 集成，非整包/runtime/native issuer 验收。
M1-04 pure values/in-memory
codec/client parser 已由 PR18 实际集成 exact `ff77e63`，main CI 37001014793 成功；
full OAuth/binding 仍未完成。PR19 model policy 已实际集成 exact `a57dd771`，
main CI 37018290223 成功；PR20 bounded OS foundation 已独审并实际集成 exact
`ea80db2`，candidate CI 37025751696 与 main CI 37026826339 均 dual-Python 成功。
PR22 corrected Thread harness 已实际集成 exact `befe278`，candidate CI37036616826
与 main CI37037683010 dual-Python 成功；当时 befe main 为 758 full/40 CLI each。
PR21 exact36b 的 main CI37028856572 Python3.12 FAIL/3.13 PASS 与 a410 H1 HOLD
仍是历史失败，不由后续 green 覆盖。PR28 actual MERGED exact
`b5a32015837f03a6efd935700a2c56441e77087a`，current main 2332 full/40 CLI each；
PR15 actual MERGED/Draft metadata true，不等于完整 M1-02/Issue9 验收。
真实 DB/auth/runtime consumers、
Gmail/Compose/Dashboard 和完整维护 CLI 均未完成。

D1 phase 内合格工程 PR 集成与 D2 限定 GHCR/main-SHA scope 已随 phase 启动生效，
仍按各包 dependencies/review/CI/gates 执行，不提前实现 image workflow。D3 live
账号/规则/操作、D4 host、额外 scopes、license、正式 tag/release 和 automation
决定没有因此获批。完整权限以 [D0-D8 台账](phase-1-execution-plan.md) 为准。

## Current finite-main ownership、派工与证据

Root 只协调/核证/review 派发和汇报。`m103_os_source` 仍是唯一 shared current-state
docs/integration owner；本次仅 status/progress/append-only own plan，位于
`phase1-source-status-main-handoff` / `p/luchengxuan/phase1-source-status-main-handoff`，
base exact qualified main `b5a32015837f03a6efd935700a2c56441e77087a`。本新 docs
unit 的独立 affected-source review、新 CI、publication/integration root release
尚未完成；不借 PR28 acceptance/CI 替代自己的新候选 gate。本次 author fresh2332
full/448.19s、separate40CLI/4.73s、installed522/11.30s、eight installedWAL/0.66s、
nine literal helpers、freshwheel69 byte/54 inert-import/privacy/locked lint gates
已通过；all187 unallocated files/36 ID|Wave|State baseline 仍 exact，非独立 source
acceptance，未授权 publication/main action。

PR28 于2026-10-03T01:09:03Z actual MERGED exactb5a3201，tree
`889d94f61e5cf6cb0e410fdfa327afc5643eeb83`；ordinary main FF/push 保留审定来源，
没有新增 platform merge/squash/history rewrite。集成 a9c SQL/action、4506 read
foundation、dd1 corrected migration、d688 combined input、b216 corrected Source A。
`phase1_sol_policy_review` 是 ACTION corrections/read-foundation source author；
earlier SQL slices 的实际历史作者归属保留；
`m103_os_source` 是 OS/harness/migration/Source A/integration source author。
各历史非作者 review 保留实际身份/SHA，root 不代替作者或 nonauthor acceptance。

M 的419L independent SOURCE APPROVE 由 `bootstrap_storage_independent_qa` 给出，
report SHA-256
`e60f7decea4ff016927554af43f2c065f95569801f9b91b00abedf061a56d99e`。
实际2332 full/447.70s、522 source/installed focus，native/DDL/K1/CAS/retained
73 R3/150 OS/71 read/114 MG/40 CLI、wheel/private-output/inert-import/literal
helper/eight installed WAL controls 通过；这些 focused subsets 重叠，不加总伪造 full。
[PR CI37082996775](https://github.com/GhostFlying/facet/actions/runs/37082996775)
both/allsteps SUCCESS，实际 checkout673ba430，parents[1bb,M]/tree889d=M；
3.12.3 full2332/401.76s+CLI40/4.26s，3.13.16 full2332/334.80s+40/3.54s。
[Main CI37084976621](https://github.com/GhostFlying/facet/actions/runs/37084976621)
pushM both/allsteps SUCCESS，BOTH actual checkout M；API parents[cb5d481,b216]
和tree889d精确匹配。3.12.3 full2332/402.56s+CLI40/4.25s，3.13.16
full2332/317.44s+40/3.17s。Run headSha 本身不代替 actual tested-tree proof。

PR15 actual MERGED、Draft metadata仍true，head a9c 是 M ancestor；平台 cached
merge metadata4be0511不是实际 main M，也不是 worker 另执行的 merge。PR24/25/26/27
仍 OPEN Draft，heads4506/dd1/d688/b216 都是 M ancestors；不要仅凭 ancestry 编造
MERGED。没有 old-PR ready/retarget/closure 或 branch deletion。Issues9/13 保持 OPEN。
Source plans/历史树/报告保留，旧SQL62/246、OS183、a410、36b main FAIL、eb839
foundation CI FAIL、MIG1d529 green-but-HOLD、Source A prefreeze KBI 和74d9 K1
HOLD 都未被 green descendants 追认。下面旧 PR23 快照保留当时的 source/ownership。

有限 Source A 是 supplied-connection fresh37-table/v2 stopped storage、typed
receipts/original-key lookup/two-column CAS；不是 native opener/fork issuer、public
init/provider/daemon。V1 positive/v2 before-effects refusal 保留；没有 v1→v2
production predecessor/migration path。Read foundation 不开 state，shipping ACTION/
read/runtime/migration-provider inventories 仍空，完整 producer/RV11 待验收。
Restore 仍 approved plan-only/no source release；实际 OAuth/profile/files/credential
ownership/full backup bundle/CLI/Gmail/Dashboard/Compose/live/host/G1–G6 未齐。

Separate pure-rules U1 的 count PLAN clarification 已审通过，disjoint tests 仅受控
static-only preparation，native/source qualification 未放行且不纳入 current2332。
Calibration1647 PLAN approved 不等于执行：private capability 已因 EOF boundary
撤回，conditional trusted-host packet 仍准备中、未由本单元执行。历史17 cases/
9FAIL8PASS91.32s 的 cause/retirement unknown 保留，非生产 provenance gate。
后续模型仍只 Sol high/xhigh 或 Luna；历史授权 A 归属不改，不新派/reactivate Astra。

## Historical PR23 ownership、派工与证据 snapshot

以下保留原 PR23/1bb 的当时记录：其 Draft/unmerged/source-release 和758/1625
counts 是历史事实，当前 source integration/readiness 见上文和下表，不能借这些
旧状态或计数推断新源已实现/未实现、旧 HOLD 已 waived 或后续 gate 已通过。

Root 只调度/review 核证/汇报。原 shared docs worker 结束后，root 显式将 policy
unit 的文档 ownership 转给 `m103_os_source`；该六-doc unit 已在 PR19 实际集成，
原 `phase1-model-policy` worktree/branch 保留。`m103_os_source` 继续唯一 shared
current-state/integration ownership，当前受审 handoff 仅修改 status/progress/own plan，
位于 sibling `phase1-source-handoff` / `p/luchengxuan/phase1-source-handoff`；
旧 a57→ea80→36b handoff 已历史集成；本 Oct3 unit 从 clean36b 正常 FF 到
qualified main `befe278`，不覆写 frozen OS/harness 或 SQL source。
它仍保留各 OS/harness source tree；PR20/PR22 已独审并实际集成。Root 临时授权它
在 SQL tree 仅 normal-carry accepted main，产生 immutable a9c，没有 business edit；
`phase1_sol_policy_review`（Sol xhigh）仍是 SQL action source author，独立审查其未
authored 的 OS/harness source。`phase1_os_acceptance_sol` 独立审 SQL source/combined
carry 和本 Oct3 plan，root relay exact verdicts，source owner 不 self-accept。
Root 已将 approved migration tree/source allocation 显式转给 `m103_os_source`，
待本 docs freeze/CI start 后才开始有限实现；`phase1_sol_policy_review` 另有 released
no-state read-bootstrap foundation source，非 state opener/provider。Restore 保持
approved plan-only/no source release；两项新 source 的独审/CI 尚未完成。
后续模型仅 Sol high/xhigh 或 Luna；复杂设计/高风险独立 review 使用 Sol xhigh，
不再新派工或 reactivate Astra。历史合法 A 审查/作者记录保留，表中 A 是历史角色
标记，不授予新的 Astra 派工权限。M1-01/P1-00 已集成，旧 worktrees 保留。其他 workers
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
M1-02 r3/r4 和有限 result supplement 独立 approved 后已有实际 SQL；PR #15 已审
values/schema、finite repos、epoch/History/event/expansion、intent/result/recovery、
WAL snapshot、own-child SIGKILL、target audit 和 DB17 row-stepping rollback 切片。
早期 `c03e62f` 的 879 full/独审/exact CI 资格保留；当时 DB21 clean-stopped adapter
建 WAL/SHM 的反例及后续 d6 single-owner HOLD 保留为历史失败。新的有限 DB21 library
`16bcd0b99bf1118924b214bf9ded3976813f5e1a` 在模型变更前获得独立接受：R1 由实际
source 修正，1188 full offline tests、8 ownership controls、exact dual-Python
[CI 37014341329](https://github.com/GhostFlying/facet/actions/runs/37014341329) 成功。
PR15 仍 Draft/open、未 merged；production provider/runtime registry 为空，真实 managed
reads/RV11、actual action consumer/migration/restore 与整包 DB01–28 尚未完成。
后续 action library source `62d75c0253a6d66710a9d4d4a4b4346b8b55c6db` 的 164 AP/
1352 full/wheel 与 [CI37023546672](https://github.com/GhostFlying/facet/actions/runs/37023546672)
成功，但独立 source review 对两个 required findings 判定 HOLD。后续246 R3 foreign
UoW exit lifecycle finding 也保持历史 HOLD。Corrected c0bb 已非作者独审接受，
1598 full/73 R3/eight actual WAL/wheel 与
[CI37032060497](https://github.com/GhostFlying/facet/actions/runs/37032060497) dual-Python 成功。
Normal carry a9c 的 exact parents 为 c0bb/befe；六个 accepted-main paths 合入，
所有 SQL source/tests/plans 和 accepted OS/harness bytes 不变。第三方 combined 独审
实际1625 full/73 R3/150 OS/eight WAL/wheel 通过，
[CI37038807962](https://github.com/GhostFlying/facet/actions/runs/37038807962) dual-Python 成功。
Actual CI checkout `8e703daf` tree 等于 a9c，非仅借 run headSha；PR15 未 merged。
ACTION plan actual546L/unchanged hash，旧535L review wording 仅 clerical count。
Production action/read/provider/runtime registries 仍空，无 actual M5 producer。
Migration-entry plan SHA-256
`2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4` 已独审批准，
历史 untouched plan tree 曾从 OS worker 转给 SQL worker；accepted a9c/CI + qualified
befe 输入后，root 已正式转回 `m103_os_source` 并 source-release，仅原 finite scope。
Implementation/source acceptance/new CI 尚未完成；232 design3a9fedfc bytes 不改。
Restore229 plan1cee159f/design307 3e8bd09e 独审 approved，仍无 source release。
不用 immutable-live 或建 sidecar 捷径，完整 backup/provider/restore 仍未实现。
M1-03 r3 writer/OS design approved；read-runtime integration 另行准备。历史 OS183
跨同 physical root handles 的顺序反例保持 HOLD，不由 green CI 覆盖。C1 metadata
plan4b789515 独审 approved/source-released BEFORE code 后，corrected OS
`ea80db286fe110a69450076581b0b25810dcaf91` 获非作者 Sol 独立 acceptance：123 focused/
731 full、real R1 kernel/FD paired controls、256 full-chain terminal/live stress、fork/
strongThread/uncertain-close 与 noneditable wheel/import/privacy 通过，R1/C1 已修正。
[PR20](https://github.com/GhostFlying/facet/pull/20) 实际 normal-FF merged exactea80，
[candidate CI37025751696](https://github.com/GhostFlying/facet/actions/runs/37025751696)
与 [main CI37026826339](https://github.com/GhostFlying/facet/actions/runs/37026826339)
均 dual-Python 成功；无 force/bot merge/settings change。仅有限 low-level
Linux root/owner/view/key library 集成；真实 provider/actor/receipt/storage/credential/
第二 real daemon refusal pending，非任意 mounts/NFS/SMB/native FD/fork 资格。
PR22 exact `befe278285cfbd77798ffa58e8ef5d35b12e203a` 实际于2026-10-02T16:59:36Z
normal-FF merged；150 focused/758 full、20 complete nine-scenario child controls/
真实 sibling positive/descriptor+invalid-phase negative/wheel 和独审通过，
[candidate CI37036616826](https://github.com/GhostFlying/facet/actions/runs/37036616826)
与 [main CI37037683010](https://github.com/GhostFlying/facet/actions/runs/37037683010) 成功。
历史36b main FAIL 是 sequential real-ID allocation assumption，a410 H1 HOLD 是
mutable ancestor-stat oracle；均未观察到 foreign acceptance，失败记录仍保留。
所有 production OS/complete OS-C1 plan bytes 保持 ea80-exact。Read-bootstrap217
plan87321fe4/design229 9d28e18c 已独审 approved 并 root source-released 给
`phase1_sol_policy_review`，只是有限 no-state latch/probe/launcher；非 accepted source、
production state opener/provider/qualified runtime/RV11/daemon。
M1-04 full credential design approved，实际 owner/schema publication 仍 pending；
early pure `b94b610` 的独审/120OP/608full/wheel/CI 资格保留，docs/head 独审后 PR18
实际 merged exact `ff77e63`，main CI 37001014793 成功，仅 pure slice 集成。
M1-05 early library source `c455f71` 后两-doc head `f209fbe` 独审并实际集成 PR16，
[main CI](https://github.com/GhostFlying/facet/actions/runs/36989986570) SUCCESS；
488full/33 loggingproc/wheel 保留资格。Issue14/17 保持 open，真实 auth/DB/runtime/
HTTP/DOM/Compose 消费验收未完成。M1-06 r2/M2-01 r2/M6-01 r2 仅独审设计准备，
实际 consumer 输入和 source dispatch 另 gate；all-unknown 不算认证或 G3 完成。
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
| [M1-02](phase-1-execution-plan.md) | W1a | implementing | PR28 exactb5a integrates qualified a9c SQL/action + dd1 migration-entry finite libraries；independent combined2332/full/native/wheel + candidate/main actual-tree dualCI success；PR15 actualMERGED/Draftmetadata true；62/246/1d529 historicalHOLD retained；restore/provider/RV11/whole DB01–28 pending | ACTION corrections author phase1_sol_policy_review；earlier SQL authors 历史归属保留；migration/shared integration m103_os_source / exact source nonauthor phase1_os_acceptance_sol；combined M nonauthor bootstrap_storage_independent_qa；历史 S/A 保留 | [#9](https://github.com/GhostFlying/facet/issues/9), [PR15](https://github.com/GhostFlying/facet/pull/15), [PR25](https://github.com/GhostFlying/facet/pull/25), [PR28](https://github.com/GhostFlying/facet/pull/28) |
| [M1-03](phase-1-execution-plan.md) | W1b | implementing | PR20 OS ea80 + PR22 befe retained；PR28 exactb5a integrates corrected4506 no-state foundation + b216 supplied-connection Source A；independent2332/full/522focus/native/wheel and candidate/mainCI success；183/a410/36b/eb839/74K1 history retained；nativeB/issuer/provider/actor/credential/publicinit/daemon/CLI pending | writer 历史 design A；OS/harness/Source A/shared integration m103_os_source；read-foundation author phase1_sol_policy_review / Source A+M independent bootstrap_storage_independent_qa，其他 exact nonauthor attribution 保留 | [#13](https://github.com/GhostFlying/facet/issues/13), [PR20](https://github.com/GhostFlying/facet/pull/20), [PR22](https://github.com/GhostFlying/facet/pull/22), [PR24](https://github.com/GhostFlying/facet/pull/24), [PR27](https://github.com/GhostFlying/facet/pull/27), [PR28](https://github.com/GhostFlying/facet/pull/28) |
| [M1-04](phase-1-execution-plan.md) | W1b | implementing | early pure PR18 actual integrated exactff77 + mainCI success；120OP/608full/独审/wheel/CI 资格；full OAuth/profile/files/publication 未实现，actual writer/storage 未齐 | credential 历史 source A + shared docs S / 历史独立 A；后续独立 Sol | [#17](https://github.com/GhostFlying/facet/issues/17), [PR18](https://github.com/GhostFlying/facet/pull/18) |
| [M1-05](phase-1-execution-plan.md) | W1c | implementing | early pure/logging PR16 actual integrated exactf209 + mainCI success；488full/33 loggingproc/wheel资格；真实 consumers/完整包 pending | models/logging A + shared docs S / 非作者独立 reviewer | [#14](https://github.com/GhostFlying/facet/issues/14), [PR16](https://github.com/GhostFlying/facet/pull/16) |
| [M1-06](phase-1-execution-plan.md) | W1c | ready | r2 plan/ADR approved；separate pure/U1 guarded-static test preparation unintegrated/unqualified；trusted source-path/registry、public init/doctor/G1/G3 pending，finite Source A 非 native/production init issuer | auth 历史 design A / 历史非作者独立 A；prospective independent Sol，pure/U1 disjoint author/reviewer 由 root 派工 | 未物化 |
| [M2-01](phase-1-execution-plan.md) | W2a | ready | r2 adapter design 独审 approved；actual dependencies/consumer integration pending，无 source | adapter design A / 非作者独立 A | 未物化 |
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
| [M6-01](phase-1-execution-plan.md) | W5a | ready | r2 maintenance design 独审 approved；有限 pre-v2 receipt/journal/view seam 仍需实际 owned consumer integration，无 backup/restore CLI/source | maintenance design A / 非作者独立 A | 未物化 |
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
