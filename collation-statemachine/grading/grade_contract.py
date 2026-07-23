# -*- coding: utf-8 -*-
"""
A/B/C 分级条目的结构契约校验。

规范源: SKILL §五 (条目格式 + 各级规范)。
甲方案边界: 只校验 LLM 产出的条目**结构是否合规**, 不判定"这是不是A级""分级对不对"。
分级的实质判定归 LLM; 本模块确保其输出满足 §五 的格式契约, 不合规则打回。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class Grade(Enum):
    A = "A"   # 义理性错误 (必须修订)
    B = "B"   # 须修订 (须附推荐改译)
    C = "C"   # 语体/格式


class GradeContractError(ValueError):
    """条目结构违反 §五 契约。"""


@dataclass
class GradedItem:
    """
    一条分级校对条目。字段对应 §五 "位置—问题—藏文原文对勘与说明[—推荐改译]"。
    grade/problem 等内容由 LLM 判定填充; 本模块只校验结构完整性。
    """
    grade: Grade
    location: str                 # 位置 (须为对勘表编号, 非内部节点编号)
    problem: str                  # 问题描述
    tibetan_collation: str        # 藏文原文对勘与说明
    recommended_fix: str = ""     # B级必附; A/C 视情形
    # C级(及需要时) 的"初稿原文", 与 recommended_fix 构成"初稿→更正"对照。
    # 语体类问题的说服力来自这组对照, 故单列字段而非塞进 problem。
    draft_original: str = ""
    # A级漏译专用: 必挂节点比对证据 (§五 漏译系统兜底)
    is_omission: bool = False
    omission_evidence: str = ""
    # 位置标注是否已从内部节点编号换算为对勘表编号 (§五)
    location_is_table_ref: bool = True


# 位置标注禁止直接暴露内部节点编号的形式标记 (§2.4, §五)
_INTERNAL_NODE_PREFIXES = ("节点", "[N", "N#")

# §五 C级**明文排除**之话题 (误列即打回, 并指明正确通道)。
# 注意与**合法** C 级的区分: §五 C 级本就收「偈颂表格结构性未对齐(表格不连续、
# 跨列错位)」—— 那是排版结构问题, 明文标为「非字数节拍问题」, 故不在本表内。
# 本表只拦"字数/节拍/逸出/偶言"这四类依 2.2 与 §八 另有通道者。
_C_LEVEL_FORBIDDEN_TOPICS = (
    ("节拍", "偈颂节拍依 2.2 上位规则, 核验时机在对勘表核校阶段, 不入第三轮C级"),
    ("字数不", "偈颂字数依 2.2 与 §八 脚本核验, 不入第三轮C级"),
    ("音节数", "偈颂音节依 §八 脚本物理核验, 不入第三轮C级"),
    ("逸出句", "逸出句汉译从藏、节拍仍守, 附排版附注留痕, 明文不列C级"),
    ("偶言句", "偶言句标记转人工, 归校勘存疑(待裁第1类), 明文不列C级"),
)


def validate_item(item: GradedItem, *, for_delivery: bool = False) -> None:
    """
    校验单条目的 §五 结构契约。不合规抛 GradeContractError。

    for_delivery 语义 (拍板①):
      False (缺省) = 这是**校对报告**条目 —— 报告是给人看的工作文档,
        位置标注允许直书内部节点编号 (如 [N07-3]), 便于逐条定位复核。
      True = 这是要进**统稿**的内容 —— §2.4 统稿洁净总纪律生效,
        位置标注不得暴露内部节点编号, 须换算为对勘表编号。

    即: 节点编号禁令约束的是**统稿洁净**, 不是校对报告。原实现把这条规则
    错用到报告上, 会把合规的分级报告整份打回 (经验回放实测)。
    """
    if not item.location.strip():
        raise GradeContractError(f"{item.grade.value}级条目缺位置标注 (§五)")
    if not item.problem.strip():
        raise GradeContractError(f"{item.grade.value}级条目缺问题描述 (§五)")
    if not item.tibetan_collation.strip():
        raise GradeContractError(f"{item.grade.value}级条目缺藏文原文对勘 (§五)")

    # §2.4 统稿洁净: 仅在内容进入统稿时强制 (拍板①)
    if for_delivery:
        if not item.location_is_table_ref:
            raise GradeContractError(
                f"位置标注未换算为对勘表编号: {item.location} (§五: 内部节点编号不外露)")
        if any(p in item.location for p in _INTERNAL_NODE_PREFIXES):
            raise GradeContractError(
                f"统稿位置标注暴露内部节点编号: {item.location} (§2.4 统稿洁净总纪律)")

    # §五 B级: 每条须附"推荐改译", 不得仅列问题
    if item.grade == Grade.B and not item.recommended_fix.strip():
        raise GradeContractError("B级条目须附推荐改译, 不得仅列问题 (§五)")

    # §五 A级漏译: 系统性兜底, 须挂节点比对证据
    if item.grade == Grade.A and item.is_omission and not item.omission_evidence.strip():
        raise GradeContractError(
            "A级漏译须挂节点序列比对证据 (§五 漏译系统兜底, 非肉眼)")

    # C级语体条目: 既出更正, 须并列初稿原文, 使"初稿→更正"对照完整 (拍板③)。
    # 语体判断的说服力全在这组对照上; 只给更正而不示初稿, 读者无从复核。
    if (item.grade == Grade.C and item.recommended_fix.strip()
            and not item.draft_original.strip()):
        raise GradeContractError(
            "C级条目既出更正, 须并列初稿原文以成对照 (语体问题须可复核)")

    # §五 C级明文排除: 偈颂**字数/节拍**问题依 2.2 上位规则核验, 核验时机在
    # 对勘表人工核校阶段 (直入模式视为表外已完成), **不**列入第三轮分级之 C 级。
    # 逸出句(汉译从藏、附排版附注留痕)与偶言句(标记转人工、归校勘存疑, 依待裁第1类)
    # 亦明文**不**列 C 级。此处以形式关键词拦截误列, 迫使改走正确通道。
    if item.grade == Grade.C:
        blob = f"{item.problem} {item.draft_original} {item.recommended_fix}"
        for kw, why in _C_LEVEL_FORBIDDEN_TOPICS:
            if kw in blob:
                raise GradeContractError(
                    f"C级不得列入「{kw}」类问题: {why} (§五 C级明文排除)")


@dataclass
class GradingReport:
    """一份分级报告的结构封装。"""
    items: list[GradedItem] = field(default_factory=list)

    def validate_all(self, *, for_delivery: bool = False) -> None:
        """
        全体条目结构校验; 任一不合规即抛错, 迫使 LLM 补全结构。
        for_delivery=True 时额外强制统稿洁净 (节点编号不外露), 见 validate_item。
        """
        for i, item in enumerate(self.items, 1):
            try:
                validate_item(item, for_delivery=for_delivery)
            except GradeContractError as e:
                raise GradeContractError(f"[条目{i}] {e}")

    def by_grade(self, grade: Grade) -> list[GradedItem]:
        return [it for it in self.items if it.grade == grade]

    @classmethod
    def from_dicts(cls, raw: list[dict]) -> "GradingReport":
        """
        由注入的 dict 列表构造报告 (CLI/handler 共用入口)。
        字段缺失以缺省补; grade 值非法则报错 —— 结构问题即刻暴露, 不留到出稿。
        """
        items = []
        for i, d in enumerate(raw, 1):
            g = str(d.get("grade", "")).strip().upper()
            if g not in ("A", "B", "C"):
                raise GradeContractError(
                    f"[条目{i}] grade 须为 A/B/C 之一, 实得 {d.get('grade')!r}")
            items.append(GradedItem(
                grade=Grade[g],
                location=str(d.get("location", "")),
                problem=str(d.get("problem", "")),
                tibetan_collation=str(d.get("tibetan_collation", "")),
                recommended_fix=str(d.get("recommended_fix", "")),
                draft_original=str(d.get("draft_original", "")),
                is_omission=bool(d.get("is_omission", False)),
                omission_evidence=str(d.get("omission_evidence", "")),
                location_is_table_ref=bool(d.get("location_is_table_ref", True)),
            ))
        return cls(items=items)

    def summary(self) -> str:
        return (f"分级报告结构校验通过: "
                f"A={len(self.by_grade(Grade.A))} "
                f"B={len(self.by_grade(Grade.B))} "
                f"C={len(self.by_grade(Grade.C))}")
