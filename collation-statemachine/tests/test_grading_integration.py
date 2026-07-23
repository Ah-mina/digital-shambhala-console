# -*- coding: utf-8 -*-
"""
集成冒烟: grading 层(路由+契约) 与状态机协同。
证明 GRADING 状态内 LLM 产出经契约校验、待裁项经确定性路由后, 正确进入流程。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import (
    Context, Slice, Entry, GateItem, GateStatus, GateTiming, GateResult,
    AdjudicationItem,
)
from state_machine.runner import run, Handlers
from gates.gate_checks import record_gate
from grading.adjudication_router import AdjudicationSignals, route
from grading.grade_contract import Grade, GradedItem, GradingReport


def make_grading_handler():
    def on_grading(ctx):
        # 1. LLM 产分级报告(桩) → 结构契约校验
        report = GradingReport(items=[
            GradedItem(grade=Grade.A, location="P1", problem="主被动颠倒",
                       tibetan_collation="藏文对勘…"),
            GradedItem(grade=Grade.B, location="偈1句2", problem="漏译限定词",
                       tibetan_collation="藏文对勘…", recommended_fix="补『唯』"),
        ])
        report.validate_all()   # 不合规会抛错, 迫使 LLM 补全
        ctx.log(f"[grading] {report.summary()}")

        # 2. 候选待裁项 → 确定性路由分类
        candidates = [
            AdjudicationSignals(is_first_occurrence=True, precedent_hit=False),  # 术语锁定
            AdjudicationSignals(has_quote_marker=True, is_verse=True),           # 引文成例
        ]
        for i, sig in enumerate(candidates, 1):
            routed = route(sig)   # 反模式闸+决策树; 可自验项会在此被拒
            ctx.adjudications.append(
                AdjudicationItem(idx=i, atype=routed.atype, options=["A", "B"]))
            ctx.log(f"[grading] 待裁项{i} 路由 → {routed.atype.value} ({routed.routing_basis})")

        # 3. 补齐终核门控证据
        for item in GateItem:
            record_gate(ctx, GateTiming.PRE_DELIVERY,
                        GateResult(item=item, status=GateStatus.PASS,
                                   evidence=f"[{item.value}] 证据"))
    return on_grading


def main():
    ctx = Context(slice=Slice(slice_id="pbx-integ", tone_level=2, entry=Entry.DIRECT))

    def on_consult(c):
        for a in c.adjudications:
            a.resolved_choice = "A"
    def on_recite(c):
        for a in c.adjudications:
            a.recited = True
        c.final_confirmed = True

    ctx = run(ctx, Handlers(
        on_grading=make_grading_handler(),
        on_consultation=on_consult,
        on_recite=on_recite,
    ))

    print("\n=== 关键轨迹 ===")
    for line in ctx.audit_log:
        if "[grading]" in line or "路由" in line or "转移" in line:
            print(" ", line)
    assert ctx.state.name == "DONE"
    assert len(ctx.adjudications) == 2
    print("\n集成冒烟通过: 契约校验 + 确定性路由 + 状态机流转 协同, GRADING→DONE。")


if __name__ == "__main__":
    main()
