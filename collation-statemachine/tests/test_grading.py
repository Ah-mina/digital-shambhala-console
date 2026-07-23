# -*- coding: utf-8 -*-
"""
grading 层测试 —— 路由 + 契约, 每个测试对应 SKILL §五一条纪律。
运行: cd collation-statemachine && python tests/test_grading.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine.states import AdjudicationType
from grading.adjudication_router import (
    AdjudicationSignals, route, check_anti_pattern, AntiPatternRejection,
)
from grading.grade_contract import (
    Grade, GradedItem, GradingReport, GradeContractError, validate_item,
)


# ── 六类路由 ──

def test_route_quote_precedent():
    s = AdjudicationSignals(has_quote_marker=True, is_verse=True)
    r = route(s)
    assert r.atype == AdjudicationType.QUOTE_PRECEDENT
    print("PASS: 引文标记+偈颂体 → 引文偈成例 (§五)")

def test_route_term_lock():
    s = AdjudicationSignals(is_first_occurrence=True, precedent_hit=False)
    r = route(s)
    assert r.atype == AdjudicationType.TERM_LOCK
    print("PASS: 首遇且先例未命中 → 术语锁定 (§五)")

def test_route_variant_graph():
    s = AdjudicationSignals(has_variant_graph_flag=True)
    r = route(s)
    assert r.atype == AdjudicationType.VARIANT_GRAPH
    print("PASS: 形近异文旗标 → 形近异文取字 (§五)")

def test_route_mantra_borderline():
    s = AdjudicationSignals(is_mantra_or_seed=True)
    r = route(s)
    assert r.atype == AdjudicationType.MANTRA_BORDERLINE
    print("PASS: 嵌入式咒语信号 → 咒语免校归属 (§2.3)")

def test_route_scope_and_esoteric():
    assert route(AdjudicationSignals(has_scope_ambiguity_flag=True)).atype \
        == AdjudicationType.SCOPE_AMBIGUITY
    assert route(AdjudicationSignals(has_esoteric_gap_flag=True)).atype \
        == AdjudicationType.ESOTERIC_GAP
    print("PASS: 框架辖域 / 密义存疑 各正确路由 (§五)")


# ── 反模式闸: 可自验项禁入待裁 (§五 核心纪律) ──

def test_anti_pattern_self_verifiable():
    s = AdjudicationSignals(
        self_verifiable_in_window=True,
        self_verify_basis="经名括注状态已由先例表判定")
    try:
        route(s)
        assert False
    except AntiPatternRejection:
        print("PASS: 可自验项被拒入待裁段 (§五 反模式禁绝)")

def test_anti_pattern_term_precedent_hit():
    # 首遇但先例表已命中 = 自动从先例, 不上呈
    s = AdjudicationSignals(is_first_occurrence=True, precedent_hit=True)
    try:
        route(s)
        assert False
    except AntiPatternRejection:
        print("PASS: 术语首遇但先例已命中 → 自动从先例, 不上呈 (§五)")


# ── A/B/C 结构契约 ──

def test_b_level_requires_fix():
    item = GradedItem(grade=Grade.B, location="P3", problem="生造词汇",
                      tibetan_collation="藏文对勘…", recommended_fix="")
    try:
        validate_item(item)
        assert False
    except GradeContractError:
        print("PASS: B级缺推荐改译被拦 (§五: 不得仅列问题)")

def test_b_level_with_fix_ok():
    item = GradedItem(grade=Grade.B, location="P3", problem="生造词汇",
                      tibetan_collation="藏文对勘…", recommended_fix="改为『饶益』")
    validate_item(item)
    print("PASS: B级附推荐改译合法")

def test_location_must_be_table_ref():
    # 拍板①后: 节点编号禁令归属**统稿洁净**, 校对报告允许直书 [N7] 便于定位。
    # 故本测试改指 for_delivery=True —— 纪律未削弱, 只是指向正确的产物。
    item = GradedItem(grade=Grade.A, location="节点N7", problem="漏译",
                      tibetan_collation="藏…", location_is_table_ref=True)
    validate_item(item)            # 报告模式: 允许
    try:
        validate_item(item, for_delivery=True)
        assert False
    except GradeContractError:
        print("PASS: 统稿位置暴露内部节点编号被拦 (§2.4 洁净纪律)")

def test_a_level_omission_needs_evidence():
    item = GradedItem(grade=Grade.A, location="P5", problem="整节漏译",
                      tibetan_collation="藏…", is_omission=True, omission_evidence="")
    try:
        validate_item(item)
        assert False
    except GradeContractError:
        print("PASS: A级漏译缺节点比对证据被拦 (§五 系统兜底)")


# ── 整份报告校验 ──

def test_report_validate_all():
    rep = GradingReport(items=[
        GradedItem(grade=Grade.A, location="P1", problem="主被动颠倒",
                   tibetan_collation="藏…"),
        GradedItem(grade=Grade.B, location="偈1句2", problem="漏译限定词",
                   tibetan_collation="藏…", recommended_fix="补『唯』"),
        GradedItem(grade=Grade.C, location="P4", problem="现代词汇",
                   tibetan_collation="藏…"),
    ])
    rep.validate_all()
    assert "A=1 B=1 C=1" in rep.summary()
    print("PASS: 合规三级报告整体校验通过")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n全部 {len(tests)} 项 grading 测试通过。")
