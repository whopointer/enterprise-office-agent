# Skill Eval Report

## Summary

- `activation_accuracy`: `1.0`
- `precision`: `1.0`
- `recall`: `1.0`
- `false_positive_rate`: `0.0`
- `false_negative_rate`: `0.0`
- `confidence_avg`: `0.9500000000000001`
- `confusion_matrix`: `{'TP': 6, 'TN': 5, 'FP': 0, 'FN': 0}`
- `redline_block_rate`: `1.0`
- `redline_pass_rate`: `1.0`
- `redline_false_block_rate`: `0.0`
- `redline_reason_match_rate`: `1.0`
- `execution_success_rate`: `1.0`
- `adapter_success_rate`: `{'eval-adapter': 1.0}`
- `latency_ms_avg`: `{'eval-adapter': 0.006478997723509868}`
- `artifact_success_rate`: `1.0`

## Cases

| Case | Expected | Actual | Executed | Blocked | Passed |
|---|---|---|---|---|---|
| tp_doc_zh | document-generator | document-generator | True | False | True |
| tp_doc_en | document-generator | document-generator | True | False | True |
| tp_echo | simple-echo | simple-echo | True | False | True |
| tp_skill_index | skill-index | skill-index | True | False | True |
| tp_security_passed | security-auditor | security-auditor | True | False | True |
| tn_weather | None | None | False | False | True |
| tn_coding | None | None | False | False | True |
| tn_empty | None | None | False | False | True |
| redline_block_no_fields | security-auditor | security-auditor | False | True | True |
| redline_block_partial | security-auditor | security-auditor | False | True | True |
| redline_pass | security-auditor | security-auditor | True | False | True |
