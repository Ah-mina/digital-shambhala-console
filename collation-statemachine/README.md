# collation-statemachine

把 `tibetan-chinese-collation` 工作流平移进确定性状态机的可执行骨架层。

**它不改动原 SKILL。** 原 `tibetan-chinese-collation/SKILL.md` 仍是规范源；本库
只把其中确定性的轮次纪律与门控闸门显式化为代码，让流程可程序化执行、可审计。

## 一句话

状态机守纪律（不跳轮、不漏门控、裸 PASS 被拦、待裁必经人裁），
LLM 做判断（分级校对、义理、术语），人做裁断（HITL 六类诀疑）。

## 代码 ↔ 原 SKILL 条款映射

| 文件 | 实现的原 SKILL 条款 |
|------|---------------------|
| `state_machine/states.py` | §三 轮次状态集、§四 语体、§五 待裁六类、§六 八项三态 |
| `state_machine/transitions.py` | §三 轮次纪律、双入口、§七1 早停优先 |
| `state_machine/runner.py` | 全流程编排；认知工作经 Handlers 回调交 LLM |
| `gates/hard_stops.py` | §三 三个早停闸（违反=严重工作流错误） |
| `gates/gate_checks.py` | §六 八项门控、三处时机、裸PASS禁绝、§2.4 无损覆盖、§五 漏译核验 |
| `gates/syllable_check.py` | §八 音节脚本（**原样复用**，加薄封装） |
| `grading/adjudication_router.py` | §五 待裁六类形式路由 + 可自验项拒入待裁的反模式闸 |
| `grading/grade_contract.py` | §五 A/B/C 条目结构契约（B级必附改译、位置换算、漏译挂证据） |
| `tests/` | 每条纪律一个测试 + 端到端 + grading + 集成冒烟 |

## 三个固化决定

- **拍板1 = 粗粒度**：状态机只管轮次/停顿/门控；分级校对、术语裁量等认知工作
  留 LLM 在状态内部做。状态机不替 LLM 判断。
- **拍板2 = 复用 §八脚本**：`tib_syl`/`han_len` 一字未改纳入，只加结构化封装。
- **拍板3 = 并存新建**：不动原 SKILL，本库作为其可执行骨架层。

## 运行

```bash
cd collation-statemachine
python tests/test_workflow_discipline.py    # 12 项纪律测试
python tests/test_grading.py                # 12 项 分级契约+诀疑路由+反模式闸
python tests/test_grading_integration.py    # grading 层与状态机协同
python tests/test_end_to_end_smoke.py       # 直入切片端到端
```

## 细粒度层：分级脚手架 + 诀疑路由 + 反模式闸（`grading/`，甲方案）

在粗粒度状态机之上加一层**确定性约束**，把 §五 中形式可判的部分收归代码，
**不碰实质判定**：

- **诀疑路由**：候选待裁项依形式特征（引文标记 / 先例命中 / 各类旗标）确定性
  分派到六类之一。
- **反模式闸**（§五核心）：窗口内可自验之项（括注状态已定、术语首遇但先例已命中）
  被**禁止**包装成待裁上呈——代码强制，命中即抛错。
- **分级契约**：B级必附推荐改译、A级漏译必挂节点比对证据、位置必换算为对勘表编号。
  不合规打回，但不判定分级实质对错。

"这是不是误译""归哪类"的实质判断仍由 LLM 初判，本层只校验其输出合法、并把
形式路由与反模式拦截确定性化。

## 三个硬停顿（代码强制，不依赖自觉）

1. draft 前禁任何翻译输出（§三1轮，最高优先级）
2. 核校完成前禁分级报告/统稿（§三2轮）
3. 磋商不可省，直入亦然：GRADING→DELIVERY 必经 磋商→复诵→全裁→最终确认（§三·甲5）

## 门控（§六）

八项 × 三态（PASS须挂证据 / SUSPECT / NOT_CHECKED），三处时机。
**裸 PASS 在代码层抛错**——报 PASS 必须挂可核产物，对应 §六回环3
"要么挂证据报 PASS，要么承认未核"。

## 认知/确定性分界

确定性（状态机）：轮次推进、硬停顿、门控闸门、物理核验（无损覆盖/漏译/tsheg·CJK 计数）。
认知（LLM，状态内）：A/B/C 分级、义理、句式判断。
人裁（HITL）：术语锁定、引文偈成例、底本正字、密义。

## 未做（留后续）

- 常规入口（静默轮/对勘表轮）handler 仅骨架，当前实战多走直入。
- 声部排版、统稿洁净等认知性门控项的自动证据产出待补，现由 handler 挂 LLM 证据。
