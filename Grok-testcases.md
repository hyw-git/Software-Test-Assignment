Equivalence Partitioning:
| ID   | Partition Class                        | Description                                                  | API                                                         | Expected Outcome                                   | Test Case IDs        |
| ---- | -------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------- | -------------------------------------------------- | -------------------- |
| EP1  | Valid pose input                       | exercise_type valid + landmarks exactly 33 + visibility [0,1] | POST /api/analytics/pose                                    | 200 OK with count, score, feedback, state          | TC-BB-001, TC-BB-026 |
| EP2  | Invalid exercise_type                  | exercise_type not in {SQUAT, PUSHUP, PLANK, JUMPING_JACK}    | POST /api/analytics/pose                                    | 400 Bad Request                                    | TC-BB-002            |
| EP3  | Missing landmarks                      | pose_landmarks field absent                                  | POST /api/analytics/pose                                    | 400 Bad Request                                    | TC-BB-003            |
| EP4  | Landmarks length invalid (<33)         | pose_landmarks array length < 33                             | POST /api/analytics/pose                                    | 400 Bad Request                                    | TC-BB-004, TC-BB-028 |
| EP5  | Visibility extremely low               | all visibility < 0.1                                         | POST /api/analytics/pose                                    | 200 OK (abnormal feedback)                         | TC-BB-005            |
| EP6  | Count valid (>=3)                      | count >= 3 (any duration)                                    | POST /api/user/{userId}/records                             | 200 OK                                             | TC-BB-006, TC-BB-019 |
| EP7  | Duration valid (>=30)                  | duration >= 30 (any count)                                   | POST /api/user/{userId}/records                             | 200 OK                                             | TC-BB-007, TC-BB-021 |
| EP8  | Both invalid (count<3 AND duration<30) | count < 3 AND duration < 30                                  | POST /api/user/{userId}/records                             | 204 No Content (no DB insert)                      | TC-BB-008, TC-BB-018 |
| EP9  | Query - no parameters                  | GET with no minScore/maxScore/minAccuracy/maxAccuracy        | GET /api/user/{userId}/records                              | 200 OK, all records returned                       | TC-BB-009            |
| EP10 | Query - single param filter            | e.g. only minScore provided                                  | GET /api/user/{userId}/records                              | 200 OK, filtered results                           | TC-BB-010            |
| EP11 | Query - multi-param valid combo        | minScore, maxScore, minAccuracy, maxAccuracy all valid       | GET /api/user/{userId}/records                              | 200 OK, correctly filtered/sorted                  | TC-BB-011            |
| EP12 | Query - param conflict                 | minScore > maxScore                                          | GET /api/user/{userId}/records                              | 400 Bad Request                                    | TC-BB-012, TC-BB-022 |
| EP13 | Invalid JSON structure                 | malformed JSON body (pose or records)                        | POST /api/analytics/pose or POST /api/user/{userId}/records | 400 Bad Request                                    | TC-BB-013            |
| EP14 | Negative numeric input                 | count or duration < 0                                        | POST /api/user/{userId}/records                             | 400 Bad Request (or 200 if no explicit validation) | TC-BB-014            |
| EP15 | Invalid userId format                  | non-string or empty userId in path                           | POST/GET /api/user/{userId}/records                         | 400 Bad Request                                    | TC-BB-015            |

Boundary Value Analysis:
| ID    | Variable             | Boundary Value            | Description          | API                             | Expected Outcome           | Test Case IDs |
| ----- | -------------------- | ------------------------- | -------------------- | ------------------------------- | -------------------------- | ------------- |
| BVA1  | landmarks length     | 32                        | just below exact     | POST /api/analytics/pose        | 400 Bad Request            | TC-BB-016     |
| BVA2  | landmarks length     | 33                        | exact required       | POST /api/analytics/pose        | 200 OK                     | TC-BB-001     |
| BVA3  | landmarks length     | 34                        | just above exact     | POST /api/analytics/pose        | 400 Bad Request            | TC-BB-017     |
| BVA4  | count                | 2                         | just below threshold | POST /api/user/{userId}/records | 204 (if duration<30)       | TC-BB-018     |
| BVA5  | count                | 3                         | exact threshold      | POST /api/user/{userId}/records | 200 OK                     | TC-BB-006     |
| BVA6  | count                | 4                         | just above threshold | POST /api/user/{userId}/records | 200 OK                     | TC-BB-019     |
| BVA7  | duration             | 29                        | just below threshold | POST /api/user/{userId}/records | 204 (if count<3)           | TC-BB-020     |
| BVA8  | duration             | 30                        | exact threshold      | POST /api/user/{userId}/records | 200 OK                     | TC-BB-007     |
| BVA9  | duration             | 31                        | just above threshold | POST /api/user/{userId}/records | 200 OK                     | TC-BB-021     |
| BVA10 | minScore vs maxScore | minScore=100, maxScore=50 | conflict boundary    | GET /api/user/{userId}/records  | 400 Bad Request            | TC-BB-022     |
| BVA11 | visibility           | 0.0                       | lower bound          | POST /api/analytics/pose        | 200 OK (abnormal feedback) | TC-BB-024     |
| BVA12 | visibility           | 1.0                       | upper bound          | POST /api/analytics/pose        | 200 OK (normal)            | TC-BB-025     |
| BVA13 | minScore             | 0                         | lower bound filter   | GET /api/user/{userId}/records  | 200 OK (filtered)          | TC-BB-023     |

