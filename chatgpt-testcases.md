**Equivalence Partitioning:**

| ID   | Description                                                  | Outcome                             |
| ---- | ------------------------------------------------------------ | ----------------------------------- |
| EP1  | TC-BB-001: 姿态分析合法输入（exercise_type=SQUAT, landmarks长度=33, visibility在[0,1]） | 200，返回count/score/feedback/state |
| EP2  | TC-BB-002: exercise_type非法（如YOGA）                       | 400，返回错误信息/错误字段          |
| EP3  | TC-BB-003: landmarks缺失                                     | 400，返回错误信息/错误字段          |
| EP4  | TC-BB-007: landmarks长度<33（32）                            | 400，返回错误信息/错误字段          |
| EP5  | TC-BB-018: visibility极低（0.0）但合法范围内                 | 200，反馈提示可见性问题             |
| EP6  | TC-BB-026: records接口 count<3 且 duration>=30               | 200，入库                           |
| EP7  | TC-BB-027: records接口 count>=3 且 duration<30               | 200，入库                           |
| EP8  | TC-BB-004: records接口 count<3 且 duration<30                | 204，不入库                         |
| EP9  | TC-BB-005: 查询接口无参数                                    | 200，返回记录列表                   |
| EP10 | TC-BB-029: 查询接口单参数过滤（minAccuracy）                 | 200，仅返回满足过滤条件数据         |
| EP11 | TC-BB-030: 查询接口多参数组合过滤（min/max score+accuracy）  | 200，过滤与排序正确                 |
| EP12 | TC-BB-006: 查询接口参数冲突（minScore>maxScore）             | 400，返回错误信息/错误字段          |

**Boundary Value Analysis:**

| Boundary          | Values                                                       |
| ----------------- | ------------------------------------------------------------ |
| landmarks长度边界 | 32(TC-BB-007), 33(TC-BB-008), 34(TC-BB-009)                  |
| count边界         | 2(TC-BB-010), 3(TC-BB-011), 4(TC-BB-012)                     |
| duration边界      | 29(TC-BB-010), 30(TC-BB-011), 31(TC-BB-012)                  |
| visibility边界    | 0.0(TC-BB-018), 1.0(TC-BB-013), >1.0无效(TC-BB-016)          |
| score过滤边界     | minScore=maxScore(TC-BB-022), minScore>maxScore(TC-BB-006)   |
| accuracy过滤边界  | minAccuracy单边界(TC-BB-029), minAccuracy/maxAccuracy组合(TC-BB-030) |

**Combinatorial Testing:**

| Combination ID | Input Combination Description                           | Expected Outcome             |
| -------------- | ------------------------------------------------------- | ---------------------------- |
| C1             | TC-BB-013: SQUAT + 长度33 + visibility=1.0(高)          | 200，字段完整                |
| C2             | TC-BB-014: PUSHUP + 长度33 + visibility=0.1(低)         | 200，反馈提示姿态/可见性问题 |
| C3             | TC-BB-015: PLANK + 长度32 + visibility=0.5(中)          | 400，长度非法                |
| C4             | TC-BB-016: JUMPING_JACK + 长度33 + visibility=1.2(越界) | 400，visibility非法          |
| C5             | TC-BB-017: PLANK + 长度33 + visibility=0.5(中)          | 200，字段完整                |
| C6             | TC-BB-018: SQUAT + 长度33 + visibility=0.0(极低)        | 200，反馈异常但请求合法      |

**State Transition Testing:**

| State Transition | Description            | Test Case ID |
| ---------------- | ---------------------- | ------------ |
| UP -> DOWN       | 深蹲连续帧触发下蹲状态 | TC-BB-019    |
| DOWN -> UP       | 深蹲回到站立并计数+1   | TC-BB-020    |
| COOLDOWN -> UP   | 深蹲冷却结束回到UP     | TC-BB-021    |
| UP -> DOWN       | 俯卧撑下压进入DOWN     | TC-BB-022    |
| DOWN -> UP       | 俯卧撑上推回UP并计数+1 | TC-BB-023    |
| COOLDOWN -> UP   | 俯卧撑冷却结束回UP     | TC-BB-024    |

