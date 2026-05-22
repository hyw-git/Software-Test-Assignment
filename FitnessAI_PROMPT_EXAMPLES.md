# FitnessAI Prompt Examples

This document separates the global input prompt from technique-specific prompts.

The prompt in the left **Input and Generate** sidebar should describe the test project, scope, risks, and expected output style. Requirements that are specific to one black-box testing technique should be placed in that technique's **Technical Prompt** field.

## Overall Input Prompt

```text
FitnessAI is an intelligent fitness assistant with pose analysis, repetition counting, training plans, workout record filtering, and dashboard analytics.

Please generate test cases from the reviewed QRA requirements and risk items. Focus on API-level and business-flow behavior that can reveal validation errors, incorrect state counting, record filtering mistakes, invalid plan handling, and dashboard calculation defects.

Use clear test case titles, explicit input data, expected results/oracles, priority, and traceability to requirement or risk IDs. Keep the output suitable for manual review and later automation.
```

## EP Technical Prompt

```text
Use Equivalence Partitioning for FitnessAI. Identify valid and invalid classes for exerciseType, landmarks length/shape, difficulty, skipRest, count, durationSeconds, weightKg, durationHours, and exerciseType used by calorie calculation. Prefer one representative positive case and one representative negative case per important class, and link each case to the related REQ id.
```

## BVA Technical Prompt

```text
Use Boundary Value Analysis for FitnessAI numeric and size constraints. Cover landmarks.length around 33 with 32, 33, 34; count around 3 with 2, 3, 4; durationSeconds around 30 with 29, 30, 31; weightKg around [30, 200] with 29, 30, 31, 199, 200, 201; and durationHours around >0 with 0, a small positive value, and a normal positive value. Mark expected HTTP status and validation messages where relevant.
```

## Decision Table Technical Prompt

```text
Use Decision Table testing for FitnessAI business rules. Build rule coverage for workout record saving: count < 3, count >= 3, durationSeconds < 30, durationSeconds >= 30, with the expected action saved/not saved. Also include training plan difficulty validity and skipRest behavior as condition/action combinations when useful.
```

## Combinatorial Technical Prompt

```text
Use pairwise combinatorial testing for FitnessAI. Treat exerciseType, difficulty, skipRest, record-save classification, and representative input validity as factors. Generate a compact pairwise suite that avoids impossible combinations, keeps expected outcomes explicit, and prioritizes interactions that affect pose analysis, plan mode, record saving, and dashboard analytics.
```

## State Transition Technical Prompt

```text
Use State Transition testing for FitnessAI repetition counting. Model states UP, DESCENDING, DOWN, ASCENDING, and completed cycle. Cover the valid UP->DESCENDING->DOWN->ASCENDING->UP path, invalid short paths such as UP->DESCENDING->UP, repeated/duplicate frames, and cooldown behavior after a completed rep. Include expected count changes for each transition sequence.
```
