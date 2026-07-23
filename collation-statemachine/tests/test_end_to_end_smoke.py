# -*- coding: utf-8 -*-
"""端到端冒烟: 直入模式最小切片跑完整流程 GRADING → DONE。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import (
    Context, Slice, Entry, GateItem, GateStatus, GateTiming, GateResult,
    AdjudicationItem, AdjudicationType,
)
from state_machine.runner import run, Handlers
from gates.gate_checks import record_gate


def on_grading(ctx):
    # LLM 产分级报告(此处桩), 登记一条待裁项(不自裁)
    ctx.adjudications.append(
        AdjudicationItem(idx=1, atype=AdjudicationType.TERM_LOCK, options=["A", "B"])
    )
    ctx.log("[handler] 分级报告已出, 登记待裁项1(术语锁定)")

def on_consultation(ctx):
    # 收人裁: 用户裁定 1A
    ctx.adjudications[0].resolved_choice = "A"
    ctx.log("[handler] 收到人裁: 1A")

def on_recite(ctx):
    # 复诵固定 + 用户最终确认
    for a in ctx.adjudications:
        a.recited = True
    ctx.final_confirmed = True
    ctx.log("[handler] 已复诵固定裁定, 收到最终确认")

def on_gate_report(ctx):
    ctx.log("[handler] 门控自检回报已出")

def on_delivery(ctx):
    ctx.log("[handler] 增量统稿已交付")


def main():
    ctx = Context(slice=Slice(slice_id="pbx-smoke", tone_level=2, entry=Entry.DIRECT))

    # 直入模式: 在 grading 阶段前先把八项终核门控登记齐(实运行由 on_gate handler 做,
    # 此处在 delivery 前通过一个前置 handler 补齐)
    def on_grading_full(c):
        on_grading(c)
        for item in GateItem:
            record_gate(c, GateTiming.PRE_DELIVERY,
                        GateResult(item=item, status=GateStatus.PASS,
                                   evidence=f"[{item.value}] 证据挂载"))

    handlers = Handlers(
        on_grading=on_grading_full,
        on_consultation=on_consultation,
        on_recite=on_recite,
        on_delivery=on_delivery,
        on_gate_report=on_gate_report,
    )
    ctx = run(ctx, handlers)

    print("\n=== 审计轨迹 ===")
    for line in ctx.audit_log:
        print(" ", line)
    assert ctx.state.name == "DONE"
    print("\n端到端冒烟通过: 直入切片 GRADING → DONE, 全闸门正确放行。")


if __name__ == "__main__":
    main()
