# -*- coding: utf-8 -*-
"""
M2 接线测试 —— lossless_coverage / missing_translation 接进 step 实运行路径。

背景 (映射审计 M2): 这两个确定性核验此前已实现且测过, 但**未接进 step 的实运行路径**,
NODE_LOSSLESS 门控只能靠 handler 手报 PASS。M2 把它改为: step 在出稿前**据 ctx.table_rows
自动核验并挂物理证据**, 漏译则置 SUSPECT 并由终核阻断出稿。

本测试证明接线真实生效:
  1. 干净对勘表 → 自动 NODE_LOSSLESS PASS, 挂真实证据, 放行至 AWAIT_DELIVERY
  2. 含漏译(空汉译行)的对勘表 → 自动 SUSPECT → 终核阻断出稿 (RuntimeError)
  3. 新增 ctx 字段 (table_rows/final_text) 经 to_dict/from_dict 无损往返 (A(i))
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import (
    Context, Slice, Entry, State, GateItem, GateTiming, GateStatus,
    AdjudicationItem, AdjudicationType, GateResult,
)
from state_machine import runner as runner_mod


def _direct_ctx_ready_for_delivery(table_rows):
    """构造一个已裁/已复诵/已确认、带对勘表数据、停在 FINAL_CONFIRM 的直入 ctx。"""
    ctx = Context(slice=Slice(slice_id="m2", tone_level=2, entry=Entry.DIRECT))
    ctx.table_rows = table_rows
    ctx.final_text = "稀有解脱超意达空际，\n劫末千万火焰力须臾焚毁有漏烦恼稠林尽无余。"
    # 走到 FINAL_CONFIRM 前: 无待裁项, 直接推进
    from state_machine.transitions import initial_state, transition
    initial_state(ctx)                      # → GRADING
    ctx.log("[step] on_grading 已执行")      # 标记避免重跑
    transition(ctx, State.CONSULTATION)
    ctx.consultation_done = True
    transition(ctx, State.ADJUDICATION_RECITE)
    ctx.final_confirmed = True
    transition(ctx, State.FINAL_CONFIRM)
    return ctx


def _register_other_seven_gates(ctx):
    """补齐除 NODE_LOSSLESS/OUTPUT_CLEAN 外的其余六项 PRE_DELIVERY 门控 (让终核只卡待测项)。"""
    from gates.gate_checks import record_gate
    for item in GateItem:
        if item in (GateItem.NODE_LOSSLESS, GateItem.OUTPUT_CLEAN):
            continue  # 这两项由 M2 自动核, 不手挂
        record_gate(ctx, GateTiming.PRE_DELIVERY,
                    GateResult(item=item, status=GateStatus.PASS, evidence="e"))


def test_m2_lossless_auto_registered_from_table_rows():
    """干净对勘表 → step 自动核 NODE_LOSSLESS 为 PASS 并挂真实证据, 放行至 AWAIT_DELIVERY。"""
    rows = [("ངོ་མཚར་རྣམ་ཐར", "稀有解脱超意达空际"),
            ("དུས་མཐའི་མེ་ལྕེ", "劫末千万火焰力")]
    ctx = _direct_ctx_ready_for_delivery(rows)
    _register_other_seven_gates(ctx)

    result = runner_mod.step(ctx, runner_mod.Handlers())

    # NODE_LOSSLESS 应被 step 自动登记 (非手挂)
    key = (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS)
    assert key in ctx.gate_results, "step 未自动登记 NODE_LOSSLESS (M2 接线未生效)"
    assert ctx.gate_results[key].status == GateStatus.PASS
    assert "无漏译" in ctx.gate_results[key].evidence or "完整" in ctx.gate_results[key].evidence, \
        "NODE_LOSSLESS 证据非真实核验产物"
    # 终核放行
    assert result.signal == runner_mod.StepSignal.AWAIT_DELIVERY


def test_m2_missing_translation_becomes_suspect_and_blocks_delivery():
    """含漏译(空汉译行)的对勘表 → 自动 SUSPECT → 终核阻断出稿。"""
    rows = [("ངོ་མཚར་རྣམ་ཐར", "稀有解脱超意达空际"),
            ("དུས་མཐའི་མེ་ལྕེ", "")]   # 第2行漏译
    ctx = _direct_ctx_ready_for_delivery(rows)
    _register_other_seven_gates(ctx)

    with pytest.raises(RuntimeError) as ei:
        runner_mod.step(ctx, runner_mod.Handlers())
    # 阻断原因应指向存疑 (漏译致 NODE_LOSSLESS=SUSPECT)
    assert "存疑" in str(ei.value) or "SUSPECT" in str(ei.value)
    # 且 NODE_LOSSLESS 确被自动判 SUSPECT
    key = (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS)
    assert ctx.gate_results[key].status == GateStatus.SUSPECT
    assert "漏译" in ctx.gate_results[key].evidence


def test_m2_new_ctx_fields_roundtrip():
    """A(i): 新增 table_rows/final_text 经 to_dict/from_dict 无损往返, 元组得还原。"""
    rows = [("藏1", "汉1"), ("藏2", "汉2")]
    ctx = Context(slice=Slice(slice_id="m2", tone_level=2, entry=Entry.DIRECT))
    ctx.table_rows = rows
    ctx.final_text = "统稿正文"

    revived = Context.from_dict(ctx.to_dict())
    assert revived.table_rows == rows
    assert all(isinstance(r, tuple) for r in revived.table_rows), "还原后应为元组, 非列表"
    assert revived.final_text == "统稿正文"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