**Decision Table Testing:**

| Rule | Condition 1          | Condition 2          | Condition 3  | Expected Action                      |
| ---- | -------------------- | -------------------- | ------------ | ------------------------------------ |
| R1   | count<3=Y            | duration<30=Y        | /records保存 | 204，不入库（TC-BB-025）             |
| R2   | count<3=Y            | duration<30=N        | /records保存 | 200，入库（TC-BB-026）               |
| R3   | count<3=N            | duration<30=Y        | /records保存 | 200，入库（TC-BB-027）               |
| R4   | count<3=N            | duration<30=N        | /records保存 | 200，入库（TC-BB-028）               |
| R5   | minScore<=maxScore=Y | 过滤参数存在=Y       | /records查询 | 200，按条件过滤（TC-BB-029）         |
| R6   | minScore<=maxScore=Y | score+accuracy组合=Y | /records查询 | 200，组合过滤与排序正确（TC-BB-030） |

**Sample Test Cases:**

| Test Case | Scenario                  | Expected Result                      |
| --------- | ------------------------- | ------------------------------------ |
| TC-BB-001 | 姿态分析合法输入          | 200 + count/score/feedback/state存在 |
| TC-BB-002 | 非法exercise_type         | 400 + 错误字段存在                   |
| TC-BB-003 | 缺失pose_landmarks        | 400 + 错误字段存在                   |
| TC-BB-004 | records双低阈值           | 204 + 不入库                         |
| TC-BB-005 | 查询无参数                | 200 + 返回列表                       |
| TC-BB-006 | minScore>maxScore         | 400 + 错误字段存在                   |
| TC-BB-007 | landmarks=32              | 400                                  |
| TC-BB-008 | landmarks=33              | 200                                  |
| TC-BB-009 | landmarks=34              | 400                                  |
| TC-BB-010 | count=2,duration=29       | 204 + 不入库                         |
| TC-BB-011 | count=3,duration=30       | 200 + 入库                           |
| TC-BB-012 | count=4,duration=31       | 200 + 入库                           |
| TC-BB-013 | SQUAT-33-高可见性组合     | 200                                  |
| TC-BB-014 | PUSHUP-33-低可见性组合    | 200 + 反馈异常提示                   |
| TC-BB-015 | PLANK-32-中可见性组合     | 400                                  |
| TC-BB-016 | JJ-33-visibility越界组合  | 400                                  |
| TC-BB-017 | PLANK-33-中可见性组合     | 200                                  |
| TC-BB-018 | SQUAT-33-visibility=0组合 | 200 + 反馈异常提示                   |
| TC-BB-019 | 深蹲UP->DOWN迁移          | 200 + state=DOWN                     |
| TC-BB-020 | 深蹲DOWN->UP并计数        | 200 + count+1                        |
| TC-BB-021 | 深蹲COOLDOWN->UP          | 200 + state=UP                       |
| TC-BB-022 | 俯卧撑UP->DOWN迁移        | 200 + state=DOWN                     |
| TC-BB-023 | 俯卧撑DOWN->UP并计数      | 200 + count+1                        |
| TC-BB-024 | 俯卧撑COOLDOWN->UP        | 200 + state=UP                       |
| TC-BB-025 | 判定表R1                  | 204 + 不入库                         |
| TC-BB-026 | 判定表R2                  | 200 + 入库                           |
| TC-BB-027 | 判定表R3                  | 200 + 入库                           |
| TC-BB-028 | 判定表R4                  | 200 + 入库                           |
| TC-BB-029 | 查询单参数过滤            | 200 + 全部accuracy>=minAccuracy      |
| TC-BB-030 | 查询多参数过滤与排序      | 200 + 满足范围且排序正确             |

