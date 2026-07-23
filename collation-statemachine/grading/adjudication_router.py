# -*- coding: utf-8 -*-
"""
待裁诀疑路由 —— 六类的确定性分派 + 反模式闸。

规范源: SKILL §五 (待裁六类 + 自校裁量边界)。
甲方案边界: 本模块只做**形式特征路由**与**反模式拦截**, 不做实质判定。
"某项归哪类"依形式信号确定性分派; "某项该判什么/裁什么"仍归 LLM 与人裁。

关键纪律 (§五): "凡当前窗口内可见文本足以自行核实之事项, Agent 须径行自查定案,
不得将可自验之项包装为待裁诀疑上呈" —— 将可验项列为争议属已识别之反模式, 禁绝。
本模块把这条反模式检测编码为确定性闸。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from state_machine.states import AdjudicationType


# ── 候选诀疑项的形式特征 (由上游 LLM/预处理填充, 皆为可观察信号, 非判断) ──

@dataclass
class AdjudicationSignals:
    """
    一个候选诀疑项携带的形式特征。这些是**可观察信号**, 不是认知结论:
    LLM 只需报告"有无引文标记""先例表是否命中"这类事实, 不需做裁断。
    """
    # 引文体裁信号: 有引文闭合词 (ཞེས/ཅེས) 且为偈颂体
    has_quote_marker: bool = False
    is_verse: bool = False
    # 术语信号: 本窗口首遇 且 先例表(§九)/术语清单未命中
    is_first_occurrence: bool = False
    precedent_hit: bool = False           # 先例表或挂载术语清单是否已锁定该词
    # 形近异文/木刻讹字信号
    has_variant_graph_flag: bool = False
    # 嵌入式咒语/种子字信号
    is_mantra_or_seed: bool = False
    # 框架/辖域/断句两可信号
    has_scope_ambiguity_flag: bool = False
    # 密义存疑信号: 字面与义理疑有落差
    has_esoteric_gap_flag: bool = False
    # 自验信号: 窗口内证据是否足以自行核实 (如括注状态已由先例表判定)
    self_verifiable_in_window: bool = False
    # 自验依据描述 (若 self_verifiable_in_window=True, 说明凭何自验)
    self_verify_basis: str = ""


class AntiPatternRejection(ValueError):
    """可自验项被包装成待裁项 —— §五反模式, 拒绝。"""


@dataclass
class RoutedAdjudication:
    atype: AdjudicationType
    signals: AdjudicationSignals
    routing_basis: str          # 分派依据 (可审计)


def check_anti_pattern(signals: AdjudicationSignals) -> None:
    """
    反模式闸 (§五): 窗口内可自验之项, 禁止进待裁段。
    命中即抛 AntiPatternRejection, 迫使上游改为自查定案。

    例外: 术语锁定即便"首遇", 若先例表已命中则属可自验(自动从先例, 不上呈);
    未命中才是真待裁 —— 这条在 route() 里体现。
    """
    if signals.self_verifiable_in_window:
        raise AntiPatternRejection(
            f"§五反模式: 该项窗口内可自验(依据: {signals.self_verify_basis or '未注明'}), "
            f"须径行自查定案, 不得包装为待裁诀疑上呈"
        )


def route(signals: AdjudicationSignals) -> RoutedAdjudication:
    """
    确定性路由: 依形式特征把候选项分派到六类之一。
    先过反模式闸, 再走决策树。分派是形式的, 不含实质判定。

    决策优先级 (从最具体的形式信号到最一般):
    1. 显式旗标优先 (形近异文 / 嵌入式咒语 / 框架辖域 / 密义) —— 这些由上游明确标出
    2. 引文偈成例: 有引文标记 + 偈颂体
    3. 术语锁定: 首遇 且 先例表未命中
    """
    check_anti_pattern(signals)

    # 1. 显式旗标 (上游预处理已侦测到的具体形式信号)
    if signals.has_variant_graph_flag:
        return RoutedAdjudication(
            AdjudicationType.VARIANT_GRAPH, signals,
            "形近异文/木刻讹字旗标置位")
    if signals.is_mantra_or_seed:
        return RoutedAdjudication(
            AdjudicationType.MANTRA_BORDERLINE, signals,
            "嵌入式咒语/种子字信号置位 (§2.3 免校归属存疑)")
    if signals.has_scope_ambiguity_flag:
        return RoutedAdjudication(
            AdjudicationType.SCOPE_AMBIGUITY, signals,
            "框架/辖域/断句两可旗标置位")
    if signals.has_esoteric_gap_flag:
        return RoutedAdjudication(
            AdjudicationType.ESOTERIC_GAP, signals,
            "密义存疑/字面义理落差旗标置位")

    # 2. 引文偈成例 (§五 A级: 成例交人工判定, 不自断)
    if signals.has_quote_marker and signals.is_verse:
        return RoutedAdjudication(
            AdjudicationType.QUOTE_PRECEDENT, signals,
            "引文标记(ཞེས/ཅེས)+偈颂体 → 成例有无交人裁")

    # 3. 术语锁定: 首遇 且 先例表未命中 (命中则可自验, 已被反模式闸/此处拦下)
    if signals.is_first_occurrence and not signals.precedent_hit:
        return RoutedAdjudication(
            AdjudicationType.TERM_LOCK, signals,
            "本窗口首遇且先例表未命中 → 须定译名, 交人裁")

    # 首遇但先例表已命中 = 可自验 (自动从先例), 不应到这
    if signals.is_first_occurrence and signals.precedent_hit:
        raise AntiPatternRejection(
            "§五反模式: 术语首遇但先例表已命中 → 自动从先例, 不上呈")

    raise ValueError(
        "无法路由: 该候选项无任何可识别的诀疑形式信号 "
        "(可能本不该进待裁段, 或上游信号缺失)")
