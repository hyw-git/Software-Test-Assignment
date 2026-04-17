**Equivalence Partitioning:**

| ID   | Description                                                  | Outcome                                       |
| ---- | ------------------------------------------------------------ | --------------------------------------------- |
| EP1  | Pose: exercise_type valid (SQUAT, PUSHUP, PLANK, JUMPING_JACK) + landmarks length=33 + visibility∈[0,1] | 200 OK                                        |
| EP2  | Pose: exercise_type invalid (e.g., RUNNING)                  | 400 Bad Request                               |
| EP3  | Pose: landmarks missing                                      | 400 Bad Request                               |
| EP4  | Pose: landmarks length <33 (e.g., 32)                        | 400 Bad Request                               |
| EP5  | Pose: landmarks length >33 (e.g., 34)                        | 400 Bad Request                               |
| EP6  | Pose: visibility extremely low (all <0.1)                    | 200 OK but feedback indicates poor visibility |
| EP7  | Record: count≥3 (regardless of duration)                     | 200 OK                                        |
| EP8  | Record: duration≥30 (regardless of count)                    | 200 OK                                        |
| EP9  | Record: count<3 AND duration<30                              | 204 No Content                                |
| EP10 | Query: no query parameters                                   | 200 OK, returns all records                   |
| EP11 | Query: single parameter (minScore only)                      | 200 OK, filtered                              |
| EP12 | Query: multiple parameters (minScore+maxScore+minAccuracy)   | 200 OK, filtered                              |
| EP13 | Query: minScore > maxScore                                   | 400 Bad Request                               |
| EP14 | Query: minAccuracy > maxAccuracy                             | 400 Bad Request                               |
| EP15 | User profile: valid height (50-300 cm), weight (10-500 kg)   | 200 OK                                        |
| EP16 | User profile: invalid height (negative, zero, >300)          | 400 Bad Request                               |
| EP17 | User profile: invalid weight (negative, zero, >500)          | 400 Bad Request                               |
| EP18 | Dashboard: valid userId exists                               | 200 OK                                        |
| EP19 | Dashboard: userId not found                                  | 404 Not Found                                 |

**Boundary Value Analysis:**

| Boundary                  | Values                                             |
| ------------------------- | -------------------------------------------------- |
| landmarks length          | 32, 33, 34                                         |
| count                     | 2, 3, 4                                            |
| duration (seconds)        | 29, 30, 31                                         |
| visibility                | 0.0, 0.01, 0.5, 0.99, 1.0                          |
| minScore / maxScore       | 0, 1, 50, 99, 100, (min>max combos)                |
| minAccuracy / maxAccuracy | 0.0, 0.01, 0.5, 0.99, 1.0, (min>max combos)        |
| height (cm)               | 49, 50, 51, 299, 300, 301                          |
| weight (kg)               | 9, 10, 11, 499, 500, 501                           |
| userId                    | valid existing, non-existing, empty, special chars |

**Combinatorial Testing:**

| Combination ID | Input Combination Description                                | Expected Outcome                   |
| -------------- | ------------------------------------------------------------ | ---------------------------------- |
| C1             | exercise_type=SQUAT, landmarks length=33, visibility=0.8     | 200 OK, count updated              |
| C2             | exercise_type=PUSHUP, landmarks length=32, visibility=0.5    | 400 Bad Request                    |
| C3             | exercise_type=PLANK, landmarks length=33, visibility=0.0     | 200 OK, feedback low visibility    |
| C4             | exercise_type=JUMPING_JACK, landmarks length=34, visibility=0.9 | 400 Bad Request                    |
| C5             | exercise_type=SQUAT, landmarks length=33, visibility=1.0, with valid state transition UP→DOWN | 200 OK, state changed              |
| C6             | exercise_type=PUSHUP, landmarks length=33, visibility=0.2, count<3 and duration<30 later | 200 for pose, later 204 for record |
| C7             | exercise_type=INVALID, landmarks length=33, visibility=0.7   | 400 Bad Request                    |
| C8             | exercise_type=SQUAT, landmarks missing, visibility=0.6       | 400 Bad Request                    |

**State Transition Testing:**

