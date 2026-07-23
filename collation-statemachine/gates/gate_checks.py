# -*- coding: utf-8 -*-
"""
门控核验 —— §六清单的可执行化。

规范源: SKILL §六 (三处核验时机, 八项, 三态, 裸PASS禁绝) + §2.4 无损覆盖。
粒度 (拍板1=甲): 确定性可核项 (无损覆盖、漏译、音节) 由代码核; 认知项
(义理、术语) 不在此 —— 状态机只保证"该核的核了、裸PASS被拦、豁免有据"。
"""
from __future__ import annotations

import re

from state_machine.states import (
    Context, GateItem, GateStatus, GateTiming, GateResult,
    GATE_ITEM_TIMING, Entry,
)
from gates.syllable_check import check_pairs, attribute_misalignment


class BareGatePassError(RuntimeError):
    """报 PASS 却无物理证据。对应 §六回环3 裸PASS禁绝。"""


class VariantDetectionAsCoverageError(RuntimeError):
    """以形近词侦测充作门控已核项。对应 §五「抽查性质, 不构成系统覆盖」。"""


# 形近词侦测之标志性措辞: 出现于 PASS 证据中即视为以抽查充覆盖 (§五)
_VARIANT_DETECTION_MARKERS = ("形近", "异文侦测", "讹字侦测", "形讹")


# ── 统稿洁净检测 (§六 OUTPUT_CLEAN, §七5 洁净定义) ──
# 洁净所禁者: ①节点编号 ②声部之名 ③操作批注 —— 皆内部痕迹, 纯形式可判。
# §七5明确: 洁净禁的是内部痕迹, 非藏汉对勘表格本身, 故检测须不误伤表格与正文普通词。

_CLEAN_NODE_ID = re.compile(r'\[N-?\d+\]|偈\d+句\d+|(?<![A-Za-z0-9])P\d+(?![A-Za-z0-9])')
# 声部之名仅在"标签位"命中(行首/方括号内/表格列/后接冒号), 正文普通词不命中
_CLEAN_VOICE = re.compile(r'(?:^|[|【（(\s])(原颂|论主|引文)(?:[】：:）)|\s]|$)', re.MULTILINE)
# 操作批注: 括注内含内部作业词(批注/门控/核验/待裁/PASS/漏译/节点/校对)
_CLEAN_ANNOTATION = re.compile(
    r'（[^）]*?(?:批注|门控|核验|待裁|PASS|漏译|节点|校对)[^）]*?）'
    r'|【[^】]*?(?:批注|门控|校对)[^】]*?】'
)


def output_clean_check(final_text: str) -> tuple[bool, str]:
    """
    §六终核 OUTPUT_CLEAN 的确定性检测器。
    抓三类内部痕迹; 返回 (洁净?, 证据)。证据点名抓到什么, 供门控挂据 (非裸判)。
    甲方案边界: 只判形式痕迹在不在, 不判统稿义理/排版优劣 (那是认知, 归 LLM/人)。
    """
    found = []
    nodes = _CLEAN_NODE_ID.findall(final_text)
    if nodes:
        found.append(f"节点编号 {sorted(set(nodes))}")
    voices = _CLEAN_VOICE.findall(final_text)
    if voices:
        found.append(f"声部之名 {sorted(set(voices))}")
    annos = _CLEAN_ANNOTATION.findall(final_text)
    if annos:
        found.append(f"操作批注 {annos}")
    if found:
        return False, "[洁净FAIL] 统稿含内部痕迹: " + "; ".join(found)
    return True, "[洁净PASS] 未检出节点编号/声部之名/操作批注 (§七5: 表格本身非违禁)"


def lossless_coverage_check(node_tibetan_texts: list[str], original_input: str) -> tuple[bool, str]:
    """
    §2.4.2 无损覆盖自检: 所有节点藏文拼接后须 100% 等同原始输入。
    这是确定性核验, 返回 (通过?, 可挂证据)。
    直入模式无独立底本时, 改以"对勘表行序列完整+逐行有对应汉译"为替代证据
    (§六清单首项), 该替代核验见 lossless_coverage_check_direct。
    """
    joined = "".join(node_tibetan_texts)
    def norm(s: str) -> str:
        return "".join(s.split())
    ok = norm(joined) == norm(original_input)
    if ok:
        return True, f"[无损覆盖] {len(node_tibetan_texts)}节点拼接==原始输入(去空白比对通过)"
    return False, f"[无损覆盖] FAIL: 拼接长度{len(norm(joined))} vs 原始{len(norm(original_input))}"


