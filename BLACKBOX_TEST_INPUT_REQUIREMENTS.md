# FitnessAI 黑盒测试工具输入需求规范（High-Score Optimized）

------

## 1. 文档目的

本规范作为 LLM 黑盒测试工具的**主输入（requirements input）**，目标是：

- 生成 **12+ 高质量、可执行的黑盒测试用例**
- 覆盖以下方法：
  - EP（等价类划分）
  - BVA（边界值分析）
  - Combinatorial（组合测试）
  - State Transition（状态迁移）
  - Decision Table（判定表）

⚠️ 本文档不仅用于建模，还用于**直接驱动测试用例生成**。

------

## 2. 被测系统（SUT）

### 2.1 系统边界

- 测试对象：FitnessAI 后端 REST API
- 黑盒视角：仅基于请求与响应（HTTP + JSON）
- 前端不作为断言对象

------

## 3. API规格（测试断言依据）

### 3.1 姿态分析接口

- `POST /api/analytics/pose`

#### 输入约束：

- `exercise_type`: {SQUAT, PUSHUP, PLANK, JUMPING_JACK}（必填）
- `pose_landmarks`: 长度应为 **33**
- `visibility`: ∈ [0,1]

#### 输出行为：

- 合法请求 → `200 OK`
  - 返回字段：`count, score, feedback, state`
- 非法请求 → `400 Bad Request`

------

### 3.2 记录保存接口

- `POST /api/user/{userId}/records`

#### 输入：

- `count` (int)
- `duration` (int, 秒)

#### 判定规则（核心测试点）：

- `(count < 3 AND duration < 30)` → `204 No Content`
- 否则 → `200 OK`

------

### 3.3 历史记录查询

- `GET /api/user/{userId}/records`

#### 参数：

- `minScore, maxScore`
- `minAccuracy, maxAccuracy`

#### 异常情况：

- `minScore > maxScore` → `400 Bad Request`

------

## 4. Testcase 生成规则（关键评分点）

LLM 必须遵循：

### 4.1 数量要求

- 总测试用例 ≥ 12
- 每种方法 ≥ 2 个 testcase

------

### 4.2 映射规则（非常关键）

每类建模信息必须转化为 testcase：

#### EP → 至少 1 testcase / partition

#### BVA → 每个边界点至少 1 testcase

#### Decision Table → 每条规则至少 1 testcase

#### State Transition → 每个关键迁移至少 1 testcase

#### Combinatorial → 至少 4 个组合用例

------

### 4.3 覆盖要求

必须覆盖：

- 所有 API（M1–M4）
- 正常路径 + 异常路径
- 边界值 + 非法输入
- 多参数组合

------

## 5. 黑盒建模输入（用于展开）

------

### 5.1 等价类（EP）

#### 姿态分析

- EP1: 合法输入（长度=33，类型合法） → 200
- EP2: exercise_type 非法 → 400
- EP3: landmarks 缺失 → 400
- EP4: landmarks 长度 < 33 → 400
- EP5: visibility 极低 → 200（但反馈异常）

------

#### 记录保存

- EP6: count ≥ 3 → 200
- EP7: duration ≥ 30 → 200
- EP8: count < 3 AND duration < 30 → 204

------

#### 查询接口

- EP9: 无参数 → 正常返回
- EP10: 单参数过滤
- EP11: 多参数组合
- EP12: 参数冲突 → 400

------

### 5.2 边界值（BVA）

#### landmarks 长度

- 32, 33, 34

#### count

- 2, 3, 4

#### duration

- 29, 30, 31

👉 每个值都必须转化为 testcase

------

### 5.3 判定表（Decision Table）

| count <3 | duration <30 | 结果 |
| -------- | ------------ | ---- |
| Y        | Y            | 204  |
| Y        | N            | 200  |
| N        | Y            | 200  |
| N        | N            | 200  |

👉 每一行必须生成 testcase

------

### 5.4 状态迁移（State）

#### 深蹲/俯卧撑：

- UP → DOWN
- DOWN → UP（计数+1）
- COOLDOWN → UP

👉 每个迁移生成 testcase

------

### 5.5 输入组合（Combinatorial）

因子：

- exercise_type (4)
- landmarks长度 (<33, =33, >33)
- visibility (低/中/高)

👉 至少生成 4–6 个组合测试

------

## 6. 可验证断言（必须用于 expected）

测试用例 expected 必须包含：

- HTTP status（200 / 400 / 204）
- 是否入库（records接口）
- 返回字段是否存在
- 是否过滤数据
- 排序/筛选结果是否正确

------

## 7. 强制展开提示（防止生成过少）

LLM 必须：

- 不得少于 12 个 testcases
- 不得只覆盖方法而忽略数量
- 不得只给抽象描述，必须具体输入
- 不得省略 invalid / edge cases

------

## 8. 不确定信息处理

如果信息不足：

- 记录到 `missingItems`
- 不得编造内部逻辑
