---
name: strict-trigger-lab
description: A deliberately strict trigger test skill that may be used only when the task satisfies multiple explicit constraints at the same time.
---

# Strict Trigger Lab

Use this skill only when every condition below is true:

1. The user explicitly says this is a trigger-condition, routing, middleware, or skill-selection test.
2. The user requests deterministic behavior rather than creative generation.
3. The task mentions at least three constraints that all must be satisfied.
4. The task can be completed without network access.
5. The expected output is a short diagnostic, checklist, or validation result.
6. The task does not involve secrets, credentials, personal data, production deployment, destructive file operations, or irreversible changes.

If any condition is missing, do not use this skill.

## Instructions

- State which trigger conditions were satisfied.
- State which trigger conditions were missing, if any.
- Keep the response concise and diagnostic.

