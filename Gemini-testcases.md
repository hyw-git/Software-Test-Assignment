**等价类划分 (Equivalence Partitioning):**

| ID   | 描述                                                         | 预期结果        |
| ---- | ------------------------------------------------------------ | --------------- |
| EP1  | `POST /api/analytics/pose` - 合法输入 (exercise\_type 合法, landmarks 长度=33, visibility ∈ [0,1]) | 200 OK          |
| EP2  | `POST /api/analytics/pose` - 非法 `exercise_type` (例如 "YOGA") | 400 Bad Request |
| EP3  | `POST /api/analytics/pose` - `landmarks` 字段缺失            | 400 Bad Request |
| EP4  | `POST /api/analytics/pose` - `landmarks` 数组长度 < 33       | 400 Bad Request |
| EP5  | `POST /api/analytics/pose` - `landmarks` 数组长度 > 33       | 400 Bad Request |
| EP6  | `POST /api/analytics/pose` - `visibility` 值 < 0             | 400 Bad Request |
| EP7  | `POST /api/analytics/pose` - `visibility` 值 > 1             | 400 Bad Request |
| EP8  | `POST /api/user/{userId}/records` - `count` ≥ 3, `duration` ≥ 30 | 200 OK          |
| EP9  | `POST /api/user/{userId}/records` - `count` < 3, `duration` ≥ 30 | 200 OK          |
| EP10 | `POST /api/user/{userId}/records` - `count` ≥ 3, `duration` < 30 | 200 OK          |
| EP11 | `POST /api/user/{userId}/records` - `count` < 3, `duration` < 30 | 204 No Content  |
| EP12 | `GET /api/user/{userId}/records` - 无查询参数                | 200 OK          |
| EP13 | `GET /api/user/{userId}/records` - 使用 `minScore` 和 `maxScore` 过滤 | 200 OK          |
| EP14 | `GET /api/user/{userId}/records` - 使用 `minAccuracy` 和 `maxAccuracy` 过滤 | 200 OK          |
| EP15 | `GET /api/user/{userId}/records` - `minScore` > `maxScore`   | 400 Bad Request |

**边界值分析 (Boundary Value Analysis):**

| 边界                  | 值                       |
| --------------------- | ------------------------ |
| `pose_landmarks` 长度 | 32, 33, 34               |
| `visibility`          | 0.0, 0.5, 1.0, -0.1, 1.1 |
| `count` (记录保存)    | 2, 3, 4                  |
| `duration` (记录保存) | 29, 30, 31               |

**组合测试 (Combinatorial Testing):**

| 组合 ID | 输入组合描述                                                 | 预期结果        |
| ------- | ------------------------------------------------------------ | --------------- |
| CT1     | `exercise_type`=SQUAT, `landmarks`长度=33, `visibility`=高(0.9) | 200 OK          |
| CT2     | `exercise_type`=PUSHUP, `landmarks`长度<33, `visibility`=中(0.5) | 400 Bad Request |
| CT3     | `exercise_type`=PLANK, `landmarks`长度>33, `visibility`=低(0.1) | 400 Bad Request |
| CT4     | `exercise_type`=JUMPING\_JACK, `landmarks`长度=33, `visibility`=0 | 200 OK          |
| CT5     | `exercise_type`=SQUAT, `landmarks`长度<33, `visibility`=高(0.9) | 400 Bad Request |
| CT6     | `exercise_type`=PUSHUP, `landmarks`长度=33, `visibility`=低(0.1) | 200 OK          |

**状态迁移测试 (State Transition Testing):**

| 状态迁移      | 描述                                        | 测试用例 ID  |
| ------------- | ------------------------------------------- | ------------ |
| NULL → UP     | 初始进入深蹲/俯卧撑准备姿势                 | TC-BB-ST-001 |
| UP → DOWN     | 从站立/准备姿势开始下蹲或俯身               | TC-BB-ST-002 |
| DOWN → UP     | 从蹲下/俯身姿势恢复到初始姿势，完成一次计数 | TC-BB-ST-003 |
| UP → COOLDOWN | 完成一次动作后进入冷却期，防止重复计数      | TC-BB-ST-004 |
| COOLDOWN → UP | 冷却期结束，可以开始下一次动作              | TC-BB-ST-005 |
| DOWN → DOWN   | 在底部位置保持不动                          | TC-BB-ST-006 |

**判定表测试 (Decision Table Testing):**

| 规则 | `count < 3` | `duration < 30` | 预期行为       |
| ---- | ----------- | --------------- | -------------- |
| 1    | Y           | Y               | 204 No Content |
| 2    | Y           | N               | 200 OK         |
| 3    | N           | Y               | 200 OK         |
| 4    | N           | N               | 200 OK         |