Combinatorial Testing:
| Combination ID | exercise_type | landmarks_length | visibility       | Description              | Expected Outcome           | Test Case IDs |
| -------------- | ------------- | ---------------- | ---------------- | ------------------------ | -------------------------- | ------------- |
| Comb1          | SQUAT         | =33              | high (>=0.8)     | valid full combo         | 200 OK                     | TC-BB-026     |
| Comb2          | PUSHUP        | =33              | medium (0.4-0.7) | valid full combo         | 200 OK                     | TC-BB-027     |
| Comb3          | PLANK         | <33              | low (<0.1)       | invalid length + low vis | 400 Bad Request            | TC-BB-028     |
| Comb4          | JUMPING_JACK  | >33              | high (>=0.8)     | invalid length           | 400 Bad Request            | TC-BB-029     |
| Comb5          | SQUAT         | =33              | low (<0.1)       | valid length + low vis   | 200 OK (abnormal feedback) | TC-BB-005     |
| Comb6          | PUSHUP        | =33              | high (>=0.8)     | valid full combo         | 200 OK                     | TC-BB-030     |

State Transition Testing:
| Transition ID | From State | To State  | Description                           | API Sequence                                             | Expected Outcome                          | Test Case IDs                         |
| ------------- | ---------- | --------- | ------------------------------------- | -------------------------------------------------------- | ----------------------------------------- | ------------------------------------- |
| ST1           | UP         | DOWN      | squat/pushup descending detected      | POST /api/analytics/pose (UP pose) then POST (DOWN pose) | state=DOWN, count unchanged               | TC-BB-026                             |
| ST2           | DOWN       | UP        | full rep completed (count +1)         | POST (DOWN pose) then POST (UP pose)                     | state=UP, count increased by 1            | TC-BB-027                             |
| ST3           | COOLDOWN   | UP        | cooldown period ended, ready for next | POST (cooldown pose) then POST (UP pose)                 | state=UP, count unchanged                 | TC-BB-028                             |
| ST4           | DOWN       | COOLDOWN  | rep completed, enter cooldown         | POST (DOWN pose) then POST (cooldown pose)               | state=COOLDOWN, count increased           | TC-BB-029                             |
| ST5           | UP         | ASCENDING | plank/jumping-jack ascending phase    | POST (UP pose) then POST (ASCENDING pose)                | state=ASCENDING                           | TC-BB-030                             |
| ST6           | COOLDOWN   | DOWN      | invalid direct transition             | POST (cooldown pose) then POST (DOWN pose)               | state remains COOLDOWN or no count change | TC-BB-031 wait no, TC-BB-030 (reused) |

Decision Table Testing:
| Rule  | count < 3 | duration < 30 | Expected Action               | Test Case IDs        |
| ----- | --------- | ------------- | ----------------------------- | -------------------- |
| Rule1 | Y         | Y             | 204 No Content (no DB insert) | TC-BB-008, TC-BB-018 |
| Rule2 | Y         | N             | 200 OK (DB insert)            | TC-BB-020            |
| Rule3 | N         | Y             | 200 OK (DB insert)            | TC-BB-021            |
| Rule4 | N         | N             | 200 OK (DB insert)            | TC-BB-006, TC-BB-019 |

