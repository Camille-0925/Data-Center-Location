Georgia Gate运行模块。Python 3.10+，无需第三方依赖，运行无需联网。

与Virginia使用相同用户输入及输出字段，搜索Georgia全州159个county。
输入：power_input_mw（设施总负荷MW）、target_full_power_date（YYYY-MM-DD）。
默认新建数据中心。

从仓库根目录运行：
PYTHONPATH=src python3 -m dc_locator.gates.georgia.gate_runner src/dc_locator/gates/georgia/examples/default_input.json --output outputs/georgia_gate.json --as-of 2026-10-04
可加 --csv outputs/georgia_gate.csv 导出表格。输出目录需要先存在。

Python调用：
from dc_locator.gates.georgia.gate_runner import evaluate
result = evaluate({"power_input_mw":100,"target_full_power_date":"2029-12-31"})

规则：供电资料缺失时，使用同供电公司250km内最多3个county的规模参考，距离衰减长度75km，需求比较容差25%。
供电时间采用Georgia历史工程时间参考；Permitting缺本地资料时归入未察觉明显风险，保留适用中的限制。
数据来源与内部规则保留在data及engine中，公共输出不显示推算方法标签。

默认示例（评估日2026-10-04）：
Power availability：155个未察觉明显风险，4个资料不足。
Time-to-power：159个未察觉明显风险。
Permitting / zoning：158个未察觉明显风险，1个历史资料显示有风险。

供电规模参考不是新增项目剩余可用容量；筛查状态不代表具体地点已经取得供电或审批承诺。
