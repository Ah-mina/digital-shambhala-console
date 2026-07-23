# -*- coding: utf-8 -*-
"""
甲 · 常规入口补齐测试 —— 完整四步节奏 (静默→对勘表→分级→统稿) 逐点挂起。

背景 (映射审计 甲): 此前 step 常规入口只有骨架, 且 draft 等待与核校等待复用同一
AWAIT_GRADING 信号 (M1 语义不清)。甲补齐后, 常规入口按 §三 完整驱动:
  SILENT_INTAKE → (等draft, AWAIT_DRAFT) → 产四事缓存 → COLLATION_TABLE
  → (出对勘表+音节表, 等核校, AWAIT_COLLATION) → GRADING → ... → 统稿 → 门控回报

本测试证明:
  1. 各轮以**专用信号**挂起 (AWAIT_DRAFT / AWAIT_COLLATION), 不再复用 AWAIT_GRADING
  2. 每轮的认知 handler (on_silent/on_table) 只跑一次 (可重入)
  3. 常规入口不豁免任何后续闸门 (磋商/裁/复诵/确认照常)
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import Context, Slice, Entry, State
from state_machine import runner as runner_mod


def _normal_ctx():
    return Context(slice=Slice(slice_id="normal", tone_level=2, entry=Entry.NORMAL))


def test_normal_entry_suspends_at_draft_with_dedicated_signal():
    """静默轮: 收 draft 前挂起于 AWAIT_DRAFT (专用信号, 非 AWAIT_GRADING)。"""
    ctx = _normal_ctx()
    r = runner_mod.step(ctx, runner_mod.Handlers())
    assert r.signal == runner_mod.StepSignal.AWAIT_DRAFT, (
        f"常规入口静默轮应挂起于 AWAIT_DRAFT, 实得 {r.signal}"
    )
    assert ctx.state == State.SILENT_INTAKE


def test_normal_entry_full_four_round_drive():
    """完整四步节奏逐点挂起, 各 handler 只跑一次。"""
    ctx = _normal_ctx()
    silent_calls = {"n": 0}
    table_calls = {"n": 0}

    def on_silent(c):
        silent_calls["n"] += 1
        c.log("四事缓存: 节点/声部/风险区/无损自检")

    def on_table(c):
        table_calls["n"] += 1
        # 出对勘表时填入表行数据 (供 M2 出稿前自动核无损覆盖)
        c.table_rows = [("藏1", "汉1"), ("藏2", "汉2")]
        c.log("对勘表+音节对照表已出")

    handlers = runner_mod.Handlers(on_silent=on_silent, on_table=on_table)

    # turn 1: 挂起等 draft
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_DRAFT

    # turn 2: draft 到达 → 产四事缓存 → 挂起等核校完成
    ctx.draft_received = True
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_COLLATION, (
        f"draft 后应挂起于 AWAIT_COLLATION, 实得 {r.signal}"
    )
    assert ctx.state == State.COLLATION_TABLE
    assert silent_calls["n"] == 1, "on_silent 应只跑一次"
    assert table_calls["n"] == 1, "on_table 应只跑一次"

    # 再 step 一次(核校仍未完成) → 仍挂 AWAIT_COLLATION, on_table 不重跑 (可重入)
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_COLLATION
    assert table_calls["n"] == 1, "on_table 不应重跑"

    # turn 3: 核校完成 → 进 GRADING → 无待裁项 → 一路到 AWAIT_FINAL_CONFIRM
    ctx.collation_confirmed = True
    r = runner_mod.step(ctx, handlers)
    # 无待裁项时, GRADING→CONSULTATION→ADJUDICATION_RECITE, 停在等最终确认
    assert r.signal == runner_mod.StepSignal.AWAIT_FINAL_CONFIRM, (
        f"实得 {r.signal} (state={ctx.state.name})"
    )

    # turn 4: 最终确认 → 补齐门控 → 终核放行 → AWAIT_DELIVERY
    ctx.final_confirmed = True
    from gates.gate_checks import record_gate
    from state_machine.states import GateItem, GateTiming, GateStatus, GateResult
    for item in GateItem:
        if item == GateItem.NODE_LOSSLESS:
            continue  # M2 自动核 (ctx.table_rows 已由 on_table 填)
        record_gate(ctx, GateTiming.PRE_DELIVERY,
                    GateResult(item=item, status=GateStatus.PASS, evidence="e"))
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_DELIVERY
    # M2: NODE_LOSSLESS 由 step 自动据 table_rows 核出并登记
    assert (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS) in ctx.gate_results

    # turn 5: 出稿 → 门控回报挂起 → DONE
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.AWAIT_GATE_REPORT
    r = runner_mod.step(ctx, handlers)
    assert r.signal == runner_mod.StepSignal.DONE
    assert ctx.state == State.DONE


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
