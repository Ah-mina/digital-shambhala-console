# -*- coding: utf-8 -*-
"""
对勘状态机运行器。

规范源: SKILL 全文。
粒度 (拍板1=甲): 运行器只推进轮次、施加闸门、登记门控; 每个状态内部的
认知工作 (分级、术语、拟改句) 由注入的 handler 回调完成, handler 内部可调 LLM,
但**不**决定状态转移 —— 转移由本模块确定性代码依 SKILL 纪律做出。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from state_machine.states import (
    Context, State, Entry, Slice,
    GateTiming, GateItem, GateResult, GateStatus,
    AdjudicationItem,
)
from state_machine.transitions import initial_state, transition
from gates.gate_checks import (
    verify_pre_delivery_complete,
    record_lossless_coverage,
    record_output_clean,
    record_syllable_count,
)


# handler 签名: 接收 ctx, 在该状态内做认知工作 (可调 LLM), 就地写回 ctx。
Handler = Callable[[Context], None]


class Handlers:
    """各状态的认知处理器。测试时可注入桩; 实运行时接 LLM。"""
    def __init__(
        self,
        on_silent: Optional[Handler] = None,
        on_table: Optional[Handler] = None,
        on_grading: Optional[Handler] = None,      # 产 A/B/C + 登记待裁项
        on_consultation: Optional[Handler] = None, # 收人裁 → 填 resolved_choice
        on_recite: Optional[Handler] = None,       # 复诵固定 → recited=True
        on_delivery: Optional[Handler] = None,     # 出增量统稿
        on_gate_report: Optional[Handler] = None,  # 登记 PRE_DELIVERY 八项门控
    ):
        self.on_silent = on_silent or (lambda c: None)
        self.on_table = on_table or (lambda c: None)
        self.on_grading = on_grading or (lambda c: None)
        self.on_consultation = on_consultation or (lambda c: None)
        self.on_recite = on_recite or (lambda c: None)
        self.on_delivery = on_delivery or (lambda c: None)
        self.on_gate_report = on_gate_report or (lambda c: None)


def run(ctx: Context, handlers: Handlers) -> Context:
    """
    驱动全流程。返回终态 ctx (含完整 audit_log)。
    调用方按真实交互节奏, 在收到用户信号后推进; 此处为一次性顺序驱动的
    参考实现 —— 各 handler 内部负责等待/消费用户输入并置位相应闸标志。
    """
    state = initial_state(ctx)

    if state == State.SILENT_INTAKE:
        handlers.on_silent(ctx)
        # 常规: 须等 draft 到达 (handler 置 draft_received) 才进对勘表
        transition(ctx, State.COLLATION_TABLE)
        handlers.on_table(ctx)
        # 须等核校完成信号 (handler 置 collation_confirmed) 才进第三轮
        transition(ctx, State.GRADING)
    # 直入模式: initial_state 已把 state 置 GRADING 并过闸1、2

    # ── 第三轮 (两入口汇合) ──
    handlers.on_grading(ctx)          # 产分级报告 + 登记待裁项 (不自裁)

    transition(ctx, State.CONSULTATION)
    handlers.on_consultation(ctx)     # 收人裁: 每条 AdjudicationItem 填 resolved_choice
    ctx.consultation_done = True

    transition(ctx, State.ADJUDICATION_RECITE)
    handlers.on_recite(ctx)           # 逐条复诵固定 (§七6): recited=True
    # 复诵后须最终确认
    if not ctx.final_confirmed:
        # 实运行由 handler 在收到"确认无误"后置位; 此处不代置
        ctx.log("等待最终确认 (§三·丙): final_confirmed 由用户信号置位")

    transition(ctx, State.FINAL_CONFIRM)

    # 出统稿前: 闸3 在 transition(DELIVERY) 内强制
    transition(ctx, State.DELIVERY)
    # 统稿前终核 (§六最后一道): 八项须齐、A级全修PASS、无存疑
    verify_pre_delivery_complete(ctx)
    handlers.on_delivery(ctx)         # 出增量统稿 (§七5)

    transition(ctx, State.GATE_REPORT)
    handlers.on_gate_report(ctx)      # 门控自检回报 (§六回环)

    transition(ctx, State.DONE)
    ctx.log("流程完成")
    return ctx


# ════════════════════════════════════════════════════════════════════════
# 可重入驱动器 (方案第 2 步; 拍板 A(i)/B(ii)/C(i))
#
# 落地为 agent 状态机 (无前端) 的核心: run() 是一次性同步驱动, 无法在 HITL 点
# 挂起并把控制权交回 agent。step() 补这一块 —— 推进到"需要外部输入"即**挂起**,
# 返回 StepResult(signal=AWAIT_*), 由 agent 在**下一 turn**回填用户输入后再调 step。
#
# 拍板 B(ii) = agent 主导: 状态机不驱动对话, 只在 step 内**校验**每一次推进是否
#   合法 (硬停顿/门控经不变的 transition 强制), 到 HITL 点即挂起交回 agent。
#   B(ii) 的灵活不削弱强制力 —— 闸门仍在 transition/verify 里抛错, 与 run() 同源。
# 拍板 A(i) = 每步整份 ctx 落盘: step 不持有跨调用状态, 全部状态在 ctx 里,
#   故 agent 可在两次 step 之间 ctx.to_dict() 落盘、下一 turn from_dict() 读回。
# 拍板 C(i) = 结构化 JSON 信号: StepResult 可 as_json() 供 agent 消费 (见 run_agent.py)。
# ════════════════════════════════════════════════════════════════════════


class StepSignal(Enum):
    """step 挂起/终止信号。AWAIT_* 表示'需 agent 下一 turn 回填 X 后再 step'。"""
    AWAIT_DRAFT = auto()          # 常规入口静默轮: 等 [draft] 初稿到达 (闸1)
    AWAIT_COLLATION = auto()      # 常规入口对勘表轮: 等对勘表核校完成信号 (闸2)
    AWAIT_GRADING = auto()        # 需 LLM 产分级报告 + 登记待裁项
    AWAIT_ADJUDICATION = auto()   # 需用户逐条裁断 (填 resolved_choice)
    AWAIT_RECITE = auto()         # 需复诵固定 (recited=True)
    AWAIT_FINAL_CONFIRM = auto()  # 需用户"确认无误" (final_confirmed=True)
    AWAIT_DELIVERY = auto()       # 需出增量统稿 (终核已放行)
    AWAIT_GATE_REPORT = auto()    # 统稿后门控回报: 列八项客观状态, 只收存疑/未核反馈
    DONE = auto()                 # 流程完成


@dataclass
class StepResult:
    """
    一次 step 的结果。signal 告诉 agent'现在停在哪、需要什么'。
    C(i): as_json() 产结构化信号供无前端 agent 消费。
    """
    signal: StepSignal
    state: State
    detail: str = ""
    # 需 agent 回填时, 点名待办 (如未裁项 idx 列表), 便于 agent 组织下一 turn 的提示
    pending: Optional[list] = None

    def as_json(self) -> dict:
        return {
            "signal": self.signal.name,
            "state": self.state.name,
            "detail": self.detail,
            "pending": list(self.pending) if self.pending else [],
        }


def _pending_adjudications(ctx: Context) -> list:
    return [a.idx for a in ctx.adjudications if a.resolved_choice is None]


def _unrecited(ctx: Context) -> list:
    return [a.idx for a in ctx.adjudications
            if a.resolved_choice is not None and not a.recited]


def step(ctx: Context, handlers: Handlers) -> StepResult:
    """
    推进状态机到下一个'需外部输入'的挂起点, 返回 StepResult; 不越过任何闸门。

    可重入契约:
      - 幂等于挂起点: 若挂起条件仍未满足 (如待裁项仍未裁), 再次 step 返回同一 AWAIT_*,
        且**不重跑**已完成的认知 handler (如 on_grading 只在进入 GRADING 时跑一次)。
      - 全状态在 ctx 内: step 无跨调用内部状态, 故 ctx 落盘-读回后可无缝恢复 (A(i))。
      - agent 主导 (B(ii)): step 只推进+校验+挂起; 用户裁断/确认由 agent 写回 ctx 再调 step。

    典型 turn 序列 (直入):
      step→AWAIT_GRADING → [agent: on_grading 产报告] → step→AWAIT_ADJUDICATION
      → [agent: 呈报告, 下一 turn 收用户裁断写回] → step→AWAIT_RECITE
      → step→AWAIT_FINAL_CONFIRM → [收"确认无误"] → step→AWAIT_DELIVERY
      → [出统稿] → step→DONE
    """
    # 首次进入: 依入口定起始态 (直入过闸1、2 → GRADING)
    if ctx.state in (State.SILENT_INTAKE,) and not ctx.draft_received \
            and ctx.slice.entry == Entry.DIRECT:
        initial_state(ctx)

    # ── 常规入口前两轮编排 (甲: 补齐完整四步节奏) ──
    # §三1轮静默接收 → §三2轮出对勘表 → §三3轮分级(与直入汇合)。
    # 每轮在"需外部输入"处以专用信号挂起, 交回控制权由人工下一 turn 回填。
    if ctx.slice.entry == Entry.NORMAL:
        # 第1轮: 静默接收。收 [draft] 前挂起 (闸1); draft 到达后产四事缓存, 进对勘表轮。
        if ctx.state == State.SILENT_INTAKE:
            if not ctx.draft_received:
                return StepResult(StepSignal.AWAIT_DRAFT, ctx.state,
                                  "§三1轮: 等 [draft] 初稿到达 (早停闸1: 收稿前禁翻译)")
            # draft 已到 → 产静默确认四事缓存 (§三1轮: 节点/声部/风险区/无损自检等)
            handlers.on_silent(ctx)
            transition(ctx, State.COLLATION_TABLE)
            ctx.log("§三1轮完成: 静默四事缓存已产, 进对勘表轮")
        # 第2轮: 出对勘表。产表+附§八音节表后, 等核校完成信号 (闸2) 挂起。
        if ctx.state == State.COLLATION_TABLE:
            if not ctx.collation_confirmed:
                # 出对勘表(含音节对照表)是认知/形式产出, 由 handler 产; 只产一次
                _table_marker = "[step] on_table 已产对勘表"
                if _table_marker not in ctx.audit_log:
                    handlers.on_table(ctx)
                    ctx.log(_table_marker)
                return StepResult(StepSignal.AWAIT_COLLATION, ctx.state,
                                  "§三2轮: 对勘表已出(附音节对照表), 等人工核校完成信号 (闸2)")
            transition(ctx, State.GRADING)
            ctx.log("§三2轮完成: 收到核校完成信号, 进第三轮分级")
    elif ctx.state == State.SILENT_INTAKE:
        # 直入但 initial_state 尚未把态推到 GRADING 的兜底
        initial_state(ctx)

    # ── GRADING: 需分级报告 + 待裁项登记 (只跑一次) ──
    if ctx.state == State.GRADING:
        # 只在'尚无待裁项'时跑一次 on_grading; 恢复后 ctx 已带待裁项 → 不重跑 (可重入)。
        # 注: 若某切片本就无待裁项, on_grading 跑后仍空, 靠 audit_log 标记避免重跑。
        _graded_marker = "[step] on_grading 已执行"
        if not ctx.adjudications and _graded_marker not in ctx.audit_log:
            handlers.on_grading(ctx)
            ctx.log(_graded_marker)
            # 产完报告后, 若有待裁项 → 挂起等人裁 (裁断权属人, 状态机不自代)
        pend = _pending_adjudications(ctx)
        if pend:
            return StepResult(StepSignal.AWAIT_ADJUDICATION, ctx.state,
                              f"分级报告已出; 待裁项 {pend} 需人裁 (§五: 裁断权属人)",
                              pending=pend)
        # 无待裁项或已全裁 → 可进磋商
        transition(ctx, State.CONSULTATION)
        ctx.consultation_done = True

    # ── CONSULTATION 已完成 → 复诵固定 ──
    if ctx.state == State.CONSULTATION:
        # 全部待裁项须已裁才可离开磋商
        pend = _pending_adjudications(ctx)
        if pend:
            return StepResult(StepSignal.AWAIT_ADJUDICATION, ctx.state,
                              f"待裁项 {pend} 尚未裁, 不得离开磋商", pending=pend)
        ctx.consultation_done = True
        transition(ctx, State.ADJUDICATION_RECITE)

    # ── ADJUDICATION_RECITE: 复诵固定 (§七6) ──
    if ctx.state == State.ADJUDICATION_RECITE:
        unrec = _unrecited(ctx)
        if unrec:
            handlers.on_recite(ctx)   # 由 handler 置 recited=True (可能同时收最终确认)
            unrec = _unrecited(ctx)
        if unrec:
            return StepResult(StepSignal.AWAIT_RECITE, ctx.state,
                              f"裁定项 {unrec} 已裁未复诵固定 (§七6)", pending=unrec)
        if not ctx.final_confirmed:
            return StepResult(StepSignal.AWAIT_FINAL_CONFIRM, ctx.state,
                              "复诵固定毕; 待用户最终确认 (§三·丙)")
        transition(ctx, State.FINAL_CONFIRM)

    # ── FINAL_CONFIRM → 出统稿前终核 (闸3 + 八项) ──
    if ctx.state == State.FINAL_CONFIRM:
        if not ctx.final_confirmed:
            return StepResult(StepSignal.AWAIT_FINAL_CONFIRM, ctx.state,
                              "待用户最终确认, 不得出统稿 (闸3)")
        transition(ctx, State.DELIVERY)          # 闸3 在此强制
        # M2: 有数据的确定性门控在此自动据实核验并挂证据, 不靠 handler 手报 PASS。
        # 数据缺省则不自动核 (留待 handler/人工显式登记或豁免), 避免无数据强跑报错。
        if ctx.table_rows and (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS) not in ctx.gate_results:
            record_lossless_coverage(ctx, GateTiming.PRE_DELIVERY)
        if ctx.final_text and (GateTiming.PRE_DELIVERY, GateItem.OUTPUT_CLEAN) not in ctx.gate_results:
            record_output_clean(ctx, GateTiming.PRE_DELIVERY, ctx.final_text)
        if ctx.verse_pairs and (GateTiming.PRE_DELIVERY, GateItem.SYLLABLE_COUNT) not in ctx.gate_results:
            record_syllable_count(ctx, GateTiming.PRE_DELIVERY)
        verify_pre_delivery_complete(ctx)        # §六终核: 八项齐、A级PASS、无存疑
        return StepResult(StepSignal.AWAIT_DELIVERY, ctx.state,
                          "终核放行; 待出增量统稿 (§七5)")

    # ── DELIVERY: 出统稿 → 挂起于门控回报 (甲 A3: §六统稿后回环) ──
    if ctx.state == State.DELIVERY:
        # 终核再断言 (幂等): 防 ctx 从 AWAIT_DELIVERY 落盘-resume 后, 直接进 DELIVERY 块
        # 而跳过 FINAL_CONFIRM→DELIVERY 那一步的终核。出稿前八项必须仍成立。
        if ctx.table_rows and (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS) not in ctx.gate_results:
            record_lossless_coverage(ctx, GateTiming.PRE_DELIVERY)
        if ctx.final_text and (GateTiming.PRE_DELIVERY, GateItem.OUTPUT_CLEAN) not in ctx.gate_results:
            record_output_clean(ctx, GateTiming.PRE_DELIVERY, ctx.final_text)
        if ctx.verse_pairs and (GateTiming.PRE_DELIVERY, GateItem.SYLLABLE_COUNT) not in ctx.gate_results:
            record_syllable_count(ctx, GateTiming.PRE_DELIVERY)
        verify_pre_delivery_complete(ctx)
        handlers.on_delivery(ctx)
        transition(ctx, State.GATE_REPORT)
        # §六统稿后回环: 列八项客观状态(PASS/存疑/未核), 只收存疑/未核反馈,
        # 不设褒位、不阻断交付。此处挂起, 让人工据回报反馈; 下一 step 收讫进 DONE。
        return StepResult(StepSignal.AWAIT_GATE_REPORT, ctx.state,
                          "统稿已出; 门控回报八项客观状态, 请仅就存疑/未核项反馈 (§六回环)")

    # ── GATE_REPORT: 回报已呈, 收讫 → DONE ──
    if ctx.state == State.GATE_REPORT:
        handlers.on_gate_report(ctx)
        transition(ctx, State.DONE)
        ctx.log("流程完成 (step 驱动)")
        return StepResult(StepSignal.DONE, ctx.state, "门控回报受讫, 流程完成")

    if ctx.state == State.DONE:
        return StepResult(StepSignal.DONE, ctx.state, "流程已完成")

    # 不应到达
    return StepResult(StepSignal.DONE, ctx.state, f"未预期态 {ctx.state.name}")