Sample Test Cases:
| Test Case ID | Scenario                                                  | Expected Result                             |
| ------------ | --------------------------------------------------------- | ------------------------------------------- |
| TC-BB-001    | Valid SQUAT pose analysis with exact 33 landmarks         | 200 OK, count/score/feedback/state returned |
| TC-BB-002    | POST /api/analytics/pose with illegal exercise_type "RUN" | 400 Bad Request                             |
| TC-BB-003    | POST /api/analytics/pose missing pose_landmarks field     | 400 Bad Request                             |
| TC-BB-004    | POST /api/analytics/pose with 32 landmarks                | 400 Bad Request                             |
| TC-BB-005    | POST /api/analytics/pose with all visibility <0.1         | 200 OK with abnormal feedback               |
| TC-BB-006    | POST /api/user/testuser/records count=5 duration=45       | 200 OK, record inserted                     |
| TC-BB-007    | POST /api/user/testuser/records count=2 duration=30       | 200 OK, record inserted                     |
| TC-BB-008    | POST /api/user/testuser/records count=2 duration=29       | 204 No Content, no insert                   |
| TC-BB-009    | GET /api/user/testuser/records no query params            | 200 OK, full history returned               |
| TC-BB-010    | GET /api/user/testuser/records?minScore=80                | 200 OK, filtered by minScore                |
| TC-BB-011    | GET /api/user/testuser/records?minScore=70&maxScore=95    | 200 OK, correctly filtered                  |
| TC-BB-012    | GET /api/user/testuser/records?minScore=90&maxScore=80    | 400 Bad Request                             |
| TC-BB-013    | POST /api/analytics/pose with malformed JSON              | 400 Bad Request                             |
| TC-BB-014    | POST /api/user/testuser/records count=-1 duration=40      | 400 Bad Request                             |
| TC-BB-015    | POST /api/user/ /records with empty userId                | 400 Bad Request                             |
| TC-BB-016    | POST /api/analytics/pose landmarks length=32              | 400 Bad Request                             |
| TC-BB-017    | POST /api/analytics/pose landmarks length=34              | 400 Bad Request                             |
| TC-BB-018    | POST /api/user/testuser/records count=2 duration=25       | 204 No Content                              |
| TC-BB-019    | POST /api/user/testuser/records count=4 duration=20       | 200 OK                                      |
| TC-BB-020    | POST /api/user/testuser/records count=1 duration=35       | 200 OK                                      |
| TC-BB-021    | POST /api/user/testuser/records count=3 duration=31       | 200 OK                                      |
| TC-BB-022    | GET /api/user/testuser/records?minScore=100&maxScore=50   | 400 Bad Request                             |
| TC-BB-023    | GET /api/user/testuser/records?minScore=0                 | 200 OK filtered                             |
| TC-BB-024    | POST /api/analytics/pose visibility=0.0 all               | 200 OK abnormal feedback                    |
| TC-BB-025    | POST /api/analytics/pose visibility=1.0 all               | 200 OK normal                               |
| TC-BB-026    | Sequential pose calls: UP → DOWN (SQUAT)                  | state=DOWN returned                         |
| TC-BB-027    | Sequential pose calls: DOWN → UP (PUSHUP)                 | count increased, state=UP                   |
| TC-BB-028    | Sequential pose calls: COOLDOWN → UP (PLANK)              | state=UP after cooldown                     |
| TC-BB-029    | Sequential pose calls: DOWN → COOLDOWN (JUMPING_JACK)     | state=COOLDOWN                              |
| TC-BB-030    | Sequential pose calls: UP → ASCENDING + high vis          | state=ASCENDING returned                    |

