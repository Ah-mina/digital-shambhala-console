# -*- coding: utf-8 -*-
"""
分级契约修订测试 —— 依经验回放对齐 (三拍板)。

背景: 拿经验回放(用户认可的理想产出)实撞旧契约, 整份被打回, 暴露三处问题:
  1. 节点编号禁令被错用到**校对报告**上 —— 该禁令约束的是**统稿洁净**(§2.4)。
     报告是给人看的工作文档, 直书 [N07-3] 正便于逐条定位复核。
  2. 规则顺序掩盖真问题: A级漏译缺证据本该被拦, 却因位置检查先抛错而从未跑到。
  3. C级语体条目的说服力在"初稿→更正"对照, 旧契约无初稿字段。

三拍板:
  ① 校对报告允许节点编号; 统稿仍禁 → validate_item(for_delivery=...)
  ② 藏文对勘一律必填 (含C级) —— 维持现状, 语体修订亦须指向源句
  ③ 加 draft_original 字段; C级既出更正须并列初稿, 使对照完整
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grading.grade_contract import (
    GradedItem, Grade, GradingReport, validate_item, GradeContractError,
)


# ── 拍板①: 报告允许节点编号, 统稿禁 ──

def test_report_allows_internal_node_number():
    """校对报告条目直书 [N07-3] 应通过 (经验回放实际形态)。"""
    it = GradedItem(grade=Grade.A, location="[N07-3]",
                    problem="藏文误录为 བདུད་ལྡན(魔), 系 བདུན(七) 形近讹字",
                    tibetan_collation="བཀའ་བབས་བདུད་ལྡན")
    validate_item(it)                      # 缺省=报告模式, 不应抛错
    validate_item(it, for_delivery=False)


def test_delivery_still_forbids_internal_node_number():
    """同一条目进统稿则被 §2.4 拦下 —— 禁令仍在, 只是指向正确的产物。"""
    it = GradedItem(grade=Grade.A, location="[N07-3]",
                    problem="x", tibetan_collation="y")
    with pytest.raises(GradeContractError) as ei:
        validate_item(it, for_delivery=True)
    assert "统稿" in str(ei.value) and "节点编号" in str(ei.value)


def test_delivery_accepts_table_reference():
    """换算为对勘表编号后, 统稿模式放行。"""
    it = GradedItem(grade=Grade.A, location="句11", problem="x", tibetan_collation="y")
    validate_item(it, for_delivery=True)


# ── 规则顺序修复: 漏译证据检查真正生效 ──

def test_omission_without_evidence_now_caught_in_report():
    """
    A级漏译缺证据, 在**报告模式**下即被拦 (旧实现因位置检查先抛错而从未跑到)。
    §五: 漏译系统兜底, 非肉眼 —— 必挂节点比对证据。
    """
    it = GradedItem(grade=Grade.A, location="[N12]",
                    problem="初稿漏译关键法相 བསྐྱེད་པ(生起次第)",
                    tibetan_collation="དེ་ལ་ཐོག་མར་བསྐྱེད་པ་མ་ཧཱ་ཡོ་གའང",
                    is_omission=True, omission_evidence="")
    with pytest.raises(GradeContractError) as ei:
        validate_item(it)
    assert "漏译" in str(ei.value)


def test_omission_with_evidence_passes():
    it = GradedItem(grade=Grade.A, location="[N12]", problem="漏译 བསྐྱེད་པ",
                    tibetan_collation="དེ་ལ་ཐོག་མར་བསྐྱེད་པ",
                    is_omission=True,
                    omission_evidence="N12节点比对: 藏含 བསྐྱེད་པ, 汉无对应")
    validate_item(it)


# ── 拍板②: 藏文对勘一律必填, 含 C 级 ──

def test_c_level_still_requires_tibetan_collation():
    """C级(语体)亦须附藏文对勘 —— 维持现状, 迫使语体修订指向源句。"""
    it = GradedItem(grade=Grade.C, location="[N09-6]",
                    problem="「实操」系现代工商业俗语",
                    tibetan_collation="",
                    draft_original="续部义教授修持实操",
                    recommended_fix="续部义教授履践法")
    with pytest.raises(GradeContractError) as ei:
        validate_item(it)
    assert "藏文原文对勘" in str(ei.value)


# ── 拍板③: C级"初稿→更正"对照须完整 ──

def test_c_level_fix_requires_draft_original():
    """C级既出更正却无初稿原文 → 打回 (对照不全, 读者无从复核)。"""
    it = GradedItem(grade=Grade.C, location="[N09-6]", problem="实操系现代俗语",
                    tibetan_collation="རྒྱུད་དོན་མན་ངག",
                    recommended_fix="续部义教授履践法")   # 无 draft_original
    with pytest.raises(GradeContractError) as ei:
        validate_item(it)
    assert "初稿原文" in str(ei.value)


def test_c_level_full_pair_passes():
    """初稿+更正+藏文齐备 → 通过 (经验回放 C1 的合规形态)。"""
    it = GradedItem(grade=Grade.C, location="[N09-6]",
                    problem="「实操」系现代工商业俗语, 偏离 Level2 疏钞体",
                    tibetan_collation="རྒྱུད་དོན་མན་ངག་ལག་ལེན་དང་བཅས་པ",
                    draft_original="续部义教授修持实操",
                    recommended_fix="续部义教授履践法")
    validate_item(it)


def test_c_level_without_fix_needs_no_draft():
    """C级只述问题、未出更正者, 不强求初稿字段。"""
    it = GradedItem(grade=Grade.C, location="[N25]", problem="句式现代口语化",
                    tibetan_collation="འདིར་སྐབས་སུ་བབས་པ")
    validate_item(it)


# ── 整份报告 (经验回放形态) ──

def test_replay_shaped_report_validates_in_report_mode():
    """依经验回放建模的一份 A/B/C 报告, 在报告模式下整份通过。"""
    rpt = GradingReport(items=[
        GradedItem(grade=Grade.A, location="[N07-3]",
                   problem="藏文误录 བདུད་ལྡན(魔), 系 བདུན(七) 形近讹字",
                   tibetan_collation="བཀའ་བབས་བདུད་ལྡན"),
        GradedItem(grade=Grade.A, location="[N12]", problem="漏译 བསྐྱེད་པ",
                   tibetan_collation="དེ་ལ་ཐོག་མར་བསྐྱེད་པ",
                   is_omission=True, omission_evidence="N12比对: 汉无对应"),
        GradedItem(grade=Grade.B, location="[N02]",
                   problem="扩充为「智海无边」, མཐའ་ཡས 无 མཚོ(海) 字",
                   tibetan_collation="བློ་གྲོས་མཐའ་ཡས།",
                   recommended_fix="罗卓泰耶（智无边）著"),
        GradedItem(grade=Grade.C, location="[N09-6]", problem="「实操」现代俗语",
                   tibetan_collation="རྒྱུད་དོན་མན་ངག་ལག་ལེན",
                   draft_original="续部义教授修持实操",
                   recommended_fix="续部义教授履践法"),
    ])
    rpt.validate_all()                                   # 报告模式通过
    assert "A=2" in rpt.summary() and "B=1" in rpt.summary()
    with pytest.raises(GradeContractError):              # 统稿模式则拦节点编号
        rpt.validate_all(for_delivery=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