| State Transition                            | Description                                                 | Test Case ID |
| ------------------------------------------- | ----------------------------------------------------------- | ------------ |
| UP → DOWN (Squat)                           | User goes from standing to squatting position               | TC-ST-001    |
| DOWN → UP (Squat)                           | User rises from squat to standing, count increments         | TC-ST-002    |
| COOLDOWN → UP (Squat)                       | After a valid rep, cooldown period ends and next rep starts | TC-ST-003    |
| UP → DOWN (Pushup)                          | User goes from plank top to chest down                      | TC-ST-004    |
| DOWN → UP (Pushup)                          | User pushes up, count increments                            | TC-ST-005    |
| IDLE → ACTIVE (Plank)                       | User holds plank position, timer starts                     | TC-ST-006    |
| ACTIVE → COOLDOWN (Plank)                   | User holds for threshold, cooldown                          | TC-ST-007    |
| JUMPING_JACK: ARMS_UP → ARMS_DOWN           | Arms raised then lowered, count increments                  | TC-ST-008    |
| Invalid transition: DOWN → DOWN (no change) | Staying in down position does not count                     | TC-ST-009    |

**Decision Table Testing:**

| Rule | count < 3 | duration < 30 | Result         |
| ---- | --------- | ------------- | -------------- |
| 1    | Y         | Y             | 204 No Content |
| 2    | Y         | N             | 200 OK         |
| 3    | N         | Y             | 200 OK         |
| 4    | N         | N             | 200 OK         |

(Additional decision table for pose analysis validation:)

| Rule | exercise_type valid? | landmarks length =33? | visibility >=0? | Result          |
| ---- | -------------------- | --------------------- | --------------- | --------------- |
| 5    | Y                    | Y                     | Y               | 200 OK          |
| 6    | N                    | Y                     | Y               | 400 Bad Request |
| 7    | Y                    | N                     | Y               | 400 Bad Request |
| 8    | Y                    | Y                     | N (negative)    | 400 Bad Request |

**Sample Test Cases:**

