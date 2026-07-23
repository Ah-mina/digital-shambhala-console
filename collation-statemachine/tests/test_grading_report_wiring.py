# -*- coding: utf-8 -*-
"""
A/B/C 分级报告接线测试 —— 补 grading 报告的注入通道 (宽松承载, 暂不校验)。

背景 (实机反馈): CLI 此前只承接待裁项登记, A/B/C 分级报告无注入通道 → 报告为空。
本步补 ctx.graded_items + signal 注入 + 输出呈现。拍板: 先宽松跑通, 严格 validate_all 另作。

本测试证明:
  1. graded_items 经注入后存于 ctx, 与待裁项并存不混
  2. 新字段经 to_dict/from_dict 无损往返 (A(i))
  3. 宽松承载: 即便条目结构不全(如 B 级缺改译)也不在注入时抛错 (校验另做)
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import Context, Slice, Entry


def test_graded_items_roundtrip():
    """A(i): graded_items 经 to_dict/from_dict 无损往返。"""
    ctx = Context(slice=Slice(slice_id="g", tone_level=2, entry=Entry.DIRECT))
    ctx.graded_items = [
        {"grade": "A", "location": "N22", "problem": "误增因字",
         "tibetan_collation": "རྒྱུ་མཐུན་པ", "recommended_fix": "具足等流之法相"},
        {"grade": "C", "location": "P12", "problem": "现代语感"},
    ]
    revived = Context.from_dict(ctx.to_dict())
    assert len(revived.graded_items) == 2
    assert revived.graded_items[0]["grade"] == "A"
    assert revived.graded_items[0]["recommended_fix"] == "具足等流之法相"
    assert revived.graded_items[1]["location"] == "P12"


def test_graded_items_and_adjudications_coexist():
    """分级报告与待裁项并存不混 (报告=agent自判, 待裁=上呈人裁)。"""
    from state_machine.states import AdjudicationItem, AdjudicationType
    ctx = Context(slice=Slice(slice_id="g", tone_level=2, entry=Entry.DIRECT))
    ctx.graded_items = [{"grade": "B", "location": "P3", "problem": "扩充",
                         "tibetan_collation": "x", "recommended_fix": "改译y"}]
    ctx.adjudications.append(
        AdjudicationItem(idx=1, atype=AdjudicationType.TERM_LOCK, options=["A", "B"]))
    revived = Context.from_dict(ctx.to_dict())
    assert len(revived.graded_items) == 1
    assert len(revived.adjudications) == 1
    assert revived.graded_items[0]["grade"] == "B"
    assert revived.adjudications[0].atype == AdjudicationType.TERM_LOCK


def test_loose_carry_does_not_validate_on_inject():
    """
    ctx.graded_items 字段本身是**纯承载**, 不自校验 —— 校验发生在**注入边界**
    (run_agent._apply_signal 调 GradingReport.validate_all), 而非 dataclass 层。
    故直接给 ctx 赋值不会抛错; 但经 CLI --signal 注入的违规报告会被打回且不落盘。
    分层理由: ctx 是状态容器, 契约是入口守卫, 二者职责分开。
    """
    ctx = Context(slice=Slice(slice_id="g", tone_level=2, entry=Entry.DIRECT))
    # B 级缺 recommended_fix, 严格契约会拦, 但宽松承载阶段只是存下
    ctx.graded_items = [{"grade": "B", "location": "P1", "problem": "x",
                         "tibetan_collation": "y"}]  # 无 recommended_fix
    revived = Context.from_dict(ctx.to_dict())
    assert revived.graded_items[0]["grade"] == "B"
    assert "recommended_fix" not in revived.graded_items[0]  # 未强制补全


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