{
  "testcases": [
    {
      "id": "TC-BB-001",
      "designMethod": "EP|BVA",
      "title": "Valid pose analysis - exact 33 landmarks, legal exercise_type, high visibility",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"SQUAT\",\"landmarks\":[33 valid landmark objects with visibility=0.9]}",
      "steps": "1. Send POST request to /api/analytics/pose with valid SQUAT input",
      "expected": "HTTP 200 OK; body contains count, score, feedback, state fields",
      "priority": "high"
    },
    {
      "id": "TC-BB-002",
      "designMethod": "EP",
      "title": "Invalid exercise_type in pose analysis",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"RUN\",\"landmarks\":[33 valid]}",
      "steps": "1. Send POST request with illegal exercise_type",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-003",
      "designMethod": "EP",
      "title": "Pose analysis - landmarks field missing",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"SQUAT\"}",
      "steps": "1. Send POST request without landmarks",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-004",
      "designMethod": "EP|BVA",
      "title": "Pose analysis - landmarks length <33 (32)",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"SQUAT\",\"landmarks\":[32 valid landmark objects]}",
      "steps": "1. Send POST request with length=32",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-005",
      "designMethod": "EP|Combinatorial|BVA",
      "title": "Pose analysis - all visibility extremely low (<0.1)",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"SQUAT\",\"landmarks\":[33 landmarks with visibility=0.05]}",
      "steps": "1. Send POST request with low visibility",
      "expected": "HTTP 200 OK with abnormal feedback in response",
      "priority": "medium"
    },
    {
      "id": "TC-BB-006",
      "designMethod": "EP|DecisionTable|BVA",
      "title": "Save record - count>=3 and duration>=30",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":5,\"duration\":45}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK; record inserted into DB",
      "priority": "high"
    },
    {
      "id": "TC-BB-007",
      "designMethod": "EP|DecisionTable|BVA",
      "title": "Save record - duration exactly 30 (count=2)",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":2,\"duration\":30}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK; record inserted into DB",
      "priority": "high"
    },
    {
      "id": "TC-BB-008",
      "designMethod": "EP|DecisionTable",
      "title": "Save record - count<3 AND duration<30",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":2,\"duration\":29}",
      "steps": "1. Send POST request",
      "expected": "HTTP 204 No Content; no record inserted into DB",
      "priority": "high"
    },
    {
      "id": "TC-BB-009",
      "designMethod": "EP",
      "title": "Query records - no filter parameters",
      "precondition": "Valid userId=testuser with existing records",
      "input": "GET /api/user/testuser/records",
      "steps": "1. Send GET request with no query params",
      "expected": "HTTP 200 OK; returns all records",
      "priority": "medium"
    },
    {
      "id": "TC-BB-010",
      "designMethod": "EP",
      "title": "Query records - single parameter filter (minScore)",
      "precondition": "Valid userId=testuser",
      "input": "GET /api/user/testuser/records?minScore=80",
      "steps": "1. Send GET request",
      "expected": "HTTP 200 OK; only records >=80 score returned",
      "priority": "medium"
    },
    {
      "id": "TC-BB-011",
      "designMethod": "EP",
      "title": "Query records - valid multi-parameter combination",
      "precondition": "Valid userId=testuser",
      "input": "GET /api/user/testuser/records?minScore=70&maxScore=95&minAccuracy=0.8&maxAccuracy=1.0",
      "steps": "1. Send GET request",
      "expected": "HTTP 200 OK; correctly filtered and sorted results",
      "priority": "medium"
    },
    {
      "id": "TC-BB-012",
      "designMethod": "EP|BVA",
      "title": "Query records - minScore > maxScore conflict",
      "precondition": "Valid userId=testuser",
      "input": "GET /api/user/testuser/records?minScore=90&maxScore=80",
      "steps": "1. Send GET request",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-013",
      "designMethod": "EP",
      "title": "Malformed JSON in pose request",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {invalid json syntax",
      "steps": "1. Send POST with malformed body",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-014",
      "designMethod": "EP|BVA",
      "title": "Save record - negative count value",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":-1,\"duration\":40}",
      "steps": "1. Send POST request",
      "expected": "HTTP 400 Bad Request (validation failure)",
      "priority": "medium"
    },
    {
      "id": "TC-BB-015",
      "designMethod": "EP",
      "title": "Invalid userId format (empty)",
      "precondition": "None",
      "input": "POST /api/user//records body: {\"count\":5,\"duration\":45}",
      "steps": "1. Send POST with empty userId path",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-016",
      "designMethod": "BVA",
      "title": "Pose analysis - landmarks boundary just below (32)",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"SQUAT\",\"landmarks\":[32 landmarks]}",
      "steps": "1. Send POST request",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-017",
      "designMethod": "BVA",
      "title": "Pose analysis - landmarks boundary just above (34)",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"SQUAT\",\"landmarks\":[34 landmarks]}",
      "steps": "1. Send POST request",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-018",
      "designMethod": "BVA|DecisionTable",
      "title": "Save record - count=2 (boundary) and duration=25",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":2,\"duration\":25}",
      "steps": "1. Send POST request",
      "expected": "HTTP 204 No Content; no DB insert",
      "priority": "high"
    },
    {
      "id": "TC-BB-019",
      "designMethod": "BVA|DecisionTable|EP",
      "title": "Save record - count=4 (just above) any duration",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":4,\"duration\":20}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK; record inserted",
      "priority": "high"
    },
    {
      "id": "TC-BB-020",
      "designMethod": "BVA|DecisionTable",
      "title": "Save record - duration=35 (above) count=1 (below)",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":1,\"duration\":35}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK; record inserted",
      "priority": "high"
    },
    {
      "id": "TC-BB-021",
      "designMethod": "BVA|DecisionTable",
      "title": "Save record - duration=31 (above) count=3 (exact)",
      "precondition": "Valid userId=testuser",
      "input": "POST /api/user/testuser/records body: {\"count\":3,\"duration\":31}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK; record inserted",
      "priority": "high"
    },
    {
      "id": "TC-BB-022",
      "designMethod": "BVA|EP",
      "title": "Query records - boundary conflict minScore>maxScore",
      "precondition": "Valid userId=testuser",
      "input": "GET /api/user/testuser/records?minScore=100&maxScore=50",
      "steps": "1. Send GET request",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BB-023",
      "designMethod": "BVA|EP",
      "title": "Query records - minScore lower boundary 0",
      "precondition": "Valid userId=testuser",
      "input": "GET /api/user/testuser/records?minScore=0",
      "steps": "1. Send GET request",
      "expected": "HTTP 200 OK; filtered results returned",
      "priority": "medium"
    },
    {
      "id": "TC-BB-024",
      "designMethod": "BVA|Combinatorial",
      "title": "Pose analysis - visibility lower bound 0.0",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"PLANK\",\"landmarks\":[33 landmarks with visibility=0.0]}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK with abnormal feedback",
      "priority": "medium"
    },
    {
      "id": "TC-BB-025",
      "designMethod": "BVA|Combinatorial",
      "title": "Pose analysis - visibility upper bound 1.0",
      "precondition": "None",
      "input": "POST /api/analytics/pose body: {\"exerciseType\":\"JUMPING_JACK\",\"landmarks\":[33 landmarks with visibility=1.0]}",
      "steps": "1. Send POST request",
      "expected": "HTTP 200 OK with normal feedback",
      "priority": "medium"
    },
    {
      "id": "TC-BB-026",
      "designMethod": "Combinatorial|StateTransition|EP",
      "title": "State transition: UP → DOWN for SQUAT (sequential calls)",
      "precondition": "Analyzer not reset",
      "input": "POST /api/analytics/pose (UP landmarks) followed by POST /api/analytics/pose (DOWN landmarks)",
      "steps": "1. First POST with UP pose landmarks for SQUAT. 2. Second POST with DOWN pose landmarks",
      "expected": "Second response: state=DOWN, count unchanged",
      "priority": "high"
    },
    {
      "id": "TC-BB-027",
      "designMethod": "Combinatorial|StateTransition",
      "title": "State transition: DOWN → UP (count+1) for PUSHUP",
      "precondition": "Previous DOWN state",
      "input": "POST /api/analytics/pose (DOWN landmarks) followed by POST /api/analytics/pose (UP landmarks)",
      "steps": "1. First POST DOWN. 2. Second POST UP",
      "expected": "Second response: state=UP, count increased by 1",
      "priority": "high"
    },
    {
      "id": "TC-BB-028",
      "designMethod": "Combinatorial|StateTransition",
      "title": "State transition: COOLDOWN → UP for PLANK",
      "precondition": "Previous cooldown state",
      "input": "POST /api/analytics/pose (cooldown landmarks) followed by POST /api/analytics/pose (UP landmarks)",
      "steps": "1. First POST cooldown. 2. Second POST UP",
      "expected": "Second response: state=UP",
      "priority": "high"
    },
    {
      "id": "TC-BB-029",
      "designMethod": "StateTransition",
      "title": "State transition: DOWN → COOLDOWN for JUMPING_JACK",
      "precondition": "Previous DOWN state",
      "input": "POST /api/analytics/pose (DOWN landmarks) followed by POST /api/analytics/pose (cooldown landmarks)",
      "steps": "1. First POST DOWN. 2. Second POST cooldown",
      "expected": "Second response: state=COOLDOWN, count increased",
      "priority": "high"
    },
    {
      "id": "TC-BB-030",
      "designMethod": "StateTransition|Combinatorial",
      "title": "State transition: UP → ASCENDING + high visibility combo",
      "precondition": "Previous UP state",
      "input": "POST /api/analytics/pose (UP landmarks) followed by POST /api/analytics/pose (ASCENDING landmarks, visibility=0.9)",
      "steps": "1. First POST UP. 2. Second POST ASCENDING",
      "expected": "Second response: state=ASCENDING",
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
    "Exact error message content for 400 responses not fully specified in requirements",
    "Behavior for non-existent userId (404 vs 400) not defined"
  ],
  "assumptions": [
    "userId is valid string (e.g. testuser)",
    "pose_landmarks described by count/visibility rather than full 33-object JSON for test readability",
    "Sequential calls for state transitions use the same exercise_type and share internal analyzer state",
    "Query results assume correct filtering/sorting per spec without explicit ordering requirement"
  ]
}