def lossless_coverage_check_direct(table_rows: list[tuple[str, str]]) -> tuple[bool, str]:
    """
    直入模式替代证据 (§六清单首项): 对勘表行序列完整 + 逐行有对应汉译。
    row = (藏文, 汉译)。汉译空者即一处待查漏译。
    """
    missing = [i for i, (_, h) in enumerate(table_rows, 1) if not h.strip()]
    if missing:
        return False, f"[无损覆盖·直入] FAIL: 行 {missing} 无对应汉译(疑漏译)"
    return True, f"[无损覆盖·直入] {len(table_rows)}行序列完整, 逐行有汉译"


def missing_translation_check(table_rows: list[tuple[str, str]]) -> tuple[bool, str, list[int]]:
    """
    §五 漏译核验 (系统性兜底): 逐节点比对有无对应汉译。
    确定性, 非肉眼。返回 (无漏译?, 证据, 漏译行号)。
    """
    missing = [i for i, (_, h) in enumerate(table_rows, 1) if not h.strip()]
    if missing:
        return False, f"[漏译核验] 发现 {len(missing)} 处漏译: 行 {missing}", missing
    return True, f"[漏译核验] {len(table_rows)}节点逐一比对, 无漏译", []


def record_gate(ctx: Context, timing: GateTiming, result: GateResult) -> None:
    """
    登记一项门控结论。裸 PASS 当场拦截 (§六回环3)。
    并校验该项在此 timing 确实可核 (§六三处分配)。
    """
    if not result.is_legal():
        raise BareGatePassError(
            f"裸PASS禁绝(§六回环3): {result.item.value} 报 PASS 但无物理证据"
        )
    # §五: 形近词侦测**属抽查性质, 不构成系统覆盖**; 门控与自检**不得引之为已核项**。
    # 故以形近异文侦测结果作为某项 PASS 之证据者, 当场拦下 —— 所获个案应循
    # 「待裁难点与诀疑」第1类(形近异文取字)上呈人裁, 而非充作覆盖性核验通过。
    if result.status == GateStatus.PASS:
        for kw in _VARIANT_DETECTION_MARKERS:
            if kw in (result.evidence or ""):
                raise VariantDetectionAsCoverageError(
                    f"{result.item.value} 以形近词侦测(「{kw}」)充作已核项: "
                    f"§五明定形近侦测属抽查、不构成系统覆盖, 不得引为门控已核。"
                    f"个案请循待裁第1类上呈人裁"
                )
    if timing not in GATE_ITEM_TIMING[result.item]:
        ctx.log(f"[警告] {result.item.value} 不应在 {timing.name} 核验(§六时机不符)")
    ctx.gate_results[(timing, result.item)] = result
    tag = result.status.name
    ev = result.evidence or result.exemption_reason
    ctx.log(f"门控[{timing.name}] {result.item.value}: {tag} — {ev}")


def record_output_clean(ctx: Context, timing: GateTiming, final_text: str) -> GateResult:
    """
    用检测器自动产出 OUTPUT_CLEAN 门控证据, 而非 handler 手挂 PASS。
    洁净 → PASS 挂检测证据; 不洁净 → SUSPECT 挂点名证据 (终核见 SUSPECT 即阻断出稿)。
    这堵住"手挂PASS但统稿实际带[N-x]"的路径 —— 洁净是纯形式, 不该靠自觉。
    """
    ok, ev = output_clean_check(final_text)
    result = GateResult(
        item=GateItem.OUTPUT_CLEAN,
        status=GateStatus.PASS if ok else GateStatus.SUSPECT,
        evidence=ev,
    )
    record_gate(ctx, timing, result)
    return result


