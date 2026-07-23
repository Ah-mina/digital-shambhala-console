# -*- coding: utf-8 -*-
"""
SKILL 纪律测试 —— 每个测试对应 tibetan-chinese-collation/SKILL.md 一条纪律。
代码若漂移出 SKILL, 此处应失败。

运行: cd collation-statemachine && python tests/test_workflow_discipline.py
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import (
    Context, Slice, Entry, State,
    GateItem, GateStatus, GateTiming, GateResult,
    AdjudicationItem, AdjudicationType,
)
from state_machine.transitions import initial_state, transition, IllegalTransition
from state_machine.runner import run, Handlers
from gates.hard_stops import (
    HardStopViolation,
    guard_no_translation_before_draft,
    guard_no_report_before_collation_confirmed,
)
from gates.gate_checks import (
    record_gate, BareGatePassError, lossless_coverage_check,
    missing_translation_check, verify_pre_delivery_complete,
)
from gates.syllable_check import check_pairs, tib_syl, han_len


def _slice(entry=Entry.DIRECT, verse=False):
    return Slice(slice_id="pbx-test", tone_level=2, entry=entry, has_verse=verse)


# ── 硬停顿1: draft 前禁翻译 (§三1轮 最高优先级) ──
def test_hardstop_no_translation_before_draft():
    ctx = Context(slice=_slice(entry=Entry.NORMAL))
    try:
        guard_no_translation_before_draft(ctx, about_to_output_translation=True)
        assert False, "应拦截"
    except HardStopViolation:
        print("PASS: draft前禁任何翻译输出 (§三1轮 最高优先级)")


# ── 硬停顿2: 核校完成前禁分级报告 (§三2轮) ──
def test_hardstop_no_report_before_confirmed():
    ctx = Context(slice=_slice(entry=Entry.NORMAL))
    ctx.draft_received = True
    try:
        guard_no_report_before_collation_confirmed(ctx, about_to_output_report_or_delivery=True)
        assert False
    except HardStopViolation:
        print("PASS: 核校完成信号前禁分级报告/统稿 (§三2轮)")


# ── 硬停顿3: 磋商不可省, 直入亦然 (§三·甲5) ──
def test_hardstop_consultation_mandatory_even_direct():
    ctx = Context(slice=_slice(entry=Entry.DIRECT))
    initial_state(ctx)  # 直入 → GRADING, 过闸1、2
    # 直接试图跳到 DELIVERY (未磋商)
    ctx.state = State.FINAL_CONFIRM
    try:
        transition(ctx, State.DELIVERY)
        assert False, "直入也不能跳过磋商"
    except HardStopViolation:
        print("PASS: 磋商环节不可省, 直入亦不豁免 (§三·甲5)")


# ── 裸 PASS 禁绝 (§六回环3) ──
def test_bare_pass_forbidden():
    ctx = Context(slice=_slice())
    try:
        record_gate(ctx, GateTiming.PRE_DELIVERY,
                    GateResult(item=GateItem.NODE_LOSSLESS, status=GateStatus.PASS, evidence=""))
        assert False
    except BareGatePassError:
        print("PASS: 报PASS无物理证据被拦 (§六回环3 裸PASS禁绝)")


def test_pass_with_evidence_ok():
    ctx = Context(slice=_slice())
    record_gate(ctx, GateTiming.PRE_DELIVERY,
                GateResult(item=GateItem.NODE_LOSSLESS, status=GateStatus.PASS,
                           evidence="[无损覆盖] 41节点拼接==原始输入"))
    print("PASS: 挂物理证据的PASS合法")


# ── 直入模式豁免前两轮 (§三·甲) ──
def test_direct_entry_skips_first_two_rounds():
    ctx = Context(slice=_slice(entry=Entry.DIRECT))
    st = initial_state(ctx)
    assert st == State.GRADING
    assert ctx.draft_received and ctx.collation_confirmed  # 输入即核定过闸
    print("PASS: 直入模式起于GRADING, 输入即核定过闸1、2 (§三·甲)")


# ── 无损覆盖确定性自检 (§2.4.2) ──
def test_lossless_coverage():
    nodes = ["བཅོམ་ལྡན་", "འདས་"]
    ok, ev = lossless_coverage_check(nodes, "བཅོམ་ལྡན་འདས་")
    assert ok
    ok2, _ = lossless_coverage_check(nodes, "བཅོམ་ལྡན་འདས་ཀྱི")  # 多字
    assert not ok2
    print("PASS: 无损覆盖拼接==原始输入 确定性自检 (§2.4.2)")


# ── 漏译核验 (§五 系统兜底) ──
def test_missing_translation():
    rows = [("藏1", "汉1"), ("藏2", ""), ("藏3", "汉3")]
    ok, ev, missing = missing_translation_check(rows)
    assert not ok and missing == [2]
    print("PASS: 漏译核验逐节点比对, 空汉译即漏译 (§五)")


# ── §八音节脚本原样复用且可用 ──
def test_syllable_script_reused():
    # tsheg 切分: 3 音节
    assert tib_syl("བཅོམ་ལྡན་འདས་") == 3
    # CJK 计数: 双字法相数为二字
    assert han_len("本智解脱") == 4
    rep = check_pairs([("བཅོམ་ལྡན་འདས་", "出有坏")])  # 3 vs 3
    assert rep.all_aligned
    print("PASS: §八脚本原样复用, tsheg/CJK物理计数正确")


# ── 红队: 禁止笼统归咎某一侧 (§八纪律: 未数即归咎底本属严重失信) ──
def test_misalignment_must_be_attributable_with_evidence():
    """
    真实盲区回归 (pbx30a 句3): 汉译比藏文 tsheg 多3字, 纯本土词无梵文借词。
    此前 agent 笼统报"不齐落在藏侧、汉译无误", 违反 §八"未数即归咎底本"纪律。
    本测试钉死: 任何不齐句必须暴露 tsheg 逐段明细, 且归因结论必须挂逐段证据,
    无证据的归因不可采信 —— 把"我觉得是藏文的问题"逼成"要么挂段, 要么不许下结论"。
    """
    from gates.syllable_check import attribute_misalignment

    # pbx30a 句3: 藏17 tsheg段 vs 汉20字, 无梵文借词
    t3 = "དུས་མཐའི་མེ་ལྕེ་བྱེ་བའི་སྟོབས་ཀྱིས་སྲིད་དང་ཉོན་མོངས་ཚང་ཚིང་ཡུད་ལ་སྲེག"
    h3 = "劫末千万火焰力须臾焚毁有漏烦恼稠林尽无余"
    rep = check_pairs([(t3, h3)])
    row = rep.rows[0]

    # (1) 逐段明细必须暴露, 供人裁复核, 不得只给一个总数
    assert row.tib_segments is not None
    assert len(row.tib_segments) == 17, f"tsheg段应为17, 实得{len(row.tib_segments)}"

    # (2) 归因必须挂证据; 且据物理计数, 此句差值来自汉侧(+3), 不得归咎藏侧
    attr = attribute_misalignment(row)
    assert attr.side in ("han_surplus", "tib_surplus", "indeterminate")
    assert attr.evidence, "归因结论必须挂逐段物理证据, 禁止裸归因"
    # 句3汉字多于藏段, 物理事实是汉侧超出, 系统不得反向归咎藏侧
    assert attr.side == "han_surplus", (
        f"句3汉20>藏17, 应判 han_surplus(汉侧配字超出), "
        f"不得笼统归咎藏侧; 实判 {attr.side}"
    )
    print("PASS: 不齐句可追溯到侧与段, 无证据归因被拦 (§八失信防线)")


# ── 待裁项未裁不得出稿 (HITL 硬停顿) ──
def test_unresolved_adjudication_blocks_delivery():
    ctx = Context(slice=_slice(entry=Entry.DIRECT))
    initial_state(ctx)
    ctx.adjudications = [
        AdjudicationItem(idx=1, atype=AdjudicationType.TERM_LOCK, options=["A", "B"])
    ]
    ctx.consultation_done = True
    ctx.state = State.FINAL_CONFIRM
    try:
        transition(ctx, State.DELIVERY)
        assert False
    except HardStopViolation:
        print("PASS: 待裁项未经人裁不得出统稿 (HITL 硬停顿)")


# ── 终核缺项/存疑阻断出稿 (§六) ──
def test_pre_delivery_requires_all_items():
    ctx = Context(slice=_slice())
    # 只登记一项 → 终核应报缺项
    record_gate(ctx, GateTiming.PRE_DELIVERY,
                GateResult(item=GateItem.NODE_LOSSLESS, status=GateStatus.PASS,
                           evidence="ev"))
    try:
        verify_pre_delivery_complete(ctx)
        assert False
    except RuntimeError:
        print("PASS: 终核八项须齐, 缺项阻断出稿 (§六)")


# ── 非法转移拦截 (§三 轮次纪律) ──
def test_illegal_transition_blocked():
    ctx = Context(slice=_slice(entry=Entry.NORMAL))
    initial_state(ctx)  # SILENT_INTAKE
    try:
        transition(ctx, State.DELIVERY)  # 跳过所有中间轮
        assert False
    except (IllegalTransition, HardStopViolation):
        print("PASS: 跳轮非法转移被拦 (§三 轮次纪律)")


# ── 红队: 统稿洁净检测器 (§六终核 OUTPUT_CLEAN, §七5洁净定义) ──
def test_output_clean_detects_internal_traces():
    """
    §七5: 洁净所禁者为节点编号、操作批注、声部之名等内部痕迹, 非表格本身。
    此前 OUTPUT_CLEAN 无确定性检测器, 脏统稿(带[N-x]/论主/批注)可溜过终核。
    本测试钉死: 三类内部痕迹必被抓, 且合法藏汉对勘表格零误伤。
    """
    from gates.gate_checks import output_clean_check

    # 脏统稿: 三类违禁物俱全
    dirty = (
        "[N-1] 吉祥金刚普巴根本续片段之释。\n"
        "论主：此处从事业普巴游舞大续部中。\n"
        "偈1句1 离障空界造作分别相尘，（批注：此句已核验PASS）\n"
        "P3 劫末千万火焰力须臾焚毁。"
    )
    ok, ev = output_clean_check(dirty)
    assert not ok, "脏统稿含节点编号/声部名/批注, 洁净检测应判 FAIL"
    # 证据须点名抓到什么, 不得裸判 (与裸PASS禁绝同族)
    assert "N-1" in ev or "节点" in ev
    assert "论主" in ev or "声部" in ev
    assert "批注" in ev

    # 合法统稿: 藏汉对勘表格 —— 洁净所禁非表格本身, 须零误伤
    clean = (
        "| དཔལ་རྡོ་རྗེ་ཕུར་པ | 吉祥金刚普巴 |\n"
        "| སྒྲིབ་བྲལ་མཁའ་དབྱིངས | 离障空界造作分别相尘纵然未曾稍侵入， |\n"
        "劫末千万火焰力须臾焚毁有漏烦恼稠林尽无余。"
    )
    ok2, ev2 = output_clean_check(clean)
    assert ok2, f"合法对勘表格被误判不洁净: {ev2}"

    # 假阳性边界: '引文''论主'作正文普通词不得命中 (仅标签位命中)
    prose = "此引文出自根本续, 论主之意甚明。"
    ok3, _ = output_clean_check(prose)
    assert ok3, "正文中'引文/论主'作普通词, 不应误判为声部标签"
    print("PASS: 统稿洁净检测器抓三类内部痕迹, 表格与正文普通词零误伤")


def test_dirty_output_blocked_at_final_gate():
    """
    集成: 脏统稿经 record_output_clean 自动置 SUSPECT, 终核见 SUSPECT 阻断出稿。
    证明检测器真接进了闸门, 而非孤立函数 —— 手挂PASS但统稿脏的路径被堵死。
    """
    from gates.gate_checks import (
        record_output_clean, record_gate, verify_pre_delivery_complete,
    )
    from state_machine.states import (
        Context, Slice, Entry, GateItem, GateTiming, GateResult, GateStatus,
    )

    ctx = Context(slice=Slice(slice_id="test", tone_level=2, entry=Entry.DIRECT))
    # 先给其余七项挂合法 PASS(带证据), 只留 OUTPUT_CLEAN 走检测器
    for item in GateItem:
        if item == GateItem.OUTPUT_CLEAN:
            continue
        record_gate(ctx, GateTiming.PRE_DELIVERY,
                    GateResult(item=item, status=GateStatus.PASS, evidence=f"[证据]{item.value}"))
    # 脏统稿走检测器 → 应置 SUSPECT
    res = record_output_clean(ctx, GateTiming.PRE_DELIVERY, "[N-1] 论主：正文。")
    assert res.status == GateStatus.SUSPECT
    # 终核应因 SUSPECT 阻断
    try:
        verify_pre_delivery_complete(ctx)
        assert False, "脏统稿竟通过终核"
    except RuntimeError as e:
        assert "存疑" in str(e) or "统稿洁净" in str(e)
    print("PASS: 脏统稿置SUSPECT并被终核阻断 (检测器真接进闸门)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部 {len(tests)} 项 SKILL 纪律测试通过。")
