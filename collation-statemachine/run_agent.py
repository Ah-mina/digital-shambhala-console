#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_agent.py —— 无前端 agent 状态机入口 (拍板 A(i)/B(ii)/C(i))。

定位:
  把 collation-statemachine 落地到编程 agent 界面 (无前端)。agent 通过命令行 +
  结构化 JSON 驱动可重入 step: 每次读 ctx.json、置入本 turn 的用户信号、调一次 step、
  回写 ctx.json、打印一个 JSON StepResult 告诉 agent'现在停在哪、需要什么输入'。

三拍板落地:
  A(i) 每步整份 ctx 落盘: --ctx 指向 ctx.json; init/step 后都整份 to_dict() 写回。
  B(ii) agent 主导: 本入口不驱动对话; 它只在收到 agent 递来的用户信号后推进一步、
        由状态机校验合法性 (硬停顿/门控在 step 内经不变的 transition 强制) 并挂起。
  C(i) 结构化 JSON: --signal 收 JSON, stdout 出 JSON StepResult。机器友好、可测试。

用法:
  # 起一个直入切片, 建 ctx.json
  python run_agent.py init --ctx ctx.json --slice-id pbx30a --tone 2 --entry DIRECT

  # 推进一步 (无信号): 返回下一个 AWAIT_*
  python run_agent.py step --ctx ctx.json

  # 带信号推进: 本 turn 用户裁断 / 最终确认 (JSON)
  python run_agent.py step --ctx ctx.json --signal '{"adjudications":{"1":"A"}}'
  python run_agent.py step --ctx ctx.json --signal '{"final_confirm":true}'

信号 schema (C(i)):
  {
    "draft": true,                       # 常规入口: [draft] 到达 → 置 draft_received
    "collation_confirmed": true,         # 常规入口: 对勘表核校完成
    "adjudications": {"1":"A","2":"B"},  # 待裁项 idx → 裁断选项 (裁断权属人)
    "recite": [1,2],                     # 复诵固定这些 idx (缺省=全部已裁项)
    "final_confirm": true,               # 用户"确认无误"
    "grading": [                         # (可选) 直接注入分级产出的待裁项登记
      {"idx":1,"atype":"TERM_LOCK","options":["A","B"]}
    ]
  }

注意: 本入口只做'消费信号 → 置位 ctx → step'。真正的**认知产出** (分级报告、拟改句)
  由 agent 的 LLM 在调用本入口前完成, 并经 --signal 的 grading 字段或注入 handler 传入。
  状态机不产认知内容 (甲方案边界)。
