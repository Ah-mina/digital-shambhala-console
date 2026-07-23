# -*- coding: utf-8 -*-
"""
分级报告注入边界校验测试 —— validate_all 接进实运行路径。

背景: 此前 graded_items 经 --signal 注入是**宽松承载**(存下不校验), §五 契约
在实运行里形同虚设。本步把 GradingReport.validate_all() 接到注入边界:
  - 注入即校验 (报告模式), 结构违规当场打回
  - **违规不落盘** —— 脏报告不得写进 ctx, 保持真相源干净
  - 报告模式允许 [N…] 式定位 (§三·甲4); 统稿洁净另由 for_delivery=True 把关

分层: ctx.graded_items 是状态容器(纯承载), 契约是入口守卫。二者职责分开。
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grading.grade_contract import GradingReport, GradeContractError, Grade


# ── from_dicts 转换 ──

def test_from_dicts_builds_report():
    rpt = GradingReport.from_dicts([
        {"grade": "A", "location": "[N07-3]", "problem": "形近讹字",
         "tibetan_collation": "བཀའ་བབས་བདུད་ལྡན"},
        {"grade": "B", "location": "[N02]", "problem": "诠释性扩充",
         "tibetan_collation": "བློ་གྲོས་མཐའ་ཡས།", "recommended_fix": "智无边"},
    ])
    rpt.validate_all()
    assert len(rpt.items) == 2
    assert rpt.by_grade(Grade.A)[0].location == "[N07-3]"


def test_from_dicts_rejects_bad_grade():
    with pytest.raises(GradeContractError) as ei:
        GradingReport.from_dicts([{"grade": "D", "location": "x", "problem": "y",
                                   "tibetan_collation": "z"}])
    assert "A/B/C" in str(ei.value)


# ── 四类结构违规在注入边界被打回 ──

@pytest.mark.parametrize("raw,expect", [
    # B级缺推荐改译
    ([{"grade": "B", "location": "[N02]", "problem": "扩充",
       "tibetan_collation": "藏"}], "推荐改译"),
    # C级误列字数问题 (§五明文排除)
    ([{"grade": "C", "location": "[N05]", "problem": "偈颂字数不齐",
       "tibetan_collation": "藏"}], "C级明文排除"),
    # C级出更正却无初稿对照
    ([{"grade": "C", "location": "[N09-6]", "problem": "实操系俗语",
       "tibetan_collation": "藏", "recommended_fix": "履践法"}], "初稿原文"),
    # A级漏译无证据
    ([{"grade": "A", "location": "[N12]", "problem": "漏译",
       "tibetan_collation": "藏", "is_omission": True}], "漏译"),
    # 缺藏文对勘
    ([{"grade": "A", "location": "[N12]", "problem": "误译",
       "tibetan_collation": ""}], "藏文原文对勘"),
])
def test_violations_rejected_at_injection(raw, expect):
    rpt = GradingReport.from_dicts(raw)
    with pytest.raises(GradeContractError) as ei:
        rpt.validate_all()
    assert expect in str(ei.value)
    assert "条目1" in str(ei.value), "须点明是第几条, 便于定位修正"


# ── 合规报告 (经验回放形态) 通过 ──

def test_replay_shaped_report_passes_injection():
    """依经验回放建模: A漏译带证据 / B带改译 / C带初稿对照 —— 整份通过。"""
    rpt = GradingReport.from_dicts([
        {"grade": "A", "location": "[N07-3]",
         "problem": "藏文误录 བདུད་ལྡན(魔), 系 བདུན(七) 形近讹字",
         "tibetan_collation": "བཀའ་བབས་བདུད་ལྡན"},
        {"grade": "A", "location": "[N12]", "problem": "漏译 བསྐྱེད་པ(生起次第)",
         "tibetan_collation": "དེ་ལ་ཐོག་མར་བསྐྱེད་པ",
         "is_omission": True,
         "omission_evidence": "N12节点比对: 藏含 བསྐྱེད་པ, 汉无对应"},
        {"grade": "B", "location": "[N02]", "problem": "扩充为「智海无边」",
         "tibetan_collation": "བློ་གྲོས་མཐའ་ཡས།",
         "recommended_fix": "罗卓泰耶（智无边）著"},
        {"grade": "C", "location": "[N09-6]", "problem": "「实操」系现代工商业俗语",
         "tibetan_collation": "རྒྱུད་དོན་མན་ངག་ལག་ལེན",
         "draft_original": "续部义教授修持实操",
         "recommended_fix": "续部义教授履践法"},
    ])
    rpt.validate_all()                       # 报告模式: 通过
    assert "A=2" in rpt.summary()
    with pytest.raises(GradeContractError):  # 统稿模式: 节点编号被拦
        rpt.validate_all(for_delivery=True)


# ── CLI 注入边界: 违规不落盘 ──

def test_cli_rejects_and_does_not_persist(tmp_path):
    """
    经 run_agent._apply_signal 注入违规报告 → 抛 GradeContractError,
    且 ctx.graded_items 保持为空 (脏报告不得写进真相源)。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "run_agent", os.path.join(root, "run_agent.py"))
    ra = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ra)

    from state_machine.states import Context, Slice, Entry
    ctx = Context(slice=Slice(slice_id="x", tone_level=2, entry=Entry.DIRECT))
    bad = {"graded_items": [{"grade": "B", "location": "[N02]",
                             "problem": "扩充", "tibetan_collation": "藏"}]}
    with pytest.raises(GradeContractError):
        ra._apply_signal(ctx, bad)
    assert ctx.graded_items == [], "违规报告不得落进 ctx"


def test_cli_accepts_valid_report():
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "run_agent2", os.path.join(root, "run_agent.py"))
    ra = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ra)

    from state_machine.states import Context, Slice, Entry
    ctx = Context(slice=Slice(slice_id="x", tone_level=2, entry=Entry.DIRECT))
    good = {"graded_items": [{"grade": "B", "location": "[N02]", "problem": "扩充",
                              "tibetan_collation": "藏", "recommended_fix": "智无边"}]}
    ra._apply_signal(ctx, good)
    assert len(ctx.graded_items) == 1
    assert any("结构契约已校验" in l for l in ctx.audit_log)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
