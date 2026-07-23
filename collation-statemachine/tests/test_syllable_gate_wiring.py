# -*- coding: utf-8 -*-
"""
SYLLABLE_COUNT 接线测试 —— §八 音节脚本接进 step 实运行路径。

背景 (对照实验发现): check_pairs 早已实现且测过, 但**未接进 step 自动核验路径**,
SYLLABLE_COUNT 门控仍靠 handler 手挂 PASS —— 与 M2 之前的处境同类。
本步补 ctx.verse_pairs + record_syllable_count + 接进 step 两处自动核点。

本测试证明:
  1. 全齐偈颂 → 自动 PASS, 挂逐句对照表为物理证据
  2. 不齐句 → 自动 SUSPECT, 且**强制挂 tsheg 逐段证据**(禁裸归因, §八失信防线),
     终核见 SUSPECT 即阻断出稿
  3. 合法逸出句(17/19/21言)不误报为不齐
  4. 无 verse_pairs 时不伪造 PASS, 抛 BareGatePassError
  5. verse_pairs 经 to_dict/from_dict 无损往返
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import (
    Context, Slice, Entry, GateItem, GateTiming, GateStatus,
)
from gates.gate_checks import record_syllable_count, BareGatePassError

# pbx30a N05 真实偈颂 (含合法逸出句 17/19/17/21)
_N05 = [
    ("སྒྲིབ་བྲལ་མཁའ་དབྱིངས་རྩོལ་རྟོག་མཚན་མའི་རྡུལ་གྱིས་གོ་སྐབས་ནམ་ཡང་མི་ཕྱེད་ཀྱང་",
     "离垢虚空虽永不为勤作分别相尘所分割"),
    ("མ་རུངས་གདུལ་དཀའི་ཡུལ་ལ་རང་བཞིན་ཤུགས་ཀྱི་ཐུགས་རྗེས་འབར་བའི་ཕྱག་རྒྱ་རང་ཤར་བ",
     "于难调伏凶恶境中自然大悲威光手印自显现"),
    ("དུས་མཐའི་མེ་ལྕེ་བྱེ་བའི་སྟོབས་ཀྱིས་སྲིད་དང་ཉོན་མོངས་ཚང་ཚིང་ཡུད་ལ་སྲེག",
     "末劫千万火舌威力刹那焚尽生死烦恼林"),
    ("བདུད་འདུལ་ཧེ་རུ་ཀ་དཔལ་སངས་རྒྱས་ཀུན་གྱི་ཕྲིན་ལས་རྫོགས་མཛད་ལྷག་པའི་ལྷ་མཆོག་དེས་སྐྱོངས་ཤིག",
     "降魔吉祥赫鲁迦尊圆满诸佛一切事业胜本尊祈护"),
]
# pbx30a N07-1: 对勘表两层措辞不一致处 —— Layer A 作9字, 藏文8段 → 应判不齐
_N07_1_LAYER_A = ("རྩོད་པའི་དུས་མཐར་ཨུ་དུམྦཱ་ར་ལྟར", "争斗时末犹如优昙华")
_N07_1_LAYER_B = ("རྩོད་པའི་དུས་མཐར་ཨུ་དུམྦཱ་ར་ལྟར", "争斗末世如优昙华")


def _ctx(pairs):
    c = Context(slice=Slice(slice_id="v", tone_level=2, entry=Entry.NORMAL))
    c.verse_pairs = pairs
    return c


def test_aligned_verses_auto_pass_with_evidence():
    """全齐偈颂(含合法逸出17/19/17/21) → PASS, 逸出句不误报。"""
    ctx = _ctx(_N05)
    r = record_syllable_count(ctx, GateTiming.PRE_DELIVERY)
    assert r.status == GateStatus.PASS, f"合法逸出句被误判不齐: {r.evidence}"
    assert r.evidence.strip(), "PASS 必须挂证据 (禁裸 PASS)"
    assert "4句全齐" in r.evidence


def test_misaligned_verse_suspect_with_segment_evidence():
    """
    不齐句 → SUSPECT, 且必挂 tsheg 逐段证据。
    用例取自真实对勘表 pbx30a 句9 (Layer A 措辞9字 vs 藏文8段)。
    §八: 只报哪侧超出+逐段明细, 不裁定该改哪侧 —— 那归人裁。
    """
    ctx = _ctx([_N07_1_LAYER_A])
    r = record_syllable_count(ctx, GateTiming.PRE_DELIVERY)
    assert r.status == GateStatus.SUSPECT
    # 必须点明哪侧超出
    assert "han_surplus" in r.evidence
    # 必须挂逐段物理证据 (禁裸归因)
    assert "逐段" in r.evidence and "tsheg" in r.evidence
    assert "藏8/汉9" in r.evidence


def test_layer_b_wording_is_aligned():
    """同一句 Layer B 措辞(8字)则齐 —— 证明差异源于汉译措辞, 非脚本判错。"""
    ctx = _ctx([_N07_1_LAYER_B])
    r = record_syllable_count(ctx, GateTiming.PRE_DELIVERY)
    assert r.status == GateStatus.PASS


def test_no_verse_pairs_refuses_bare_pass():
    """无偈颂数据 → 不伪造 PASS, 须显式豁免登记 (§六)。"""
    ctx = _ctx([])
    with pytest.raises(BareGatePassError):
        record_syllable_count(ctx, GateTiming.PRE_DELIVERY)


def test_verse_pairs_roundtrip():
    """A(i): verse_pairs 经序列化无损往返, 还原为元组。"""
    ctx = _ctx(_N05)
    revived = Context.from_dict(ctx.to_dict())
    assert revived.verse_pairs == _N05
    assert all(isinstance(p, tuple) for p in revived.verse_pairs)


def test_misaligned_verse_blocks_delivery_via_step():
    """不齐句致 SUSPECT → 终核阻断出稿 (经 step 实运行路径)。"""
    from state_machine.states import State, GateResult
    from state_machine.transitions import initial_state, transition
    from gates.gate_checks import record_gate
    from state_machine import runner as runner_mod

    ctx = Context(slice=Slice(slice_id="v", tone_level=2, entry=Entry.DIRECT))
    ctx.verse_pairs = [_N07_1_LAYER_A]      # 不齐
    ctx.table_rows = [("藏", "汉")]
    ctx.final_text = "统稿"
    initial_state(ctx)
    ctx.log("[step] on_grading 已执行")
    transition(ctx, State.CONSULTATION)
    ctx.consultation_done = True
    transition(ctx, State.ADJUDICATION_RECITE)
    ctx.final_confirmed = True
    transition(ctx, State.FINAL_CONFIRM)
    # 其余六项手挂 PASS; NODE_LOSSLESS/OUTPUT_CLEAN/SYLLABLE_COUNT 由 step 自动核
    for item in GateItem:
        if item in (GateItem.NODE_LOSSLESS, GateItem.OUTPUT_CLEAN,
                    GateItem.SYLLABLE_COUNT):
            continue
        record_gate(ctx, GateTiming.PRE_DELIVERY,
                    GateResult(item=item, status=GateStatus.PASS, evidence="e"))

    with pytest.raises(RuntimeError) as ei:
        runner_mod.step(ctx, runner_mod.Handlers())
    assert "存疑" in str(ei.value) or "SUSPECT" in str(ei.value)
    assert ctx.gate_results[
        (GateTiming.PRE_DELIVERY, GateItem.SYLLABLE_COUNT)].status == GateStatus.SUSPECT


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