{
  "testcases": [
    {
      "id": "TC-BB-001",
      "designMethod": "EP",
      "title": "姿态分析-合法输入返回200",
      "precondition": "用户已启动后端服务",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"SQUAT\",\"pose_landmarks\":\"33个点(visibility=0.9)\"}",
      "steps": "发送请求并读取响应JSON",
      "expected": "HTTP 200；返回字段count,score,feedback,state均存在"
    ,
      "priority": "high"
    },
    {
      "id": "TC-BB-002",
      "designMethod": "EP",
      "title": "姿态分析-exercise_type非法",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"YOGA\",\"pose_landmarks\":\"33个点(visibility=0.9)\"}",
      "steps": "发送请求",
      "expected": "HTTP 400；响应包含错误信息或错误字段",
      "priority": "high"
    },
    {
      "id": "TC-BB-003",
      "designMethod": "EP",
      "title": "姿态分析-landmarks缺失",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"PUSHUP\"}",
      "steps": "发送请求",
      "expected": "HTTP 400；响应包含错误信息或错误字段",
      "priority": "high"
    },
    {
      "id": "TC-BB-004",
      "designMethod": "EP",
      "title": "记录保存-双低阈值不入库",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":2,\"duration\":20}",
      "steps": "发送保存请求后查询该用户最新记录",
      "expected": "HTTP 204；数据库不新增该条记录",
      "priority": "high"
    },
    {
      "id": "TC-BB-005",
      "designMethod": "EP",
      "title": "历史记录查询-无参数",
      "precondition": "userId=1存在且已有历史记录",
      "input": "GET /api/user/1/records",
      "steps": "发送请求并检查响应数组",
      "expected": "HTTP 200；返回列表结构正确",
      "priority": "medium"
    },
    {
      "id": "TC-BB-006",
      "designMethod": "EP",
      "title": "历史记录查询-参数冲突",
      "precondition": "userId=1存在",
      "input": "GET /api/user/1/records?minScore=90&maxScore=80",
      "steps": "发送请求",
      "expected": "HTTP 400；响应包含错误信息或错误字段",
      "priority": "high"
    },
    {
      "id": "TC-BB-007",
      "designMethod": "BVA",
      "title": "landmarks长度下界外-32",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"SQUAT\",\"pose_landmarks\":\"32个点(visibility=0.9)\"}",
      "steps": "发送请求",
      "expected": "HTTP 400；长度校验失败",
      "priority": "high"
    },
    {
      "id": "TC-BB-008",
      "designMethod": "BVA",
      "title": "landmarks边界值-33",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"SQUAT\",\"pose_landmarks\":\"33个点(visibility=0.9)\"}",
      "steps": "发送请求",
      "expected": "HTTP 200；返回字段完整",
      "priority": "high"
    },
    {
      "id": "TC-BB-009",
      "designMethod": "BVA",
      "title": "landmarks上界外-34",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"SQUAT\",\"pose_landmarks\":\"34个点(visibility=0.9)\"}",
      "steps": "发送请求",
      "expected": "HTTP 400；长度校验失败",
      "priority": "high"
    },
    {
      "id": "TC-BB-010",
      "designMethod": "BVA",
      "title": "count=2,duration=29双下界",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":2,\"duration\":29}",
      "steps": "发送请求后检查是否入库",
      "expected": "HTTP 204；不入库",
      "priority": "high"
    },
    {
      "id": "TC-BB-011",
      "designMethod": "BVA",
      "title": "count=3,duration=30精确边界",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":3,\"duration\":30}",
      "steps": "发送请求后检查是否入库",
      "expected": "HTTP 200；入库成功",
      "priority": "high"
    },
    {
      "id": "TC-BB-012",
      "designMethod": "BVA",
      "title": "count=4,duration=31上界内",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":4,\"duration\":31}",
      "steps": "发送请求后检查是否入库",
      "expected": "HTTP 200；入库成功",
      "priority": "medium"
    },
    {
      "id": "TC-BB-013",
      "designMethod": "Combinatorial",
      "title": "组合C1-SQUAT/33/高可见性",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"SQUAT\",\"pose_landmarks\":\"33个点(visibility=1.0)\"}",
      "steps": "发送请求",
      "expected": "HTTP 200；返回字段完整",
      "priority": "medium"
    },
    {
      "id": "TC-BB-014",
      "designMethod": "Combinatorial",
      "title": "组合C2-PUSHUP/33/低可见性",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"PUSHUP\",\"pose_landmarks\":\"33个点(visibility=0.1)\"}",
      "steps": "发送请求",
      "expected": "HTTP 200；feedback提示动作或可见性问题",
      "priority": "medium"
    },
    {
      "id": "TC-BB-015",
      "designMethod": "Combinatorial",
      "title": "组合C3-PLANK/32/中可见性",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"PLANK\",\"pose_landmarks\":\"32个点(visibility=0.5)\"}",
      "steps": "发送请求",
      "expected": "HTTP 400；长度非法",
      "priority": "high"
    },
    {
      "id": "TC-BB-016",
      "designMethod": "Combinatorial",
      "title": "组合C4-JUMPING_JACK/33/visibility越界",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"JUMPING_JACK\",\"pose_landmarks\":\"33个点(visibility=1.2)\"}",
      "steps": "发送请求",
      "expected": "HTTP 400；visibility范围校验失败",
      "priority": "high"
    },
    {
      "id": "TC-BB-017",
      "designMethod": "Combinatorial",
      "title": "组合C5-PLANK/33/中可见性",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"PLANK\",\"pose_landmarks\":\"33个点(visibility=0.5)\"}",
      "steps": "发送请求",
      "expected": "HTTP 200；返回字段完整",
      "priority": "medium"
    },
    {
      "id": "TC-BB-018",
      "designMethod": "Combinatorial",
      "title": "组合C6-SQUAT/33/visibility=0",
      "precondition": "后端服务可用",
      "input": "POST /api/analytics/pose; body={\"exercise_type\":\"SQUAT\",\"pose_landmarks\":\"33个点(visibility=0.0)\"}",
      "steps": "发送请求",
      "expected": "HTTP 200；feedback存在且提示质量问题",
      "priority": "medium"
    },
    {
      "id": "TC-BB-019",
      "designMethod": "StateTransition",
      "title": "深蹲状态UP到DOWN",
      "precondition": "深蹲分析器处于UP初始状态",
      "input": "连续POST /api/analytics/pose(模拟下蹲帧序列)",
      "steps": "发送连续帧直到触发状态转换",
      "expected": "HTTP 200；state从UP变为DOWN；count不增加",
      "priority": "high"
    },
    {
      "id": "TC-BB-020",
      "designMethod": "StateTransition",
      "title": "深蹲状态DOWN到UP计数+1",
      "precondition": "深蹲分析器已处于DOWN",
      "input": "连续POST /api/analytics/pose(模拟起立帧序列)",
      "steps": "发送连续帧直到完成一次动作循环",
      "expected": "HTTP 200；state变为UP；count较前一次+1",
      "priority": "high"
    },
    {
      "id": "TC-BB-021",
      "designMethod": "StateTransition",
      "title": "深蹲状态COOLDOWN到UP",
      "precondition": "深蹲分析器处于COOLDOWN",
      "input": "连续POST /api/analytics/pose(稳定站立帧)",
      "steps": "发送足够帧数使冷却结束",
      "expected": "HTTP 200；state从COOLDOWN回到UP",
      "priority": "medium"
    },
    {
      "id": "TC-BB-022",
      "designMethod": "StateTransition",
      "title": "俯卧撑状态UP到DOWN",
      "precondition": "俯卧撑分析器处于UP",
      "input": "连续POST /api/analytics/pose(模拟下压帧序列)",
      "steps": "发送连续帧直到触发DOWN",
      "expected": "HTTP 200；state变为DOWN",
      "priority": "high"
    },
    {
      "id": "TC-BB-023",
      "designMethod": "StateTransition",
      "title": "俯卧撑状态DOWN到UP计数+1",
      "precondition": "俯卧撑分析器处于DOWN",
      "input": "连续POST /api/analytics/pose(模拟上推帧序列)",
      "steps": "发送连续帧完成一次动作",
      "expected": "HTTP 200；state变为UP；count+1",
      "priority": "high"
    },
    {
      "id": "TC-BB-024",
      "designMethod": "StateTransition",
      "title": "俯卧撑状态COOLDOWN到UP",
      "precondition": "俯卧撑分析器处于COOLDOWN",
      "input": "连续POST /api/analytics/pose(稳定帧)",
      "steps": "发送冷却结束所需帧",
      "expected": "HTTP 200；state回到UP",
      "priority": "medium"
    },
    {
      "id": "TC-BB-025",
      "designMethod": "DecisionTable",
      "title": "规则R1: count<3且duration<30",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":1,\"duration\":10}",
      "steps": "发送请求并检查数据库",
      "expected": "HTTP 204；不入库",
      "priority": "high"
    },
    {
      "id": "TC-BB-026",
      "designMethod": "DecisionTable",
      "title": "规则R2: count<3且duration>=30",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":2,\"duration\":45}",
      "steps": "发送请求并检查数据库",
      "expected": "HTTP 200；入库成功",
      "priority": "high"
    },
    {
      "id": "TC-BB-027",
      "designMethod": "DecisionTable",
      "title": "规则R3: count>=3且duration<30",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":5,\"duration\":20}",
      "steps": "发送请求并检查数据库",
      "expected": "HTTP 200；入库成功",
      "priority": "high"
    },
    {
      "id": "TC-BB-028",
      "designMethod": "DecisionTable",
      "title": "规则R4: count>=3且duration>=30",
      "precondition": "userId=1存在",
      "input": "POST /api/user/1/records; body={\"count\":6,\"duration\":40}",
      "steps": "发送请求并检查数据库",
      "expected": "HTTP 200；入库成功",
      "priority": "high"
    },
    {
      "id": "TC-BB-029",
      "designMethod": "DecisionTable",
      "title": "查询规则R5: 单参数过滤",
      "precondition": "userId=1存在且有不同accuracy记录",
      "input": "GET /api/user/1/records?minAccuracy=80",
      "steps": "发送请求并校验结果集每条记录accuracy>=80",
      "expected": "HTTP 200；过滤生效，无不满足条件数据",
      "priority": "medium"
    },
    {
      "id": "TC-BB-030",
      "designMethod": "DecisionTable",
      "title": "查询规则R6: 多参数组合过滤与排序",
      "precondition": "userId=1存在且有覆盖不同score/accuracy的记录",
      "input": "GET /api/user/1/records?minScore=60&maxScore=95&minAccuracy=70&maxAccuracy=98",
      "steps": "发送请求并校验每条记录都在区间内，且按接口默认排序返回",
      "expected": "HTTP 200；过滤正确；排序结果正确",
      "priority": "high"
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
    "错误响应体的固定字段结构未明确定义（仅能断言存在错误信息/错误字段）",
    "历史记录接口默认排序字段与排序方向未在需求中明确",
    "状态迁移触发所需连续帧阈值未在输入需求中明确"
  ],
  "assumptions": [
    "测试用户userId=1存在且可访问",
    "可通过构造连续姿态帧驱动状态迁移",
    "查询接口在过滤后返回可验证的score与accuracy字段",
    "records入库可通过后续查询结果或数据库探针验证"
  ]
}