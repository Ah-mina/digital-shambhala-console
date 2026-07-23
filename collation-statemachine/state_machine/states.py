# -*- coding: utf-8 -*-
"""
对勘工作流状态定义。

规范源: tibetan-chinese-collation/SKILL.md (并存, 不改动原 SKILL)。
粒度 (拍板1=甲): 状态机守轮次纪律、硬停顿、门控闸门; 分级校对/术语裁量等
认知判断留给 LLM 在状态内部做, 不编码进状态机。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class State(Enum):
    """轮次状态集。对应 SKILL §三。"""
    # ── 常规入口 (§三 1、2 轮) ──
    SILENT_INTAKE = auto()       # 静默接收藏文 (§三1轮)
    COLLATION_TABLE = auto()     # 出对勘表 (§三2轮)
    # ── 第三轮 (两入口汇合; 直入模式 §三·甲 从此进入) ──
    GRADING = auto()             # 分级校对报告 A/B/C + 待裁诀疑 (§三·丙, §五)
    CONSULTATION = auto()        # 磋商 (§三·丙)
    ADJUDICATION_RECITE = auto() # 裁定复诵固定 (§七6)
    FINAL_CONFIRM = auto()       # 最终确认
    DELIVERY = auto()            # 增量统稿 (§七5)
    GATE_REPORT = auto()         # 门控自检回报 (§六回环)
    DONE = auto()


class Entry(Enum):
    """入口模式。"""
    NORMAL = auto()   # 常规: 走 1、2、3 轮 (§三·乙)
    DIRECT = auto()   # 直入: 豁免前两轮, 输入即核定 (§三·甲)


class GateStatus(Enum):
    """
    门控三态。对应 SKILL §六回环: 仅记 PASS/存疑/未核, 不附褒贬。
    PASS 须挂物理证据 (§六回环3: 禁止裸 PASS)。
    """
    PASS = auto()          # 须挂可核产物, 否则非法
    SUSPECT = auto()       # 存疑, 如实标, 宁严毋宽
    NOT_CHECKED = auto()   # 未核 (含依约豁免), 须注明豁免依据, 不得以PASS占位


class GateTiming(Enum):
    """三处核验时机。对应 SKILL §六。"""
    ROUND2_INIT = auto()    # 第二轮初核 (直入豁免)
    ROUND3_RECHECK = auto() # 第三轮复核
    PRE_DELIVERY = auto()   # 统稿前终核 (最终一道)


# 八条门控项 id, 对应 SKILL §六清单八条。
class GateItem(Enum):
    NODE_LOSSLESS = "节点序列无损覆盖"
    VOICE_LAYOUT = "声部排版"
    MANTRA_EXEMPT = "咒语免校"
    SYLLABLE_COUNT = "偈颂音节-字数"
    SEGMENTATION_CONSISTENT = "切分与声部一以贯之"
    OUTPUT_CLEAN = "统稿洁净"
    LAYOUT_INCREMENTAL = "排版遵约与增量范围"
    A_LEVEL_FIXED = "A级错误已全部修正"


# 各门控项在哪些时机可核。对应 §六三处分配。
GATE_ITEM_TIMING = {
    GateItem.NODE_LOSSLESS: {GateTiming.ROUND2_INIT, GateTiming.ROUND3_RECHECK, GateTiming.PRE_DELIVERY},
    GateItem.VOICE_LAYOUT: {GateTiming.ROUND2_INIT, GateTiming.ROUND3_RECHECK, GateTiming.PRE_DELIVERY},
    GateItem.MANTRA_EXEMPT: {GateTiming.ROUND2_INIT, GateTiming.ROUND3_RECHECK, GateTiming.PRE_DELIVERY},
    GateItem.SYLLABLE_COUNT: {GateTiming.ROUND3_RECHECK, GateTiming.PRE_DELIVERY},
    GateItem.SEGMENTATION_CONSISTENT: {GateTiming.PRE_DELIVERY},
    GateItem.OUTPUT_CLEAN: {GateTiming.PRE_DELIVERY},
    GateItem.LAYOUT_INCREMENTAL: {GateTiming.PRE_DELIVERY},
    GateItem.A_LEVEL_FIXED: {GateTiming.PRE_DELIVERY},  # 唯磋商结束后成立
}


@dataclass
class GateResult:
    """单个门控项的核验结论。"""
    item: GateItem
    status: GateStatus
    evidence: str = ""          # PASS 必须非空 (物理证据); 否则 verdict 层报错
    exemption_reason: str = ""  # NOT_CHECKED 时若因豁免, 注明依据

    def is_legal(self) -> bool:
        # §六回环3: PASS 无证据即非法 (裸 PASS 禁绝)
        if self.status == GateStatus.PASS:
            return bool(self.evidence.strip())
        return True


# ── 待裁诀疑六类 (§五 收口), 状态机只登记"须人裁", 不替裁 ──
class AdjudicationType(Enum):
    VARIANT_GRAPH = "形近异文/木刻录入讹字取字"
    ESOTERIC_GAP = "密义存疑/字面义理落差"
    TERM_LOCK = "术语锁定(首遇定译名)"
    SCOPE_AMBIGUITY = "框架/辖域/断句两可"
    QUOTE_PRECEDENT = "引文偈成例有无"
    MANTRA_BORDERLINE = "嵌入式咒语/种子字免校归属或对音"


@dataclass
class AdjudicationItem:
    """一条待裁项。状态机登记并强制其被裁, 但不产生裁断。"""
    idx: int
    atype: AdjudicationType
    options: list[str]           # 如 ["A", "B"]
    resolved_choice: Optional[str] = None
    recited: bool = False        # §七6: 是否已复诵固定


@dataclass
class Slice:
    """一个切片的处理上下文。"""
    slice_id: str
    tone_level: int              # §四 语体等级
    entry: Entry
    has_verse: bool = False
    # 直入模式的"输入即核定"仅覆盖原文本; 新拟改句不承袭 (§三·甲2)
    input_ratified: bool = False


@dataclass
class Context:
    """在状态间传递。"""
    slice: Slice
    state: State = State.SILENT_INTAKE
    draft_received: bool = False        # §三1轮早停闸
    collation_confirmed: bool = False   # §三2轮早停闸: 核校完成信号
    consultation_done: bool = False
    final_confirmed: bool = False
    adjudications: list[AdjudicationItem] = field(default_factory=list)
    gate_results: dict[tuple[GateTiming, GateItem], GateResult] = field(default_factory=dict)
    audit_log: list[str] = field(default_factory=list)
    # A/B/C 分级报告条目 (认知层判定, 经 signal 注入)。此处宽松承载: 存下来供呈现;
    # 严格结构契约校验 (validate_all) 另作一步, 暂不在注入时强制 (拍板: 先宽松跑通)。
    # 存为原始 dict 列表, 与 grade_contract.GradedItem 字段对应, 序列化直观。
    graded_items: list = field(default_factory=list)
    # M2: 确定性门控所需的实际数据。table_rows=对勘表行[(藏文,汉译)];
    # final_text=拟出统稿。二者由认知层(人工/handler)填入, 供代码自动核验挂证据,
    # 而非靠 handler 手报 PASS。缺省空 → 相应确定性核验无数据可跑, 须显式登记或豁免。
    table_rows: list[tuple[str, str]] = field(default_factory=list)
    final_text: str = ""
    # 偈颂逐句藏汉对 [(藏句, 汉句), ...]。与 table_rows 粒度不同: 一个节点可含多句偈
    # (如 N05 含4句、N09 含8句)。供 SYLLABLE_COUNT 门控据 §八 脚本自动物理核验。
    verse_pairs: list[tuple[str, str]] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.audit_log.append(msg)

    # ── 序列化 (拍板A(i): 每步整份 ctx 落盘; 跨 turn 存取中途态) ──
    # 纯 additive: 不改任何字段, 只加 to_dict/from_dict。enum 以 .name 存;
    # gate_results 的 (GateTiming,GateItem) 元组键 JSON 不能直接做键, 故存为记录列表。

    def to_dict(self) -> dict:
        return {
            "slice": {
                "slice_id": self.slice.slice_id,
                "tone_level": self.slice.tone_level,
                "entry": self.slice.entry.name,
                "has_verse": self.slice.has_verse,
                "input_ratified": self.slice.input_ratified,
            },
            "state": self.state.name,
            "draft_received": self.draft_received,
            "collation_confirmed": self.collation_confirmed,
            "consultation_done": self.consultation_done,
            "final_confirmed": self.final_confirmed,
            "adjudications": [
                {
                    "idx": a.idx,
                    "atype": a.atype.name,
                    "options": list(a.options),
                    "resolved_choice": a.resolved_choice,
                    "recited": a.recited,
                }
                for a in self.adjudications
            ],
            "gate_results": [
                {
                    "timing": timing.name,
                    "item": item.name,
                    "status": r.status.name,
                    "evidence": r.evidence,
                    "exemption_reason": r.exemption_reason,
                }
                for (timing, item), r in self.gate_results.items()
            ],
            "audit_log": list(self.audit_log),
            # M2 数据字段
            "table_rows": [[t, h] for (t, h) in self.table_rows],
            "final_text": self.final_text,
            "graded_items": [dict(g) for g in self.graded_items],
            "verse_pairs": [[t, h] for (t, h) in self.verse_pairs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Context":
        sl = d["slice"]
        ctx = cls(
            slice=Slice(
                slice_id=sl["slice_id"],
                tone_level=sl["tone_level"],
                entry=Entry[sl["entry"]],
                has_verse=sl.get("has_verse", False),
                input_ratified=sl.get("input_ratified", False),
            ),
            state=State[d["state"]],
            draft_received=d.get("draft_received", False),
            collation_confirmed=d.get("collation_confirmed", False),
            consultation_done=d.get("consultation_done", False),
            final_confirmed=d.get("final_confirmed", False),
        )
        for a in d.get("adjudications", []):
            ctx.adjudications.append(
                AdjudicationItem(
                    idx=a["idx"],
                    atype=AdjudicationType[a["atype"]],
                    options=list(a["options"]),
                    resolved_choice=a.get("resolved_choice"),
                    recited=a.get("recited", False),
                )
            )
        for g in d.get("gate_results", []):
            timing = GateTiming[g["timing"]]
            item = GateItem[g["item"]]
            ctx.gate_results[(timing, item)] = GateResult(
                item=item,
                status=GateStatus[g["status"]],
                evidence=g.get("evidence", ""),
                exemption_reason=g.get("exemption_reason", ""),
            )
        ctx.audit_log = list(d.get("audit_log", []))
        # M2 数据字段: JSON 把元组转成列表, 还原为 (藏,汉) 元组
        ctx.table_rows = [(row[0], row[1]) for row in d.get("table_rows", [])]
        ctx.final_text = d.get("final_text", "")
        ctx.graded_items = [dict(g) for g in d.get("graded_items", [])]
        ctx.verse_pairs = [(r[0], r[1]) for r in d.get("verse_pairs", [])]
        return ctx
