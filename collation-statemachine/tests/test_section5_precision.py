# -*- coding: utf-8 -*-
"""
§五 精度对齐测试 —— 分级校对相关代码逐条对齐 SKILL §五 明文。

本轮补齐三项此前未落地的 §五 明文约束 (皆为**形式可判**者; 认知判断仍留白):

1. **C级明文排除** (§五 C级): 偈颂**字数/节拍**问题依 2.2 上位规则核验,
   核验时机在对勘表人工核校阶段 (直入视为表外已完成), **不**列入第三轮 C 级;
   **逸出句**(汉译从藏、节拍仍守、附排版附注留痕) 与 **偶言句**(标记转人工、
   归校勘存疑, 依待裁第1类) 亦明文**不**列 C 级。

2. **合法 C 级不得误伤**: §五 C 级本就收「偈颂表格结构性未对齐(表格不连续、
   跨列错位)」—— 明文标为「非字数节拍问题」; 另收现代词汇、擅加科判标题、
   引文末句缺句号、括注/顿号体例不一。这些必须照常通过。

3. **形近词侦测不得充作已核项** (§五 A级): 形近异文侦测**属抽查性质,
   不构成系统覆盖**; **门控与自检不得引之为已核项**, 个案循待裁第1类上呈。
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grading.grade_contract import GradedItem, Grade, validate_item, GradeContractError
from gates.gate_checks import (
    record_gate, VariantDetectionAsCoverageError,
)
from state_machine.states import (
    Context, Slice, Entry, GateItem, GateTiming, GateStatus, GateResult,
)


def _c(problem, **kw):
    kw.setdefault("grade", Grade.C)
    kw.setdefault("location", "[N09-6]")
    kw.setdefault("tibetan_collation", "藏文对勘…")
    return GradedItem(problem=problem, **kw)


# ── 1. C级明文排除 ──

@pytest.mark.parametrize("problem,kw", [
    ("偈颂字数不齐, 汉多3字", "字数不"),
    ("偈颂节拍未按 2-2-1 配字", "节拍"),
    ("藏文音节数与汉字数不符", "字数不"),
    ("此句为逸出句, 音节偏离本偈众数", "逸出句"),
    ("偶言句8言, 疑刻本讹字", "偶言句"),
])
def test_c_level_forbidden_topics_rejected(problem, kw):
    """字数/节拍/逸出句/偶言句 —— §五明文不入第三轮C级, 误列即打回。"""
    with pytest.raises(GradeContractError) as ei:
        validate_item(_c(problem))
    assert "C级明文排除" in str(ei.value)


# ── 2. 合法 C 级不得误伤 (边界锁死) ──

@pytest.mark.parametrize("problem", [
    "偈颂表格结构性未对齐, 表格不连续",     # §五明文: 非字数节拍问题, 属合法C级
    "偈颂表格跨列错位",
    "译者擅加科判标题",
    "引文末句缺句号",
    "括注体例不一",
    "并列成分顿号体例不一",
    "「实操」系现代工商业俗语, 偏离 Level2",
])
def test_legitimate_c_level_topics_pass(problem):
    """§五 C 级本就收录之话题, 不得被排除规则误伤。"""
    validate_item(_c(problem, draft_original="初稿原文", recommended_fix="更正后"))


def test_table_misalignment_is_c_level_not_syllable_issue():
    """
    关键边界: 「表格结构性未对齐」是排版问题(合法C级),
    与「字数节拍不齐」(不入C级)必须区分开 —— §五明文「非字数节拍问题」。
    """
    ok = _c("偈颂表格不连续、跨列错位", draft_original="原表", recommended_fix="重排对齐")
    validate_item(ok)                      # 通过
    bad = _c("偈颂字数不齐")
    with pytest.raises(GradeContractError):
        validate_item(bad)                 # 打回


# ── 3. 形近词侦测不得充作门控已核项 ──

def _ctx():
    return Context(slice=Slice(slice_id="v5", tone_level=2, entry=Entry.DIRECT))


@pytest.mark.parametrize("evidence", [
    "已核形近异文, 无讹字",
    "形近词侦测完毕",
    "讹字侦测通过",
    "无形讹",
])
def test_variant_detection_cannot_be_cited_as_gate_coverage(evidence):
    """
    §五: 形近侦测属抽查、不构成系统覆盖, 门控不得引为已核项。
    以形近侦测结果作 PASS 证据者当场拦下。
    """
    ctx = _ctx()
    with pytest.raises(VariantDetectionAsCoverageError) as ei:
        record_gate(ctx, GateTiming.PRE_DELIVERY, GateResult(
            item=GateItem.NODE_LOSSLESS, status=GateStatus.PASS, evidence=evidence))
    assert "抽查" in str(ei.value)


def test_normal_evidence_still_passes():
    """正常物理证据不受影响 (不误伤)。"""
    ctx = _ctx()
    record_gate(ctx, GateTiming.PRE_DELIVERY, GateResult(
        item=GateItem.NODE_LOSSLESS, status=GateStatus.PASS,
        evidence="38节点逐一比对, 无漏译"))
    assert (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS) in ctx.gate_results


def test_variant_finding_may_be_recorded_as_suspect():
    """
    形近个案本身并非不可登记 —— §五要求它循待裁第1类上呈, 而非充作 PASS。
    故以 SUSPECT 登记形近发现是合法的 (只禁以之报 PASS)。
    """
    ctx = _ctx()
    record_gate(ctx, GateTiming.PRE_DELIVERY, GateResult(
        item=GateItem.NODE_LOSSLESS, status=GateStatus.SUSPECT,
        evidence="抽查见形近疑似讹字, 已循待裁第1类上呈"))
    assert ctx.gate_results[
        (GateTiming.PRE_DELIVERY, GateItem.NODE_LOSSLESS)].status == GateStatus.SUSPECT


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
