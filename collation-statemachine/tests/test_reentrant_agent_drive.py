# -*- coding: utf-8 -*-
"""
红队测试 —— 坐实"落地为 agent 状态机"的核心架构缺口: 现有 run() 不可重入。

背景 (DEVLOG 方案第一步):
  把 collation-statemachine 落地到编程 agent 界面 (无前端) 时, 交互是**多轮**的:
  agent 在 CONSULTATION(收人裁)、FINAL_CONFIRM(收"确认无误") 这些 HITL 点, 必须
  **交出控制权、等下一个 agent turn 再回来**。

  但现有 state_machine/runner.py 的 run(ctx, handlers) 是**一次性同步驱动**: 它在
  单次调用里顺序跑完 on_grading → on_consultation → on_recite → ... → DONE。
  它没有"推进到需要外部输入就挂起、把控制权交回 agent、下一 turn 再 step 恢复"的能力。

本测试的职责 (先证否, 后修复 —— 承红队纪律):
  按**尚未实现**的可重入 API (runner.step / StepResult / StepSignal) 编写期望行为,
  证明它在当前代码上跑不起来。测试当前应 **失败** (红); 待方案第 2 步实现 step +
  ctx 持久化后, 应转 **绿**。

  失败必须落在**正确的原因**上 —— "没有可重入 step 驱动器", 而非偶然的别的错。
  故 test_reentrancy_gap_is_real 显式断言: step API 不存在 (ImportError/AttributeError),
  即缺口真实存在。另两个测试描述 step 一旦存在时必须满足的行为契约。

一律不改动原 SKILL、不改动现有 27 测试。本文件只**新增**期望, 不重写纪律。
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import (
    Context, Slice, Entry, State,
    AdjudicationItem, AdjudicationType,
)
from state_machine import runner as runner_mod


# ── 尚未实现的可重入 API 的期望名字 (方案第 2 步将落地) ──
# step(ctx, handlers) -> StepResult, 推进到"需外部输入"即返回, 交回控制权。
# StepResult.signal ∈ {AWAIT_ADJUDICATION, AWAIT_FINAL_CONFIRM, DONE, ...}
_HAS_STEP = hasattr(runner_mod, "step")
_HAS_STEP_RESULT = hasattr(runner_mod, "StepResult")


def _fresh_direct_ctx() -> Context:
    """直入模式最小切片: 起点即 GRADING (§三·甲 豁免前两轮)。"""
    return Context(slice=Slice(slice_id="pbx-reentrant", tone_level=2, entry=Entry.DIRECT))


def test_reentrancy_gap_is_real():
    """
    坐实缺口: 当前 runner **没有**可重入的 step 驱动器 / StepResult 信号类型。
    这正是"落地为 agent 状态机"缺的那一块。

    当前代码: step / StepResult 不存在 → 本测试**失败** (红), 缺口被坐实。
    方案第 2 步实现后: 二者存在 → 本测试转**绿**。
    """
    assert _HAS_STEP, (
        "缺口坐实: state_machine.runner 无 step() —— 现有 run() 是一次性同步驱动, "
        "无法在 HITL 点挂起并把控制权交回 agent。这是落地为 agent 状态机要补的核心件。"
    )
    assert _HAS_STEP_RESULT, (
        "缺口坐实: 无 StepResult —— 无从表达'推进到此需要外部输入X, 请 agent 下一 turn 回填'。"
    )


@pytest.mark.skipif(not _HAS_STEP, reason="step 尚未实现 (方案第 2 步) —— 缺口测试先行")
def test_step_suspends_at_consultation_returning_control_to_agent():
    """
    行为契约 (step 实现后必须满足):
    直入切片推进到 GRADING、产出分级报告并登记待裁项后, step 必须在人裁到达之前
    **挂起并交回控制权** —— 返回 AWAIT_ADJUDICATION, 且此刻待裁项仍未裁 (resolved_choice is None)。

    这对应真实 agent 交互: 报告要先呈给用户, 用户的裁断在**下一个 turn**才来。
    现有一次性 run() 做不到这一点 —— 它会在同一次调用里径直跑完 on_consultation。
    """
    ctx = _fresh_direct_ctx()

    def on_grading(c):
        # LLM 产分级报告(桩) + 登记一条待裁项, 但**不自裁** (§五: 裁断权属人)
        c.adjudications.append(
            AdjudicationItem(idx=1, atype=AdjudicationType.TERM_LOCK, options=["A", "B"])
        )

    handlers = runner_mod.Handlers(on_grading=on_grading)

    result = runner_mod.step(ctx, handlers)

    # 必须挂起在"等人裁", 而非一路跑到底
    assert result.signal == runner_mod.StepSignal.AWAIT_ADJUDICATION, (
        f"step 应在 HITL 点挂起等人裁, 实得 {result.signal}"
    )
    # 挂起时控制权已交回 agent: 待裁项尚未裁 (下一 turn 才由 agent 回填用户裁断)
    assert ctx.adjudications[0].resolved_choice is None, (
        "挂起点上待裁项不应已被裁 —— 裁断须来自下一 turn 的用户输入, 而非状态机自代"
    )
    # 且流程未擅自越过磋商推进到统稿
    assert ctx.state != State.DONE


@pytest.mark.skipif(not _HAS_STEP, reason="step 尚未实现 (方案第 2 步) —— 缺口测试先行")
def test_step_resumes_next_turn_after_user_signal_persisted_ctx():
    """
    行为契约 (step 实现后必须满足):
    可重入性 = 上一 turn 挂起的 ctx, 经序列化落盘 → 下一 turn 读回 → 回填用户裁断
    → 再 step, 流程从**原挂起点**继续, 而非从头重来。

    这检验两件"落地"必需能力: ①ctx 可持久化(序列化-反序列化后等价) ②step 可从
    持久化的中途态恢复推进。现有 run() 无中途态可存, 更无从恢复。
    """
    ctx = _fresh_direct_ctx()

    def on_grading(c):
        c.adjudications.append(
            AdjudicationItem(idx=1, atype=AdjudicationType.TERM_LOCK, options=["A", "B"])
        )

    handlers = runner_mod.Handlers(on_grading=on_grading)

    # turn 1: 推进到挂起
    r1 = runner_mod.step(ctx, handlers)
    assert r1.signal == runner_mod.StepSignal.AWAIT_ADJUDICATION

    # turn 边界: ctx 落盘再读回 (容器可能在 turn 间重置 → 必须可序列化)
    assert hasattr(ctx, "to_dict") and hasattr(Context, "from_dict"), (
        "落地需要 ctx 可持久化: 缺 to_dict/from_dict, 无法跨 turn 存取中途态"
    )
    revived = Context.from_dict(ctx.to_dict())
    assert revived.state == ctx.state
    assert len(revived.adjudications) == 1
    assert revived.adjudications[0].resolved_choice is None

    # turn 2: 回填用户裁断, 从原挂起点恢复
    revived.adjudications[0].resolved_choice = "A"
    r2 = runner_mod.step(revived, handlers)
    # 恢复后应向前推进 (至少离开"等人裁"), 而非回到起点重跑 grading
    assert r2.signal != runner_mod.StepSignal.AWAIT_ADJUDICATION
    assert len(revived.adjudications) == 1, "恢复不应重跑 on_grading 致重复登记待裁项"


@pytest.mark.skipif(not _HAS_STEP, reason="step 尚未实现")
def test_each_step_suspends_at_exactly_one_await_point():
    """
    可重入完整性: 单次 step 不得跨越多个 AWAIT 点连跑到底。
    即便一个信号同时满足多个前置条件 (裁断+复诵+最终确认一次性给全),
    step 仍须逐点挂起, 每次只前进到下一个 AWAIT_* —— 这样 agent 每 turn 只需应对
    一个明确诉求, 且 DELIVERY 前必留一次 AWAIT_DELIVERY 让 agent 产出真实统稿。
    """
    from state_machine.states import (
        GateItem, GateStatus, GateTiming, GateResult,
    )
    ctx = _fresh_direct_ctx()

    def on_grading(c):
        c.adjudications.append(
            AdjudicationItem(idx=1, atype=AdjudicationType.TERM_LOCK, options=["A", "B"])
        )
    handlers = runner_mod.Handlers(on_grading=on_grading)

    # 到 AWAIT_ADJUDICATION
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_ADJUDICATION

    # 一次性给全: 裁断 + 复诵 + 最终确认 (且补齐八项门控)
    ctx.adjudications[0].resolved_choice = "A"
    ctx.adjudications[0].recited = True
    ctx.final_confirmed = True
    for item in GateItem:
        ctx.gate_results[(GateTiming.PRE_DELIVERY, item)] = GateResult(
            item=item, status=GateStatus.PASS, evidence="e")

    # 尽管条件全满足, 下一 step 必须停在 AWAIT_DELIVERY, 不得径直 DONE
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_DELIVERY, (
        f"应逐点挂起于 AWAIT_DELIVERY 让 agent 产统稿, 实得 {r.signal} (跨点连跑=可重入破损)"
    )
    # 出稿后须停在门控回报 (§六统稿后回环: 列八项状态、只收存疑/未核反馈), 再一步才 DONE
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_GATE_REPORT, (
        f"应挂起于 AWAIT_GATE_REPORT (§六回环), 实得 {r.signal}"
    )
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.DONE


def test_delivery_state_reasserts_terminal_verification_on_resume():
    """
    红队 (终核绕过防护): ctx 从 AWAIT_DELIVERY 落盘-resume 后, 直接进 DELIVERY 块,
    必须**再次**过终核, 不得因'已在 DELIVERY 态'而跳过八项校验直出稿。

    这防的是 A(i) 持久化带来的绕过路径: 上一 turn 停在 AWAIT_DELIVERY→落盘,
    下一 turn 若门控未齐(或被篡改), step 进 DELIVERY 块仍须被终核拦下。
    """
    from state_machine.states import Context, Slice, Entry, State
    # 造一个'已在 DELIVERY 态但门控为空'的畸形 ctx (模拟脏 resume)
    ctx = Context(slice=Slice(slice_id="bypass", tone_level=2, entry=Entry.NORMAL))
    ctx.state = State.DELIVERY
    ctx.final_confirmed = True
    # 八项门控一项都没登记 → 终核必须阻断, 而非放行出稿
    with pytest.raises(RuntimeError) as ei:
        runner_mod.step(ctx, runner_mod.Handlers())
    assert "终核" in str(ei.value) or "未核" in str(ei.value)
    # 且未擅自推进到 GATE_REPORT/DONE
    assert ctx.state == State.DELIVERY


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
