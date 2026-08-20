"""dev 长跑压测脚本：产生 N 行日志（跨 5 阶段 + 显式 stage 标记）+ concert/llm
汇总块，用于压测虚拟滚动 / 断线重连回放 / 取消杀树 / 摘要解析。

用法：python mock_longrun.py <lines> <delay>
真实 step1_concert_only 不打印逐条进度，故用此 mock 验证日志底座。"""
from __future__ import annotations

import random
import sys
import time

random.seed(42)  # 确定性输出，便于断言


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.005
    stages = ["列表页采集", "详情页采集", "过滤", "合并去重", "写入 Excel"]

    print("🎤 正在采集演唱会信息...")
    sys.stdout.flush()

    per_stage = max(1, n // len(stages))
    for si, stage in enumerate(stages):
        print(f"▶ stage:{si}")
        sys.stdout.flush()
        for i in range(per_stage):
            r = random.random()
            if r < 0.03:
                print(f"  ❌ stage={stage} 模拟错误 line {i}")
            elif r < 0.10:
                print(f"  ⚠️ stage={stage} 模拟告警 line {i}（样本）")
            elif r < 0.45:
                print(f"  ✓ stage={stage} 抽取成功 line {i}")
            else:
                print(f"  stage={stage} info line {i}：正在处理详情页 {i}/{per_stage}")
            sys.stdout.flush()
            if i % 20 == 0 and delay > 0:
                time.sleep(delay)

    # concert 汇总块（照 _print_concert_report 格式）
    final = max(0, per_stage - 6)
    print("\n🎤 [Concert] 采集回显")
    print(f"  列表页分段：{max(1, n // 200)} 段（成功 {max(1, n // 200)} / 失败 0） | 列表条目 {per_stage}")
    print(f"  详情页：{per_stage} 条（成功 {per_stage - 3} / 失败 2 / 无表格 1）")
    print(f"  过滤：关键词 5 / 已采集 3 / 非北京 2 / 场地小 1")
    print(f"  最终：{final} 条演唱会")

    # llm 用量块（照 print_usage_summary 格式）
    calls = max(1, n // 100)
    prompt_tok = n * 10
    comp_tok = n * 5
    print("\n📊 LLM 用量统计")
    print(
        f"  DeepSeek 主（直连）：{calls} 次调用 | prompt {prompt_tok} + completion {comp_tok} = {prompt_tok + comp_tok} tok"
    )
    print(f"  合计：{calls} 次调用 | {prompt_tok + comp_tok} tok")

    print("\n✅ 完成！Excel 文件已保存至: mock/output.xlsx")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
