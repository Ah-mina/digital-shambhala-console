# -*- coding: utf-8 -*-
"""
确定性状态转移。

规范源: SKILL §三 (轮次纪律) + §七1 (早停优先)。
状态机只决定"能否从A轮进B轮", 内容判断留给 LLM (拍板1=甲)。
"""
from __future__ import annotations

from state_machine.states import Context, State, Entry
from gates.hard_stops import (
    guard_no_translation_before_draft,
    guard_no_report_before_collation_confirmed,
    guard_consultation_before_delivery,
    apply_direct_entry_ratification,
)


# 合法转移图。键=当前态, 值=允许的下一态集合。
LEGAL_TRANSITIONS = {
    State.SILENT_INTAKE: {State.COLLATION_TABLE},
    State.COLLATION_TABLE: {State.GRADING},
    State.GRADING: {State.CONSULTATION},
    State.CONSULTATION: {State.ADJUDICATION_RECITE},
    State.ADJUDICATION_RECITE: {State.FINAL_CONFIRM},
    State.FINAL_CONFIRM: {State.DELIVERY},
    State.DELIVERY: {State.GATE_REPORT},
    State.GATE_REPORT: {State.DONE},
}


class IllegalTransition(RuntimeError):
    pass


def initial_state(ctx: Context) -> State:
    """
    入口决定起始态。
    直入模式 (§三·甲): 豁免前两轮, 从 GRADING 起, 且输入即核定过闸1、2。
    """
    if ctx.slice.entry == Entry.DIRECT:
        apply_direct_entry_ratification(ctx)
        ctx.state = State.GRADING
        ctx.log("入口=直入: 起始态=GRADING (§三·甲 豁免前两轮)")
        # 直入模式下 GRADING 的合法前驱不是 COLLATION_TABLE
        return State.GRADING
    ctx.state = State.SILENT_INTAKE
    ctx.log("入口=常规: 起始态=SILENT_INTAKE (§三·乙)")
    return State.SILENT_INTAKE


def transition(ctx: Context, target: State) -> None:
    """
    执行一次转移, 在转移点施加相应硬停顿闸门。
    """
    cur = ctx.state

    # 直入模式允许 GRADING 作为合法起点(无 COLLATION_TABLE 前驱)
    direct_entry_ok = (
        ctx.slice.entry == Entry.DIRECT
        and cur == State.GRADING
        and target == State.CONSULTATION
    )
    if not direct_entry_ok:
        if target not in LEGAL_TRANSITIONS.get(cur, set()):
            raise IllegalTransition(f"非法转移: {cur.name} → {target.name} (§三轮次纪律)")

    # ── 转移点的硬停顿 ──
    if target == State.GRADING:
        # 进入分级报告前: 闸2 (须核校完成)
        guard_no_report_before_collation_confirmed(ctx, about_to_output_report_or_delivery=True)
    if target == State.COLLATION_TABLE:
        # 进入对勘表(含翻译内容)前: 闸1 (须 draft)
        guard_no_translation_before_draft(ctx, about_to_output_translation=True)
    if target == State.DELIVERY:
        # 出统稿前: 闸3 (磋商+复诵+全裁+最终确认)
        guard_consultation_before_delivery(ctx)

    ctx.state = target
    ctx.log(f"转移: {cur.name} → {target.name}")