| Test Case   | Scenario                                                     | Expected Result                               |
| ----------- | ------------------------------------------------------------ | --------------------------------------------- |
| TC-EP-001   | Valid pose analysis with SQUAT, 33 landmarks, visibility 0.8 | 200 OK, returns count, score, feedback, state |
| TC-EP-002   | Invalid exercise type "RUNNING"                              | 400 Bad Request                               |
| TC-EP-003   | Missing landmarks field                                      | 400 Bad Request                               |
| TC-EP-004   | Landmarks length 32                                          | 400 Bad Request                               |
| TC-EP-005   | Landmarks length 34                                          | 400 Bad Request                               |
| TC-EP-006   | Very low visibility (0.01) but valid                         | 200 OK, feedback indicates detection issue    |
| TC-EP-007   | Record with count=5, duration=10                             | 200 OK                                        |
| TC-EP-008   | Record with count=2, duration=40                             | 200 OK                                        |
| TC-EP-009   | Record with count=2, duration=29                             | 204 No Content                                |
| TC-EP-010   | Query with no params                                         | 200 OK, returns all records                   |
| TC-EP-011   | Query with minScore=50 only                                  | 200 OK, filtered records                      |
| TC-EP-012   | Query with minScore=20&maxScore=80&minAccuracy=0.5           | 200 OK                                        |
| TC-EP-013   | Query minScore=80&maxScore=50                                | 400 Bad Request                               |
| TC-EP-014   | Query minAccuracy=0.9&maxAccuracy=0.3                        | 400 Bad Request                               |
| TC-BV-001   | Landmarks length = 32 (below boundary)                       | 400 Bad Request                               |
| TC-BV-002   | Landmarks length = 33 (boundary)                             | 200 OK                                        |
| TC-BV-003   | Landmarks length = 34 (above boundary)                       | 400 Bad Request                               |
| TC-BV-004   | count = 2 (below threshold for 204) with duration<30         | 204 No Content                                |
| TC-BV-005   | count = 3 (boundary) with duration<30                        | 200 OK                                        |
| TC-BV-006   | duration = 29 (below threshold) with count<3                 | 204 No Content                                |
| TC-BV-007   | duration = 30 (boundary) with count<3                        | 200 OK                                        |
| TC-BV-008   | visibility = 0.0 (min)                                       | 200 OK                                        |
| TC-BV-009   | visibility = 1.0 (max)                                       | 200 OK                                        |
| TC-BV-010   | minScore = -1                                                | 400 Bad Request                               |
| TC-BV-011   | maxScore = 101                                               | 400 Bad Request                               |
| TC-DT-001   | Decision Table Rule 1: count=2, duration=29                  | 204 No Content                                |
| TC-DT-002   | Decision Table Rule 2: count=2, duration=30                  | 200 OK                                        |
| TC-DT-003   | Decision Table Rule 3: count=3, duration=29                  | 200 OK                                        |
| TC-DT-004   | Decision Table Rule 4: count=3, duration=30                  | 200 OK                                        |
| TC-ST-001   | Squat state UP→DOWN                                          | state becomes DOWN, count unchanged           |
| TC-ST-002   | Squat state DOWN→UP                                          | count increments, state becomes UP            |
| TC-ST-003   | Squat cooldown→UP after valid rep                            | new rep can start                             |
| TC-ST-004   | Pushup UP→DOWN                                               | state becomes DOWN                            |
| TC-ST-005   | Pushup DOWN→UP                                               | count increments                              |
| TC-ST-006   | Plank IDLE→ACTIVE                                            | timer starts                                  |
| TC-ST-007   | Plank ACTIVE→COOLDOWN after hold                             | cooldown activated                            |
| TC-ST-008   | Jumping Jack ARMS_UP→ARMS_DOWN                               | count increments                              |
| TC-ST-009   | Repeated DOWN state without UP                               | no double counting                            |
| TC-COMB-001 | SQUAT + length33 + visibility high                           | 200 OK, proper analysis                       |
| TC-COMB-002 | PUSHUP + length32 + visibility medium                        | 400 Bad Request                               |
| TC-COMB-003 | PLANK + length33 + visibility zero                           | 200 OK, low visibility warning                |
| TC-COMB-004 | JUMPING_JACK + length34 + visibility high                    | 400 Bad Request                               |
| TC-COMB-005 | SQUAT + length33 + visibility low (0.1)                      | 200 OK, but feedback warns                    |
| TC-COMB-006 | INVALID_TYPE + length33 + visibility high                    | 400 Bad Request                               |