**示例测试用例 (Sample Test Cases):**

| 测试用例      | 场景                                                 | 预期结果                                           |
| ------------- | ---------------------------------------------------- | -------------------------------------------------- |
| TC-BB-EP-001  | `POST /api/analytics/pose` - 合法深蹲请求            | 200 OK, 返回 `count`, `score`, `feedback`, `state` |
| TC-BB-EP-002  | `POST /api/analytics/pose` - 非法运动类型            | 400 Bad Request                                    |
| TC-BB-BVA-001 | `POST /api/analytics/pose` - landmarks 长度为 32     | 400 Bad Request                                    |
| TC-BB-BVA-002 | `POST /api/analytics/pose` - landmarks 长度为 33     | 200 OK                                             |
| TC-BB-BVA-007 | `POST /api/user/1/records` - count=2, duration=50    | 200 OK, 记录被保存                                 |
| TC-BB-BVA-008 | `POST /api/user/1/records` - count=3, duration=50    | 200 OK, 记录被保存                                 |
| TC-BB-DT-001  | `POST /api/user/1/records` - count=2, duration=29    | 204 No Content, 记录不保存                         |
| TC-BB-DT-002  | `POST /api/user/1/records` - count=2, duration=30    | 200 OK, 记录被保存                                 |
| TC-BB-ST-003  | `POST /api/analytics/pose` - 模拟从DOWN到UP的动作    | 200 OK, `count` 增加 1                             |
| TC-BB-CT-001  | `POST /api/analytics/pose` - 合法深蹲，高可见度      | 200 OK                                             |
| TC-BB-EP-015  | `GET /api/user/1/records` - minScore=80, maxScore=70 | 400 Bad Request                                    |