def record_lossless_coverage(ctx: Context, timing: GateTiming) -> GateResult:
    """
    M2: 用确定性核验自动产出 NODE_LOSSLESS 门控证据, 而非 handler 手挂 PASS。

    从 ctx.table_rows 跑 lossless_coverage_check_direct + missing_translation_check:
      - 行序列完整且逐行有汉译 → PASS 挂"N行完整+无漏译"证据
      - 有空汉译行(疑漏译) → SUSPECT 挂点名证据 (终核见 SUSPECT 即阻断出稿)
    无 table_rows 数据 → 不伪造 PASS: 抛错要求先填数据或显式豁免登记
      (对齐 §六"不得报无凭 PASS, 亦不以未核占位自陷")。

    这把 §二.4/§五 的无损覆盖与漏译从"靠 handler 自觉报 PASS"变为"代码据实自动核"。
    """
    if not ctx.table_rows:
        raise BareGatePassError(
            "NODE_LOSSLESS 无 table_rows 数据可核: 不得裸 PASS。"
            "请先填 ctx.table_rows, 或显式以 NOT_CHECKED+豁免依据登记 (§六)"
        )
    ok_cov, ev_cov = lossless_coverage_check_direct(ctx.table_rows)
    ok_miss, ev_miss, missing = missing_translation_check(ctx.table_rows)
    ok = ok_cov and ok_miss
    result = GateResult(
        item=GateItem.NODE_LOSSLESS,
        status=GateStatus.PASS if ok else GateStatus.SUSPECT,
        evidence=f"{ev_cov} | {ev_miss}",
    )
    record_gate(ctx, timing, result)
    return result


def record_syllable_count(ctx: Context, timing: GateTiming) -> GateResult:
    """
    据 §八 脚本自动核验偈颂音节-字数, 产出 SYLLABLE_COUNT 门控证据, 而非手挂 PASS。

    从 ctx.verse_pairs 跑 check_pairs:
      - 全句齐 → PASS, 挂逐句对照表为物理证据
      - 有不齐句 → SUSPECT, 且**每条不齐句强制挂 attribute_misalignment 的逐段证据**
        (§八: "未数即归咎底本属严重失信" —— 只报哪侧超出+逐段明细, 不裁定该改哪侧)
    无 verse_pairs → 抛错, 不伪造 PASS。散文切片无偈颂者, 应显式以 NOT_CHECKED+
      豁免依据登记 (§六: 不以 PASS 占位, 亦不以未核自陷)。

    注意分寸: 本函数只报数与归因侧, **绝不**判定"合法逸出"还是"该修" —— 那归人裁。
    """
    if not ctx.verse_pairs:
        raise BareGatePassError(
            "SYLLABLE_COUNT 无 verse_pairs 数据可核: 不得裸 PASS。"
            "请填 ctx.verse_pairs; 若本切片无偈颂, 请以 NOT_CHECKED+豁免依据显式登记 (§六)"
        )
    report = check_pairs(ctx.verse_pairs)
    if report.all_aligned:
        result = GateResult(
            item=GateItem.SYLLABLE_COUNT,
            status=GateStatus.PASS,
            evidence=f"[音节核验] {report.total}句全齐 | {report.as_evidence()}",
        )
    else:
        # 每条不齐句强制挂逐段物理证据 (禁裸归因)
        details = []
        for row in report.misaligned:
            attr = attribute_misalignment(row)
            details.append(
                f"句{row.idx}: 藏{row.tib_count}/汉{row.han_count} "
                f"({attr.side}) 证据={attr.evidence}"
            )
        result = GateResult(
            item=GateItem.SYLLABLE_COUNT,
            status=GateStatus.SUSPECT,
            evidence=(f"[音节核验] {report.total}句中 {len(report.misaligned)} 句不齐, "
                      f"已挂逐段证据待人裁: " + " ; ".join(details)),
        )
    record_gate(ctx, timing, result)
    return result


def verify_pre_delivery_complete(ctx: Context) -> None:
    """
    统稿前终核 (§六最后一道): 八项须全部有 PRE_DELIVERY 结论,
    且 A级全修 必须 PASS (唯磋商结束后成立)。
    存疑项存在则不得出稿。
    """
    for item in GateItem:
        key = (GateTiming.PRE_DELIVERY, item)
        if key not in ctx.gate_results:
            raise RuntimeError(f"统稿前终核缺项: {item.value} 未核 (§六终核须全项)")
    # A 级全修必须 PASS
    a_fixed = ctx.gate_results[(GateTiming.PRE_DELIVERY, GateItem.A_LEVEL_FIXED)]
    if a_fixed.status != GateStatus.PASS:
        raise RuntimeError(f"A级错误未全修, 不得出稿: {a_fixed.status.name} (§六)")
    # 任何 SUSPECT 阻断
    suspects = [k[1].value for k, r in ctx.gate_results.items()
                if k[0] == GateTiming.PRE_DELIVERY and r.status == GateStatus.SUSPECT]
    if suspects:
        raise RuntimeError(f"终核存疑项阻断出稿: {suspects} (§六: 任一未通过须先修正)")
    ctx.log("统稿前终核: 八项齐备, A级全修PASS, 无存疑 → 放行")
