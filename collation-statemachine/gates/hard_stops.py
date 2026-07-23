# -*- coding: utf-8 -*-
"""
硬停顿闸门 —— 状态机不可逾越的纪律。

规范源: SKILL §三 早停规则 (优先级最高) + §七1。
这三个闸门在 SKILL 中均标注"违反视为严重工作流错误", 故在代码层强制拦截,
而非依赖 LLM 自觉。
"""
from __future__ import annotations

from state_machine.states import Context, State, Entry


class HardStopViolation(RuntimeError):
    """触碰硬停顿即抛出。对应 SKILL 的"严重工作流错误"。"""


def guard_no_translation_before_draft(ctx: Context, about_to_output_translation: bool) -> None:
    """
    闸门1 (§三1轮, 最高优先级): 物理收到 [draft] 前, 禁止任何翻译输出。
    直入模式下"输入即核定"声明+对勘表全文即等价于已过此闸 (draft_received=True)。
    """
    if about_to_output_translation and not ctx.draft_received:
        raise HardStopViolation(
            "早停闸1: 未收到 [draft] 初稿前禁止输出任何翻译内容 (§三1轮, 最高优先级)"
        )


def guard_no_report_before_collation_confirmed(ctx: Context, about_to_output_report_or_delivery: bool) -> None:
    """
    闸门2 (§三2轮): 未收到核校完成信号前, 禁止出分级报告/统稿。
    直入模式: "输入即核定"声明即为核校完成信号 (collation_confirmed=True)。
    """
    if about_to_output_report_or_delivery and not ctx.collation_confirmed:
        raise HardStopViolation(
            "早停闸2: 未收到对勘表核校完成信号前, 禁止输出分级报告或统稿 (§三2轮)"
        )


def guard_consultation_before_delivery(ctx: Context) -> None:
    """
    闸门3 (§三·甲5, §三·丙, §七1): 磋商确认环节不可省 —— 即便直入已核定,
    GRADING → DELIVERY 之间必经 磋商 → 复诵 → 最终确认。
    """
    if not ctx.consultation_done:
        raise HardStopViolation(
            "早停闸3: 磋商环节不可省, 不得径出统稿 (§三·甲5: 直入亦不豁免磋商)"
        )
    # §七6: 所有待裁项须已复诵固定
    unrecited = [a.idx for a in ctx.adjudications
                 if a.resolved_choice is not None and not a.recited]
    if unrecited:
        raise HardStopViolation(
            f"早停闸3: 裁定项 {unrecited} 已裁但未复诵固定, 不得出统稿 (§七6)"
        )
    # 所有登记的待裁项必须已裁 (状态机强制其被裁, 但不替裁)
    unresolved = [a.idx for a in ctx.adjudications if a.resolved_choice is None]
    if unresolved:
        raise HardStopViolation(
            f"早停闸3: 待裁项 {unresolved} 尚未经人裁, 不得出统稿 (HITL 硬停顿)"
        )
    if not ctx.final_confirmed:
        raise HardStopViolation(
            "早停闸3: 未收到最终确认, 不得输出统稿 (§三·丙)"
        )


def apply_direct_entry_ratification(ctx: Context) -> None:
    """
    直入模式 (§三·甲): "输入即核定"声明等价于已过闸门1、2。
    效力边界 (§三·甲2): 仅覆盖所提交对勘表原文本; 新拟改句不承袭核定。
    """
    if ctx.slice.entry != Entry.DIRECT:
        return
    ctx.draft_received = True
    ctx.collation_confirmed = True
    ctx.slice.input_ratified = True
    ctx.log("直入模式: 输入即核定 → 闸门1、2 视为已过 (效力仅覆盖原文本, §三·甲2)")