```json
{
  "testcases": [
    {
      "id": "TC-BB-EP-001",
      "designMethod": "EP",
      "title": "姿态分析 - 合法输入 (SQUAT)",
      "precondition": "用户已登录，AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", \"pose_landmarks\": [{\"x\":0.5, \"y\":0.5, \"z\":0.5, \"visibility\":0.99}, ... (共33个)], \"visibility\": 0.99}",
      "steps": "发送一个包含合法 exercise_type 和33个 landmarks 的请求",
      "expected": "HTTP Status: 200 OK. 响应体包含 count, score, feedback, state 字段。",
      "priority": "high"
    },
    {
      "id": "TC-BB-EP-002",
      "designMethod": "EP",
      "title": "姿态分析 - 非法 exercise_type",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"YOGA\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 0.99}",
      "steps": "发送一个包含不在枚举范围内的 exercise_type 的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-EP-003",
      "designMethod": "EP",
      "title": "姿态分析 - 缺失 landmarks",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", \"visibility\": 0.99}",
      "steps": "发送一个缺少 pose_landmarks 字段的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-EP-004",
      "designMethod": "EP",
      "title": "姿态分析 - 非法输入 (visibility < 0)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": -0.1}",
      "steps": "发送一个 visibility 为负数的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "medium"
    },
    {
      "id": "TC-BB-EP-005",
      "designMethod": "EP",
      "title": "姿态分析 - 非法输入 (visibility > 1)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 1.1}",
      "steps": "发送一个 visibility 大于1的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "medium"
    },
    {
      "id": "TC-BB-EP-006",
      "designMethod": "EP",
      "title": "历史记录查询 - 参数冲突",
      "precondition": "用户存在历史记录",
      "input": "GET /api/user/123/records?minScore=90&maxScore=80",
      "steps": "发送一个 minScore > maxScore 的 GET 请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-001",
      "designMethod": "BVA",
      "title": "姿态分析 - landmarks 长度边界 (32)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PUSHUP\", \"pose_landmarks\": [ ... (共32个) ], \"visibility\": 0.95}",
      "steps": "发送一个 landmarks 数组长度为32的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-002",
      "designMethod": "BVA",
      "title": "姿态分析 - landmarks 长度边界 (33)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PUSHUP\", \"pose_landmarks\": [ ... (共33个) ], \"visibility\": 0.95}",
      "steps": "发送一个 landmarks 数组长度为33的请求",
      "expected": "HTTP Status: 200 OK.",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-003",
      "designMethod": "BVA",
      "title": "姿态分析 - landmarks 长度边界 (34)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PUSHUP\", \"pose_landmarks\": [ ... (共34个) ], \"visibility\": 0.95}",
      "steps": "发送一个 landmarks 数组长度为34的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-004",
      "designMethod": "BVA",
      "title": "记录保存 - count 边界 (2)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 2, \"duration\": 50}",
      "steps": "发送保存记录请求，count=2 (小于3), duration=50 (大于30)",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-005",
      "designMethod": "BVA",
      "title": "记录保存 - count 边界 (3)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 3, \"duration\": 50}",
      "steps": "发送保存记录请求，count=3 (等于3), duration=50 (大于30)",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-006",
      "designMethod": "BVA",
      "title": "记录保存 - duration 边界 (29)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 10, \"duration\": 29}",
      "steps": "发送保存记录请求，count=10 (大于3), duration=29 (小于30)",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-007",
      "designMethod": "BVA",
      "title": "记录保存 - duration 边界 (30)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 10, \"duration\": 30}",
      "steps": "发送保存记录请求，count=10 (大于3), duration=30 (等于30)",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-BVA-008",
      "designMethod": "BVA",
      "title": "姿态分析 - visibility 边界 (0.0)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PLANK\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 0.0}",
      "steps": "发送一个 visibility 为0的请求",
      "expected": "HTTP Status: 200 OK. (反馈可能提示异常)",
      "priority": "medium"
    },
    {
      "id": "TC-BB-BVA-009",
      "designMethod": "BVA",
      "title": "姿态分析 - visibility 边界 (1.0)",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PLANK\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 1.0}",
      "steps": "发送一个 visibility 为1的请求",
      "expected": "HTTP Status: 200 OK.",
      "priority": "medium"
    },
    {
      "id": "TC-BB-DT-001",
      "designMethod": "DecisionTable",
      "title": "判定表 - 规则1 (count<3, duration<30)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 2, \"duration\": 29}",
      "steps": "发送保存记录请求，count 和 duration 均小于阈值",
      "expected": "HTTP Status: 204 No Content. 记录不被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-DT-002",
      "designMethod": "DecisionTable",
      "title": "判定表 - 规则2 (count<3, duration>=30)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 2, \"duration\": 30}",
      "steps": "发送保存记录请求，count 小于阈值，duration 大于等于阈值",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-DT-003",
      "designMethod": "DecisionTable",
      "title": "判定表 - 规则3 (count>=3, duration<30)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 3, \"duration\": 29}",
      "steps": "发送保存记录请求，count 大于等于阈值，duration 小于阈值",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-DT-004",
      "designMethod": "DecisionTable",
      "title": "判定表 - 规则4 (count>=3, duration>=30)",
      "precondition": "用户存在",
      "input": "POST /api/user/123/records\nBody: {\"count\": 3, \"duration\": 30}",
      "steps": "发送保存记录请求，count 和 duration 均大于等于阈值",
      "expected": "HTTP Status: 200 OK. 记录被保存。",
      "priority": "high"
    },
    {
      "id": "TC-BB-ST-001",
      "designMethod": "StateTransition",
      "title": "状态迁移 - NULL 到 UP",
      "precondition": "分析器已重置",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", ... (模拟站立姿势)}",
      "steps": "发送第一个姿态数据，模拟用户进入准备姿势",
      "expected": "HTTP Status: 200 OK. 响应体 state: \"UP\".",
      "priority": "medium"
    },
    {
      "id": "TC-BB-ST-002",
      "designMethod": "StateTransition",
      "title": "状态迁移 - UP 到 DOWN",
      "precondition": "当前状态为 UP",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", ... (模拟下蹲姿势)}",
      "steps": "发送姿态数据，模拟用户从站立姿势开始下蹲",
      "expected": "HTTP Status: 200 OK. 响应体 state: \"DOWN\".",
      "priority": "high"
    },
    {
      "id": "TC-BB-ST-003",
      "designMethod": "StateTransition",
      "title": "状态迁移 - DOWN 到 UP (计数)",
      "precondition": "当前状态为 DOWN, count=N",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", ... (模拟站起姿势)}",
      "steps": "发送姿态数据，模拟用户从下蹲姿势站起",
      "expected": "HTTP Status: 200 OK. 响应体 state: \"UP\" 或 \"COOLDOWN\", count: N+1.",
      "priority": "high"
    },
    {
      "id": "TC-BB-ST-004",
      "designMethod": "StateTransition",
      "title": "状态迁移 - UP 到 COOLDOWN",
      "precondition": "刚完成一次计数 (DOWN -> UP)",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", ... (模拟站立姿势)}",
      "steps": "在计数后立即发送下一个站立姿势帧",
      "expected": "HTTP Status: 200 OK. 响应体 state: \"COOLDOWN\". count 不变。",
      "priority": "medium"
    },
    {
      "id": "TC-BB-ST-005",
      "designMethod": "StateTransition",
      "title": "状态迁移 - COOLDOWN 到 UP",
      "precondition": "当前状态为 COOLDOWN",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", ... (模拟站立姿势)}",
      "steps": "在冷却期后发送站立姿势帧",
      "expected": "HTTP Status: 200 OK. 响应体 state: \"UP\".",
      "priority": "medium"
    },
    {
      "id": "TC-BB-ST-006",
      "designMethod": "StateTransition",
      "title": "状态迁移 - 保持 DOWN 状态",
      "precondition": "当前状态为 DOWN",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", ... (模拟下蹲姿势)}",
      "steps": "连续发送下蹲姿势数据",
      "expected": "HTTP Status: 200 OK. 响应体 state: \"DOWN\". count 不变。",
      "priority": "medium"
    },
    {
      "id": "TC-BB-CT-001",
      "designMethod": "Combinatorial",
      "title": "组合测试 - 合法深蹲, 高可见度",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 0.95}",
      "steps": "发送一个合法运动类型、正确landmarks长度和高visibility的请求",
      "expected": "HTTP Status: 200 OK.",
      "priority": "high"
    },
    {
      "id": "TC-BB-CT-002",
      "designMethod": "Combinatorial",
      "title": "组合测试 - 俯卧撑, landmarks长度不足, 中可见度",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PUSHUP\", \"pose_landmarks\": [ ... (32个) ], \"visibility\": 0.5}",
      "steps": "发送一个合法运动类型、错误landmarks长度和中等visibility的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-CT-003",
      "designMethod": "Combinatorial",
      "title": "组合测试 - 平板支撑, landmarks长度过长, 低可见度",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PLANK\", \"pose_landmarks\": [ ... (34个) ], \"visibility\": 0.1}",
      "steps": "发送一个合法运动类型、错误landmarks长度和低visibility的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-CT-004",
      "designMethod": "Combinatorial",
      "title": "组合测试 - 开合跳, 合法长度, 零可见度",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"JUMPING_JACK\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 0.0}",
      "steps": "发送一个合法运动类型、正确landmarks长度和零visibility的请求",
      "expected": "HTTP Status: 200 OK. (反馈可能提示异常)",
      "priority": "medium"
    },
    {
      "id": "TC-BB-CT-005",
      "designMethod": "Combinatorial",
      "title": "组合测试 - 深蹲, landmarks长度不足, 高可见度",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"SQUAT\", \"pose_landmarks\": [ ... (32个) ], \"visibility\": 0.9}",
      "steps": "发送一个合法运动类型、错误landmarks长度和高visibility的请求",
      "expected": "HTTP Status: 400 Bad Request.",
      "priority": "high"
    },
    {
      "id": "TC-BB-CT-006",
      "designMethod": "Combinatorial",
      "title": "组合测试 - 俯卧撑, 合法长度, 低可见度",
      "precondition": "AI服务可用",
      "input": "POST /api/analytics/pose\nBody: {\"exercise_type\": \"PUSHUP\", \"pose_landmarks\": [ ... (33个) ], \"visibility\": 0.1}",
      "steps": "发送一个合法运动类型、正确landmarks长度和低visibility的请求",
      "expected": "HTTP Status: 200 OK.",
      "priority": "medium"
    }
  ],
  "coverageSummary": {
    "EP": "covered",
    "BVA": "covered",
    "Combinatorial": "covered",
    "StateTransition": "covered",
    "DecisionTable": "covered"
  },
  "missingItems": [
    "GET /api/user/{userId}/records 的 minAccuracy, maxAccuracy 参数的具体验证规则和冲突行为 (例如 minAccuracy > maxAccuracy)。",
    "状态迁移中 COOLDOWN 状态的具体持续时间或帧数。",
    "不同 visibility 值对 score 和 feedback 的具体影响。",
    "用户ID (userId) 的具体格式和验证规则（例如，是UUID、整数还是字符串）。"
  ],
  "assumptions": [
    "userId '123' 是一个有效的测试用户ID。",
    "pose_landmarks 的具体坐标值对于API的输入验证不重要，只有数组长度是关键。",
    "状态迁移测试中的 'UP', 'DOWN', 'COOLDOWN' 状态字符串与后端实现一致。",
    "所有API端点都部署在同一个根路径下。",
    "visibility 参数在 pose_landmarks 对象内部和请求体根级别同时存在时，具体的处理逻辑未定义，假设两者都需合法。"
  ]
}
```