```json
{
  "testcases": [
    {
      "id": "TC-EP-001",
      "designMethod": "EP",
      "title": "Valid pose analysis with SQUAT",
      "precondition": "User has valid camera input",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [{\"x\":0.5,\"y\":0.3,\"z\":0.1,\"visibility\":0.8} (33 times)] }",
      "steps": "Send request with exactly 33 landmarks, each visibility 0.8",
      "expected": "HTTP 200 OK, response contains count, score (0-100), feedback string, state (UP/DOWN/COOLDOWN)",
      "priority": "high"
    },
    {
      "id": "TC-EP-002",
      "designMethod": "EP",
      "title": "Invalid exercise type",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"RUNNING\", \"landmarks\": [33 landmarks] }",
      "steps": "Send request with exerciseType not in {SQUAT, PUSHUP, PLANK, JUMPING_JACK}",
      "expected": "HTTP 400 Bad Request, error message indicating invalid exercise type",
      "priority": "high"
    },
    {
      "id": "TC-EP-003",
      "designMethod": "EP",
      "title": "Missing landmarks field",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\" }",
      "steps": "Omit landmarks array from request body",
      "expected": "HTTP 400 Bad Request, error message about missing landmarks",
      "priority": "high"
    },
    {
      "id": "TC-EP-004",
      "designMethod": "EP",
      "title": "Landmarks length less than 33",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [32 landmarks] }",
      "steps": "Send only 32 landmark objects",
      "expected": "HTTP 400 Bad Request, error message about incorrect landmarks count",
      "priority": "high"
    },
    {
      "id": "TC-EP-005",
      "designMethod": "EP",
      "title": "Landmarks length greater than 33",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [34 landmarks] }",
      "steps": "Send 34 landmark objects",
      "expected": "HTTP 400 Bad Request, error message about incorrect landmarks count",
      "priority": "high"
    },
    {
      "id": "TC-EP-006",
      "designMethod": "EP",
      "title": "Very low visibility landmarks",
      "precondition": "Camera partially occluded",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [{\"visibility\":0.01} repeated 33 times] }",
      "steps": "Send all landmarks with visibility 0.01",
      "expected": "HTTP 200 OK, feedback indicates low visibility or poor detection, but still processes",
      "priority": "medium"
    },
    {
      "id": "TC-EP-007",
      "designMethod": "EP",
      "title": "Record save with count >=3 (valid)",
      "precondition": "User exists with userId=1",
      "input": "POST /api/user/1/records { \"count\": 5, \"duration\": 10 }",
      "steps": "Send record with count=5, duration=10 (duration<30 but count>=3)",
      "expected": "HTTP 200 OK, record saved to database",
      "priority": "high"
    },
    {
      "id": "TC-EP-008",
      "designMethod": "EP",
      "title": "Record save with duration >=30 (valid)",
      "precondition": "User exists with userId=1",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 40 }",
      "steps": "Send record with count=2 (<3) but duration=40 (>=30)",
      "expected": "HTTP 200 OK, record saved",
      "priority": "high"
    },
    {
      "id": "TC-EP-009",
      "designMethod": "EP",
      "title": "Record save with both count<3 and duration<30 (filtered)",
      "precondition": "User exists with userId=1",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 29 }",
      "steps": "Send record that does not meet minimum quality threshold",
      "expected": "HTTP 204 No Content, record not saved",
      "priority": "high"
    },
    {
      "id": "TC-EP-010",
      "designMethod": "EP",
      "title": "Query records with no parameters",
      "precondition": "User has at least 5 existing records",
      "input": "GET /api/user/1/records",
      "steps": "Send GET request with no query parameters",
      "expected": "HTTP 200 OK, returns all records for user 1 (unfiltered)",
      "priority": "medium"
    },
    {
      "id": "TC-EP-011",
      "designMethod": "EP",
      "title": "Query records with single parameter minScore",
      "precondition": "User has records with scores 40,60,80",
      "input": "GET /api/user/1/records?minScore=50",
      "steps": "Add query param minScore=50",
      "expected": "HTTP 200 OK, returns only records with score >=50 (60 and 80)",
      "priority": "medium"
    },
    {
      "id": "TC-EP-012",
      "designMethod": "EP",
      "title": "Query records with multiple parameters",
      "precondition": "User has varied records",
      "input": "GET /api/user/1/records?minScore=20&maxScore=80&minAccuracy=0.5",
      "steps": "Send with three filter parameters",
      "expected": "HTTP 200 OK, returns records with score between 20-80 and accuracy >=0.5",
      "priority": "medium"
    },
    {
      "id": "TC-EP-013",
      "designMethod": "EP",
      "title": "Query with minScore > maxScore (invalid)",
      "precondition": "None",
      "input": "GET /api/user/1/records?minScore=80&maxScore=50",
      "steps": "Set minScore greater than maxScore",
      "expected": "HTTP 400 Bad Request, error indicating invalid range",
      "priority": "high"
    },
    {
      "id": "TC-EP-014",
      "designMethod": "EP",
      "title": "Query with minAccuracy > maxAccuracy (invalid)",
      "precondition": "None",
      "input": "GET /api/user/1/records?minAccuracy=0.9&maxAccuracy=0.3",
      "steps": "Set minAccuracy greater than maxAccuracy",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BV-001",
      "designMethod": "BVA",
      "title": "Landmarks length = 32 (below boundary)",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [32 landmarks] }",
      "steps": "Send exactly 32 landmarks",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BV-002",
      "designMethod": "BVA",
      "title": "Landmarks length = 33 (exact boundary)",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [33 landmarks] }",
      "steps": "Send exactly 33 landmarks",
      "expected": "HTTP 200 OK",
      "priority": "high"
    },
    {
      "id": "TC-BV-003",
      "designMethod": "BVA",
      "title": "Landmarks length = 34 (above boundary)",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [34 landmarks] }",
      "steps": "Send 34 landmarks",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-BV-004",
      "designMethod": "BVA",
      "title": "Count = 2 (below threshold for 204)",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 29 }",
      "steps": "Send count=2, duration=29",
      "expected": "HTTP 204 No Content",
      "priority": "high"
    },
    {
      "id": "TC-BV-005",
      "designMethod": "BVA",
      "title": "Count = 3 (boundary for saving)",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 3, \"duration\": 29 }",
      "steps": "Send count=3, duration=29 (duration<30 but count=3)",
      "expected": "HTTP 200 OK",
      "priority": "high"
    },
    {
      "id": "TC-BV-006",
      "designMethod": "BVA",
      "title": "Duration = 29 (below threshold for 204)",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 29 }",
      "steps": "Send duration=29 with count=2",
      "expected": "HTTP 204 No Content",
      "priority": "high"
    },
    {
      "id": "TC-BV-007",
      "designMethod": "BVA",
      "title": "Duration = 30 (boundary for saving)",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 30 }",
      "steps": "Send duration=30 with count=2",
      "expected": "HTTP 200 OK",
      "priority": "high"
    },
    {
      "id": "TC-BV-008",
      "designMethod": "BVA",
      "title": "Visibility = 0.0 (minimum)",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [{\"visibility\":0.0} repeated 33 times] }",
      "steps": "Send all landmarks with visibility 0.0",
      "expected": "HTTP 200 OK, but feedback likely indicates no detection",
      "priority": "medium"
    },
    {
      "id": "TC-BV-009",
      "designMethod": "BVA",
      "title": "Visibility = 1.0 (maximum)",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [{\"visibility\":1.0} repeated 33 times] }",
      "steps": "Send all landmarks with visibility 1.0",
      "expected": "HTTP 200 OK, high confidence detection",
      "priority": "medium"
    },
    {
      "id": "TC-DT-001",
      "designMethod": "DecisionTable",
      "title": "Decision Table Rule 1: count<3 and duration<30",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 29 }",
      "steps": "Send request",
      "expected": "HTTP 204 No Content",
      "priority": "high"
    },
    {
      "id": "TC-DT-002",
      "designMethod": "DecisionTable",
      "title": "Decision Table Rule 2: count<3 and duration>=30",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 2, \"duration\": 30 }",
      "steps": "Send request",
      "expected": "HTTP 200 OK",
      "priority": "high"
    },
    {
      "id": "TC-DT-003",
      "designMethod": "DecisionTable",
      "title": "Decision Table Rule 3: count>=3 and duration<30",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 3, \"duration\": 29 }",
      "steps": "Send request",
      "expected": "HTTP 200 OK",
      "priority": "high"
    },
    {
      "id": "TC-DT-004",
      "designMethod": "DecisionTable",
      "title": "Decision Table Rule 4: count>=3 and duration>=30",
      "precondition": "User exists",
      "input": "POST /api/user/1/records { \"count\": 3, \"duration\": 30 }",
      "steps": "Send request",
      "expected": "HTTP 200 OK",
      "priority": "high"
    },
    {
      "id": "TC-ST-001",
      "designMethod": "StateTransition",
      "title": "Squat state transition UP → DOWN",
      "precondition": "Analyzer initialized, current state=UP",
      "input": "POST /api/analytics/pose with landmarks showing squatting motion (hip-knee-ankle angle decreasing below 140°)",
      "steps": "Send sequence of frames transitioning from standing to squat",
      "expected": "Response state field changes from UP to DOWN, count does not increment yet",
      "priority": "high"
    },
    {
      "id": "TC-ST-002",
      "designMethod": "StateTransition",
      "title": "Squat state transition DOWN → UP (count increments)",
      "precondition": "Current state=DOWN after a valid squat",
      "input": "POST /api/analytics/pose with landmarks showing rising motion (angle increasing above 160°)",
      "steps": "Send frames from squat to standing",
      "expected": "State changes to UP, count increments by 1",
      "priority": "high"
    },
    {
      "id": "TC-ST-003",
      "designMethod": "StateTransition",
      "title": "Squat cooldown → UP after valid rep",
      "precondition": "Just completed a rep, system in cooldown period",
      "input": "POST /api/analytics/pose with standing pose after cooldown frames",
      "steps": "Wait for cooldown frames (10 frames) then send standing pose",
      "expected": "State becomes UP, new rep can be started",
      "priority": "medium"
    },
    {
      "id": "TC-ST-004",
      "designMethod": "StateTransition",
      "title": "Pushup state UP → DOWN",
      "precondition": "Pushup analyzer, state=UP",
      "input": "POST /api/analytics/pose with elbow flexion increasing (chest lowering)",
      "steps": "Send frames from plank top to chest near ground",
      "expected": "State becomes DOWN, count unchanged",
      "priority": "high"
    },
    {
      "id": "TC-ST-005",
      "designMethod": "StateTransition",
      "title": "Pushup state DOWN → UP (count increments)",
      "precondition": "State=DOWN",
      "input": "POST /api/analytics/pose with arms extending, shoulders rising",
      "steps": "Send frames pushing up",
      "expected": "State becomes UP, count increments by 1",
      "priority": "high"
    },
    {
      "id": "TC-ST-006",
      "designMethod": "StateTransition",
      "title": "Plank IDLE → ACTIVE (timer starts)",
      "precondition": "Plank analyzer, state=IDLE",
      "input": "POST /api/analytics/pose with landmarks showing straight body line (shoulders, hips, ankles aligned)",
      "steps": "Send frames of stable plank position",
      "expected": "State becomes ACTIVE, timer starts counting duration",
      "priority": "high"
    },
    {
      "id": "TC-COMB-001",
      "designMethod": "Combinatorial",
      "title": "SQUAT + exact 33 landmarks + high visibility",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [33 landmarks with visibility 0.9] }",
      "steps": "Send valid combination",
      "expected": "HTTP 200 OK, proper analysis",
      "priority": "high"
    },
    {
      "id": "TC-COMB-002",
      "designMethod": "Combinatorial",
      "title": "PUSHUP + length 32 landmarks + medium visibility",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"PUSHUP\", \"landmarks\": [32 landmarks with visibility 0.5] }",
      "steps": "Invalid landmarks length",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-COMB-003",
      "designMethod": "Combinatorial",
      "title": "PLANK + exact 33 landmarks + zero visibility",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"PLANK\", \"landmarks\": [33 landmarks with visibility 0.0] }",
      "steps": "Valid length but zero visibility",
      "expected": "HTTP 200 OK, but feedback indicates poor visibility",
      "priority": "medium"
    },
    {
      "id": "TC-COMB-004",
      "designMethod": "Combinatorial",
      "title": "JUMPING_JACK + length 34 landmarks + high visibility",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"JUMPING_JACK\", \"landmarks\": [34 landmarks with visibility 0.9] }",
      "steps": "Invalid length",
      "expected": "HTTP 400 Bad Request",
      "priority": "high"
    },
    {
      "id": "TC-COMB-005",
      "designMethod": "Combinatorial",
      "title": "SQUAT + length 33 + low visibility (0.1)",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"SQUAT\", \"landmarks\": [33 landmarks with visibility 0.1] }",
      "steps": "Low but non-zero visibility",
      "expected": "HTTP 200 OK, feedback may warn about detection confidence",
      "priority": "medium"
    },
    {
      "id": "TC-COMB-006",
      "designMethod": "Combinatorial",
      "title": "Invalid exercise type + length 33 + high visibility",
      "precondition": "None",
      "input": "POST /api/analytics/pose { \"exerciseType\": \"INVALID\", \"landmarks\": [33 landmarks with visibility 0.9] }",
      "steps": "Invalid type",
      "expected": "HTTP 400 Bad Request",
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
    "Exact error message formats for 400 responses not specified in requirements",
    "Performance metrics (response time) not required for black-box functional testing",
    "Authentication/authorization mechanisms not described",
    "Database transaction rollback behavior on partial failures"
  ],
  "assumptions": [
    "User with userId=1 exists and is valid for testing",
    "Backend validation for visibility range [0,1] is enforced; negative values would be rejected",
    "State transition tests assume the analyzer maintains session state per exercise type per user (implementation detail but necessary for state testing)",
    "Cooldown period is 10 frames as mentioned in FitnessAI.md",
    "The system returns appropriate JSON error bodies for 400 responses, though exact fields not specified"
  ]
}
```