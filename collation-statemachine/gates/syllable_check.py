# -*- coding: utf-8 -*-
"""
偈颂藏汉音节-字数物理核验器。

来源: tibetan-chinese-collation/SKILL.md §八 (原样复用, 已通过 8/8 回归)。
本文件不重写核验逻辑, 只为状态机加一层薄封装 (check_pairs 返回结构化结果,
供 gates 判定使用, 不再走 sys.exit)。

纪律 (SKILL §八): 只报数、不下结论、不拦稿。差值非零之修订、逸出句裁定、
偶言转人工, 皆归人裁。脚本所报之数与人工核定记录相抵时, 并列两数上呈人裁,
不默认任何一方 (§三·甲.2 仲裁规则)。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


# ── 以下 tib_syl / han_len 原样取自 SKILL §八, 一字未改 ──

def tib_syl(s):
    # 物理数藏文音节：按 tsheg(་) 切分，末组（句末 shad ། 前无 tsheg）亦计一音节
    # 先滤除 ༈ ༆ 等头符/装饰符（U+0F00–0F17）、shad 类标点与空格，仅保留藏文字母与 tsheg，
    # 防头符并入首音节致误计；每一藏文音节必含至少一基字（Lo），故过滤不失音节
    s = "".join(c for c in s if c == "\u0f0b" or unicodedata.category(c) == "Lo")
    return len([p for p in s.strip("\u0f0b").split("\u0f0b") if p])


def han_len(s):
    # 物理数汉字：数 CJK 表意文字（含基本区与扩展区），标点/空格/西文不计
    # 「解脱」「本智」等双字法相一律数为二字，非一拍一字
    return len([c for c in s if unicodedata.category(c).startswith('Lo')
                and ('\u3400' <= c <= '\u9fff'
                     or '\U00020000' <= c <= '\U0002EBEF')])


# ── 薄封装: 结构化结果, 不走 sys.exit, 不下结论 ──

def tib_segments(s):
    """
    返回 tsheg 逐段明细 (与 tib_syl 同口径的过滤, 但保留每段以供人裁复核)。
    tib_syl 只给总数; 本函数给出可追溯的段序列, 使"不齐落在哪一侧"必须挂证据。
    不改动 tib_syl (§八原逻辑一字不改), 仅并列提供明细。
    """
    s = "".join(c for c in s if c == "\u0f0b" or unicodedata.category(c) == "Lo")
    return [p for p in s.strip("\u0f0b").split("\u0f0b") if p]


@dataclass
class SyllableRow:
    idx: int
    tib_count: int
    han_count: int
    aligned: bool
    han_text: str
    tib_segments: list = None      # tsheg 逐段明细, 供归因复核 (甲方案)

    @property
    def diff(self) -> int:
        return self.han_count - self.tib_count


@dataclass
class Attribution:
    """
    不齐归因结论。side 三值; evidence 必须非空 (禁止裸归因)。
    本类不裁定"该改哪侧"(那是人裁), 只强制归因挂物理证据 (§八失信防线)。
    """
    side: str          # "han_surplus" | "tib_surplus" | "indeterminate"
    evidence: str      # 逐段物理证据, 空则归因非法


def attribute_misalignment(row: "SyllableRow") -> "Attribution":
    """
    §八纪律可执行化: "未数即归咎底本属严重失信"。
    给定一个不齐 (或对齐) 的 SyllableRow, 依物理计数判定差值落在哪一侧,
    并强制附逐段证据。系统据此杜绝"笼统归咎藏侧"而不挂证据的失信路径。

    判定纯物理: 汉字数 > tsheg段数 → han_surplus (汉侧配字超出);
                tsheg段数 > 汉字数 → tib_surplus; 相等 → indeterminate。
    注意: 本函数不判断该差是否"合法逸出句"或"当改" —— 归人裁 (§2.2)。
    """
    segs = row.tib_segments if row.tib_segments is not None else tib_segments("")
    d = row.han_count - len(segs)
    ev = (f"[归因·逐段] tsheg{len(segs)}段={'|'.join(segs)} ; "
          f"汉{row.han_count}字={row.han_text} ; 差{d:+d}")
    if d > 0:
        side = "han_surplus"
    elif d < 0:
        side = "tib_surplus"
    else:
        side = "indeterminate"
    return Attribution(side=side, evidence=ev)


@dataclass
class SyllableReport:
    rows: list[SyllableRow]
    total: int

    @property
    def misaligned(self) -> list[SyllableRow]:
        return [r for r in self.rows if not r.aligned]

    @property
    def all_aligned(self) -> bool:
        return len(self.misaligned) == 0

    def as_evidence(self) -> str:
        """产出可挂为门控物理证据的对照表 (§六回环3: 禁止裸 PASS)。"""
        if self.all_aligned:
            return f"[音节对照] 全 {self.total} 句藏汉音节-字数对齐。"
        lines = [f"[音节对照] 共 {self.total} 句, {len(self.misaligned)} 句不齐 (供人裁):"]
        lines.append(f"{'句':>3} {'藏':>3} {'汉':>3} {'差':>4}  汉译")
        for r in self.misaligned:
            lines.append(f"{r.idx:>3} {r.tib_count:>3} {r.han_count:>3} {r.diff:>+4}  {r.han_text}")
        return "\n".join(lines)


def check_pairs(pairs: list[tuple[str, str]]) -> SyllableReport:
    """
    pairs = [(藏文句, 汉译句), ...]。返回结构化报告。
    不拦稿、不裁定 —— 调用方 (gates) 据此产出证据或升级人裁。
    """
    rows = []
    for i, (t, h) in enumerate(pairs, 1):
        ts, hl = tib_syl(t), han_len(h)
        segs = tib_segments(t)
        rows.append(SyllableRow(idx=i, tib_count=ts, han_count=hl,
                                aligned=(ts == hl), han_text=h,
                                tib_segments=segs))
    return SyllableReport(rows=rows, total=len(pairs))
