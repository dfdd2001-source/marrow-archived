#!/usr/bin/env python3
"""Marrow harness 盲测评测 CLI。

单次盲测（Agnes，新加坡免费网关，当前默认实验 harness）：
  python3 harness/run_eval.py --harness openai --list-models \
      --base-url https://api.agnes-ai.com/api/v1 --api-key-env AGNES_API_KEY
  python3 harness/run_eval.py --harness openai \
      --base-url https://api.agnes-ai.com/api/v1 --api-key-env AGNES_API_KEY \
      --model <模型名> --source harness/sources/ladr-5a.txt \
      --section "第5章 5A节：不变子空间" --page-range "PDF第126-133页" \
      --section-id ladr-5a --baseline cores/ladr-5a.json \
      --related-core-ids ladr-3a-3c,ladr-5b

多次采样择优（生产推荐：采样方差是提取质量的主要风险，N 次提取后按
"gate > 机器验证通过数 > 平均召回 > 案例数"自动选优，逐次落盘，全部留档）：
  ... 同上 ... --samples 3

两段式（第一段清点编号清单，第二段带清单提取，压算法漏提）：
  ... 同上 ... --two-stage

离线复评已有 JSON（不调 API，评测器自测/历史产物复评）：
  python3 harness/run_eval.py --harness file --from-file cores/ladr-5a.json \
      --section-id ladr-5a --baseline cores/ladr-5a.json

退出码：最优运行的 gate 通过为 0，否则 1。
产物：harness/results/<harness>/<section-id>/<时间戳>/（N>1 时含 run-i/ 与 best/）。
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)                          # harness 模块
sys.path.insert(0, os.path.join(ROOT, "backend"))  # run_validation / validation.verifiers

from evaluate import build_scorecard, to_markdown  # noqa: E402

DEFAULT_BOOK = "Marrow 演示内容"


def parse_args():
    p = argparse.ArgumentParser(description="Marrow harness 盲测评测")
    p.add_argument("--harness", required=True, choices=["openai", "deepseek", "file"])
    p.add_argument("--section-id", default=None, help="结果目录名，如 ladr-5a（--list-models 时可省）")
    p.add_argument("--baseline", help="人工校验基线 core JSON，提供则做召回对比")
    p.add_argument("--source", help="章节原文 txt 路径（提取模式必填）")
    p.add_argument("--book", default=DEFAULT_BOOK)
    p.add_argument("--section", help="节名，如 '第5章 5A节：不变子空间'")
    p.add_argument("--page-range", default="")
    p.add_argument("--model", help="模型名（openai 模式必填）")
    p.add_argument("--from-file", help="file 模式：已有提取 JSON 路径")
    p.add_argument("--related-core-ids", default="",
                   help="逗号分隔的 core id，注入 prompt 供 related_cores 引用")
    p.add_argument("--base-url", help="openai 模式：网关 base URL（Agnes 用 $AGNES_BASE_URL）")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY",
                   help="openai 模式：API key 的环境变量名（Agnes 用 AGNES_API_KEY）")
    p.add_argument("--list-models", action="store_true",
                   help="openai 模式：列出网关可用模型后退出，用于确认模型名")
    p.add_argument("--samples", type=int, default=1,
                   help="采样次数（>1 时自动择优，file 模式忽略）")
    p.add_argument("--max-tokens", type=int, default=None,
                   help="openai 模式：显式 max_tokens（推理模型+网关默认4096上限时需调大，如 32768）")
    p.add_argument("--temperature", type=float, default=0.1,
                   help="openai 模式：采样温度")
    p.add_argument("--two-stage", action="store_true",
                   help="openai 模式：两段式提取（第一段清点编号清单，第二段带清单提取），压算法漏提")
    p.add_argument("--select-by", default="verify", choices=["verify", "coverage", "balanced"],
                   help="择优标准：verify=机器验证优先（默认）；coverage=覆盖优先；balanced=综合")
    p.add_argument("--solve-practice", action="store_true",
                   help="生成-检验：对 practice 案例提议候选答案并用注册表机器检验，PASS 才写 candidate_answer")
    return p.parse_args()


def _selection_key(scorecard, mode="verify"):
    """择优标准（三档），gate 永远第一优先：
    - verify:    机器验证净通过 > 平均召回 > 案例数（默认；适合"算对最重要"）
    - coverage:  平均召回+清单落地率 > 机器验证（适合"覆盖全最重要"）
    - balanced:  机器验证净通过 + 10×(召回+落地率) 综合"""
    gate = 1 if scorecard["gate_pass"] else 0
    mc = scorecard["machine_checks"]
    mc_net = mc["pass"] - 2 * (mc["fail"] + mc["error"])
    cmp_ = scorecard.get("baseline_comparison") or {}
    recalls = [c["recall"] for c in cmp_.values() if c.get("recall") is not None]
    avg_recall = round(sum(recalls) / len(recalls), 4) if recalls else 0.0
    landing = (scorecard.get("inventory_coverage") or {}).get("rate") or 0.0
    n_cases = 0
    if cmp_ and "cases" in cmp_:
        n_cases = cmp_["cases"]["found"] + len(cmp_["cases"]["extra"])
    if mode == "verify":
        return (gate, mc_net, avg_recall, n_cases)
    if mode == "coverage":
        return (gate, round(avg_recall + landing, 4), mc_net, n_cases)
    # 三种模式统一为四元组，元数不一致会让跨模式比较/日志处理产生隐性歧义
    return (gate, round(mc_net + 10 * (avg_recall + landing), 3), mc_net, n_cases)


def _run_line(i, scorecard, usage):
    mc = scorecard["machine_checks"]
    cmp_ = scorecard.get("baseline_comparison")
    rec = ""
    if cmp_:
        rec = " recall=" + "/".join(
            ("%.0f%%" % (100 * c["recall"])) if c.get("recall") is not None else "n/a"
            for c in (cmp_["dictionary"], cmp_["algorithms"], cmp_["cases"]))
    ic = scorecard.get("inventory_coverage")
    land = f" 落地率={format(ic['rate'], '.0%')}" if ic else ""
    tok = f" tokens={usage.get('total_tokens')}" if usage else ""
    return (f"run {i}: gate={'PASS' if scorecard['gate_pass'] else 'FAIL'} "
            f"机器验证={mc['pass']}P/{mc['fail']}F/{mc['error']}E/{mc['skip']}S{rec}{land}{tok}")


def main():
    args = parse_args()
    if not args.list_models and not args.section_id:
        sys.exit("需要 --section-id（--list-models 时可省）")
    with open(os.path.join(ROOT, "docs", "marrow-core-schema-v1.json"), encoding="utf-8") as f:
        schema_json = f.read()

    related = [x.strip() for x in args.related_core_ids.split(",") if x.strip()]
    section_meta = {"book": args.book, "section": args.section, "page_range": args.page_range}
    baseline = None
    if args.baseline:
        with open(args.baseline, encoding="utf-8") as f:
            baseline = json.load(f)

    # ---- 结果目录提前建好：逐次落盘，采样中途崩溃不丢已完成的提取 ----
    # （--list-models 模式无 section-id，不建目录、提前退出）
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (os.path.join(ROOT, "harness", "results", args.harness, args.section_id, stamp)
               if args.section_id else None)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    def _save_run(d, core, run_meta, raw, scorecard):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "core.json"), "w", encoding="utf-8") as f:
            json.dump(core, f, ensure_ascii=False, indent=2)
        with open(os.path.join(d, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump(run_meta, f, ensure_ascii=False, indent=2)
        if raw:
            with open(os.path.join(d, "raw_response.json"), "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
        with open(os.path.join(d, "scorecard.json"), "w", encoding="utf-8") as f:
            json.dump(scorecard, f, ensure_ascii=False, indent=2)
        with open(os.path.join(d, "scorecard.md"), "w", encoding="utf-8") as f:
            f.write(to_markdown(scorecard, run_meta))

    # ---- 提取（可能多次采样，逐次落盘） ----
    samples = 1 if args.harness == "file" else max(1, args.samples)
    runs = []  # (core, run_meta, raw_response, scorecard)
    if args.harness == "file":
        if not args.from_file:
            sys.exit("file 模式需要 --from-file <提取JSON路径>")
        from base import FileHarness
        harness = FileHarness(args.from_file)
        core = harness.extract(None, None, schema_json)
        run_meta = {"harness": "file", "source_file": args.from_file}
        sc = build_scorecard(core, baseline)
        runs.append((core, run_meta, None, sc))
        _save_run(out_dir, core, run_meta, None, sc)
    else:
        if args.harness == "deepseek":
            if not args.source or not args.section:
                sys.exit("deepseek 模式需要 --source <章节原文txt> 和 --section <节名>")
            with open(args.source, encoding="utf-8") as f:
                source_text = f.read()
            from deepseek import DeepSeekHarness
            harness = DeepSeekHarness(model=args.model or "deepseek-chat",
                                      related_core_ids=related)
            harness_common = {"harness": "deepseek", "model": harness.model}
        else:
            from openai_compat import OpenAICompatHarness
            if not args.base_url:
                sys.exit("openai 模式需要 --base-url（Agnes: $AGNES_BASE_URL）")
            if not args.model and not args.list_models:
                sys.exit("openai 模式需要 --model（先用 --list-models 查看可用模型）")
            harness = OpenAICompatHarness(base_url=args.base_url, model=args.model,
                                          api_key_env=args.api_key_env,
                                          related_core_ids=related,
                                          max_tokens=args.max_tokens,
                                          temperature=args.temperature)
            if args.two_stage:
                from two_stage import TwoStageHarness
                harness = TwoStageHarness(harness)
            harness_common = {"harness": "openai", "base_url": args.base_url,
                              "model": args.model, "two_stage": bool(args.two_stage)}
            if args.list_models:
                print(json.dumps(harness.list_models(), ensure_ascii=False, indent=2))
                sys.exit(0)
            if not args.source or not args.section:
                sys.exit("openai 模式提取需要 --source <章节原文txt> 和 --section <节名>")
            with open(args.source, encoding="utf-8") as f:
                source_text = f.read()

        for i in range(samples):
            core = harness.extract(source_text, section_meta, schema_json)
            run_meta = dict(harness_common, usage=harness.last_usage,
                            section_meta=section_meta, sample=i + 1)
            if args.solve_practice and hasattr(harness, "complete_json"):
                from solve import solve_practice
                core, solve_stats = solve_practice(harness, core, section_meta)
                run_meta["solve_stats"] = solve_stats
            raw = getattr(harness, "raw_response", None)
            inv = (raw or {}).get("stage1_inventory") if raw else None
            sc = build_scorecard(core, baseline, inventory=inv)
            runs.append((core, run_meta, raw, sc))
            _save_run(out_dir if samples == 1 else os.path.join(out_dir, f"run-{i + 1}"),
                      core, run_meta, raw, sc)
            print(_run_line(i + 1, sc, harness.last_usage), flush=True)

    keys = [_selection_key(r[3], args.select_by) for r in runs]
    best_idx = max(range(len(runs)), key=lambda i: keys[i])

    if samples > 1:
        best_dir = os.path.join(out_dir, "best")
        core, run_meta, raw, sc = runs[best_idx]
        _save_run(best_dir, core, run_meta, raw, sc)
        lines = [f"# {args.section_id} — {len(runs)} 次采样，择优 run {best_idx + 1}", ""]
        for i, r in enumerate(runs):
            mark = "  ← 选优" if i == best_idx else ""
            lines.append(f"- {_run_line(i + 1, r[3], r[1].get('usage'))}{mark}")
        with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"→ 选优 run {best_idx + 1}\n", flush=True)

    print(to_markdown(runs[best_idx][3], runs[best_idx][1]))
    print(f"结果目录: {out_dir}")
    sys.exit(0 if runs[best_idx][3]["gate_pass"] else 1)


if __name__ == "__main__":
    main()
