# 量化指标报告 (MetricsCollector)

## 路由准确度
- activation_accuracy: 100.0%
- precision: 100.0%
- recall: 100.0%
- 混淆矩阵: TP=3 TN=2 FP=0 FN=0

## 红线质量
- 拦截率: 100.0%
- 放行率: 100.0%
- 误拦率: 0.0%
- reason 匹配率: 100.0%

## 执行质量
- 执行成功率: 100.0%
- 适配器成功率: {'SpringAI': 1.0, 'LangChain': 1.0}
- 产物成功率: 100.0%

## Token 消耗对比
- 基线 (simple-echo): 53 tokens
- 文档生成 (document-generator): 139 tokens
- overhead: 162.3%
