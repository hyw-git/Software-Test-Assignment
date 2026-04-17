# FitnessAI 黑盒测试工具输入需求规范（High-Score Optimized）

------

## 1. 文档目的

本规范作为 LLM 黑盒测试工具的**主输入（requirements input）**，目标是：

- 以**覆盖充分性优先**生成高质量、可执行的黑盒测试用例
- 在覆盖达标前提下，生成 **12+** 测试用例（数量是下限，不是目标）
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

### 4.1 覆盖优先与数量下限（Coverage-first）

- 首要目标：覆盖充分，而不是凑数量
- 数量下限：总测试用例 ≥ 12
- 方法下限：每种方法 ≥ 2 个 testcase
- 即使已达到数量下限，只要覆盖未达标，必须继续补充 testcase
- 在覆盖达标后，优先避免重复用例；建议总量区间 12–20

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

- 所有已定义 API（至少包含 3.1–3.3）
- 正常路径 + 异常路径
- 边界值 + 非法输入
- 多参数组合

------

### 4.4 完成判定（Exit Criteria）

仅当以下条件全部满足时，才允许停止生成：

- API 覆盖完成（3.1–3.3 全覆盖）
- EP：每个已定义 partition 至少 1 个 testcase
- BVA：每个边界点至少 1 个 testcase
- Decision Table：每条规则至少 1 个 testcase
- State Transition：每个关键迁移至少 1 个 testcase
- Combinatorial：至少 4 个有效组合 testcase
- 每条 testcase 均含可执行输入与可验证 expected

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

多维边界执行策略（适用于如 3.2 的 count 与 duration）：

- 默认采用 ISTQB 常用的单故障假设（Single Fault Assumption）：每次仅让一个边界变量处于无效或临界状态，其他变量取典型有效值。
- 对于“二者/多者同时无效”的组合，默认**不作为强制 testcase**。
- 例外：若需求规则本身依赖联合条件（如判定表规则、组合测试高风险组合），仍应设计联合用例。

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
- 对错误请求需断言错误行为（如 400 + 错误信息/错误字段存在）

------

## 7. 强制展开提示（防止生成过少）

LLM 必须：

- 不得少于 12 个 testcases
- 不得为了凑数量而牺牲覆盖完整性
- 不得在覆盖未达标时停止生成
- 不得只给抽象描述，必须具体输入
- 不得省略 invalid / edge cases
- 不得用高度相似或重复场景充数

------

## 8. 不确定信息处理

如果信息不足：

- 记录到 `missingItems`
- 不得编造内部逻辑

------

## 9. ISTQB 对齐要求（建议强制）

为提升结果的学术规范性和可评分性，LLM 应按 ISTQB 黑盒设计思想生成测试：

- EP（Equivalence Partitioning）：区分有效/无效等价类；每类至少 1 例
- BVA（Boundary Value Analysis）：覆盖最小值、刚低于、边界值、刚高于、最大值（按变量适配）
- Decision Table：条件与动作规则完整枚举；每条规则映射至少 1 例
- State Transition：覆盖关键状态与关键迁移（至少包含有效迁移；必要时包含无效迁移）
- Combinatorial：多因子输入优先采用 pairwise 思路，必要时补充高风险组合

ISTQB 对齐的执行原则：

- 先覆盖后计数：覆盖达标优先于数量达标
- 可追溯：每个 testcase 应可映射到具体方法与规则来源
- 可判定：expected 必须可验证，避免“模糊正确”描述