"""
from __future__ import annotations

import argparse
import json
import sys

from state_machine.states import (
    Context, Slice, Entry, AdjudicationItem, AdjudicationType,
)
from state_machine.runner import step, Handlers, StepResult
from grading.grade_contract import GradingReport, GradeContractError


def _load_ctx(path: str) -> Context:
    with open(path, "r", encoding="utf-8") as f:
        return Context.from_dict(json.load(f))


def _save_ctx(path: str, ctx: Context) -> None:
    # A(i): 每步整份 ctx 落盘
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ctx.to_dict(), f, ensure_ascii=False, indent=2)


def _emit(result: StepResult, ctx: Context) -> int:
    """C(i): stdout 出结构化 JSON。附最小 ctx 摘要便于 agent 组织下一 turn。"""
    out = {
        "result": result.as_json(),
        "ctx_summary": {
            "state": ctx.state.name,
            "entry": ctx.slice.entry.name,
            "adjudications": [
                {"idx": a.idx, "atype": a.atype.name,
                 "options": a.options, "resolved": a.resolved_choice,
                 "recited": a.recited}
                for a in ctx.adjudications
            ],
            "final_confirmed": ctx.final_confirmed,
            "graded_items": ctx.graded_items,
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_init(args) -> int:
    ctx = Context(slice=Slice(
        slice_id=args.slice_id,
        tone_level=args.tone,
        entry=Entry[args.entry],
    ))
    _save_ctx(args.ctx, ctx)
    print(json.dumps({
        "ok": True,
        "detail": f"已建 ctx: 切片 {args.slice_id}, 入口 {args.entry}",
        "next": "调 step 推进 (直入将挂起于 AWAIT_ADJUDICATION 或据切片而定)",
    }, ensure_ascii=False, indent=2))
    return 0


def _apply_signal(ctx: Context, sig: dict) -> None:
    """B(ii): 把 agent 递来的用户信号写进 ctx。只置位, 不做认知判断。"""
    if sig.get("draft"):
        ctx.draft_received = True
    if sig.get("collation_confirmed"):
        ctx.collation_confirmed = True
    # M2 数据注入: 对勘表行 / 拟出统稿正文 (供出稿前自动核无损覆盖、洁净)
    if sig.get("table_rows") is not None:
        ctx.table_rows = [(r[0], r[1]) for r in sig["table_rows"]]
        ctx.log(f"[signal] 注入对勘表 {len(ctx.table_rows)} 行")
    if sig.get("final_text") is not None:
        ctx.final_text = sig["final_text"]
        ctx.log("[signal] 注入统稿正文")
    if sig.get("verse_pairs") is not None:
        ctx.verse_pairs = [(r[0], r[1]) for r in sig["verse_pairs"]]
        ctx.log(f"[signal] 注入偈颂 {len(ctx.verse_pairs)} 句 (供音节自动核)")
    # 分级产出注入 (agent 的 LLM 已产报告, 此处仅登记待裁项)
    for g in sig.get("grading", []) or []:
        ctx.adjudications.append(AdjudicationItem(
            idx=g["idx"],
            atype=AdjudicationType[g["atype"]],
            options=list(g.get("options", [])),
        ))
        ctx.log(f"[signal] 登记待裁项 {g['idx']} ({g['atype']})")
    # A/B/C 分级报告条目注入 (认知层判定; 宽松承载, 暂不 validate_all —— 拍板: 先跑通)
    if sig.get("graded_items") is not None:
        # 注入即校验 (报告模式): 结构违规当场打回, 不留到出稿才炸。
        # 报告模式 → 允许 [N…] 式节点定位 (§三·甲4 对勘表自带编号径行沿用);
        # 统稿洁净另由出稿前 for_delivery=True 一道把关。
        report = GradingReport.from_dicts(list(sig["graded_items"]))
        report.validate_all()                      # 违规抛 GradeContractError
        ctx.graded_items = list(sig["graded_items"])
        _n = {"A": 0, "B": 0, "C": 0}
        for it in ctx.graded_items:
            g = it.get("grade", "?")
            if g in _n:
                _n[g] += 1
        ctx.log(f"[signal] 注入分级报告 A={_n['A']} B={_n['B']} C={_n['C']} (结构契约已校验)")
    # 用户裁断 (裁断权属人; 状态机只登记选择)
    for idx_str, choice in (sig.get("adjudications") or {}).items():
        idx = int(idx_str)
        for a in ctx.adjudications:
            if a.idx == idx:
                a.resolved_choice = choice
                ctx.log(f"[signal] 人裁: {idx}{choice}")
    # 复诵固定 (§七6)
    recite = sig.get("recite")
    targets = ctx.adjudications if recite is None else \
        [a for a in ctx.adjudications if a.idx in recite]
    if sig.get("recite") is not None or sig.get("_recite_all"):
        for a in targets:
            if a.resolved_choice is not None:
                a.recited = True
        ctx.log("[signal] 复诵固定完成")
    if sig.get("final_confirm"):
        ctx.final_confirmed = True
        ctx.log("[signal] 用户最终确认")


def _handlers_from_signal(sig: dict) -> Handlers:
    """
    B(ii): 本入口不产认知内容。on_recite 在收到 recite 信号时置位 (若 agent 未预置)。
    on_grading 留空 —— 分级产出经 --signal 的 grading 字段注入, 不在此产。
    """
    def on_recite(c):
        # 若 signal 已置 recited 则无操作; 否则对已裁项全部复诵固定
        for a in c.adjudications:
            if a.resolved_choice is not None and not a.recited and sig.get("recite_on_step"):
                a.recited = True
    return Handlers(on_recite=on_recite)


def cmd_step(args) -> int:
    ctx = _load_ctx(args.ctx)
    sig = {}
    if args.signal:
        sig = json.loads(args.signal)
    try:
        _apply_signal(ctx, sig)
    except GradeContractError as e:
        # 结构契约打回: **不落盘** —— 违规报告不得写进 ctx, 保持真相源干净。
        print(json.dumps({
            "error": "GradeContractError",
            "detail": str(e),
            "state": ctx.state.name,
            "note": "分级报告结构违规 (§五 契约), 已拒绝注入且未落盘。"
                    "请补全结构后重发 —— 本层只校验结构, 不判分级对错。",
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 5
    handlers = _handlers_from_signal(sig)
    try:
        result = step(ctx, handlers)
    except Exception as e:
        _save_ctx(args.ctx, ctx)   # 出错也落盘, 保留审计
        print(json.dumps({
            "error": type(e).__name__,
            "detail": str(e),
            "state": ctx.state.name,
            "note": "闸门/门控拦截 (B(ii): 状态机仍强制纪律)。修正信号后重试。",
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4
    _save_ctx(args.ctx, ctx)       # A(i): 每步整份落盘
    return _emit(result, ctx)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_agent.py",
                                description="无前端 agent 状态机入口 (A(i)/B(ii)/C(i))")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="建 ctx.json")
    sp.add_argument("--ctx", required=True)
    sp.add_argument("--slice-id", required=True)
    sp.add_argument("--tone", type=int, default=2)
    sp.add_argument("--entry", choices=["DIRECT", "NORMAL"], default="DIRECT")
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser("step", help="推进一步 (可带 --signal JSON)")
    sp.add_argument("--ctx", required=True)
    sp.add_argument("--signal", help="结构化 JSON 信号 (C(i))")
    sp.set_defaults(fn=cmd_step)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
