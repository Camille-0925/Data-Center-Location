Virginia Gate运行模块。Python 3.10+，无需第三方依赖。

输入：power_input_mw（设施总负荷MW）、target_full_power_date（YYYY-MM-DD）。
默认搜索全Virginia，默认新建。输出为各county的三个Gate状态、原因和下一步事项。

从仓库根目录运行：
PYTHONPATH=src python3 -m dc_locator.gates.virginia.gate_runner src/dc_locator/gates/virginia/examples/default_input.json --output outputs/virginia_gate.json --as-of 2026-10-04

Python调用：from dc_locator.gates.virginia.gate_runner import evaluate
Georgia后续在../georgia/中实现相同接口。
