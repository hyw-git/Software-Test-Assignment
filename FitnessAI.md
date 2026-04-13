# FitnessAI - 智能健身辅助系统

<div align="center">

![FitnessAI](https://img.shields.io/badge/FitnessAI-1.0.0-blue)
![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.2.0-brightgreen)
![React](https://img.shields.io/badge/React-19.1.0-61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791)
![License](https://img.shields.io/badge/License-MIT-green)

**基于计算机视觉和人工智能的实时健身训练辅助系统**

[功能特性](#-核心功能) • [快速开始](#-快速开始) • [API 文档](#-api-接口文档) • [部署指南](#-部署指南)

</div>

---

## 📖 项目简介

FitnessAI 是一个**生产级的多层 Web 应用程序**，基于 Jakarta EE (Spring Boot 3.2.0) 平台构建，通过计算机视觉和生物力学分析提供智能、实时的健身指导。系统使用 MediaPipe Pose 技术实时检测 33 个身体关键点，通过角度计算和状态机算法实现精准的运动计数和姿势纠正。

### 🎯 项目亮点

- 🎥 **实时姿势分析** - 30 FPS 的实时身体关键点检测和分析
- 🏋️ **多运动支持** - 深蹲、俯卧撑、平板支撑、开合跳四种运动类型
- 📊 **智能计数** - 基于状态机的防误检算法，确保计数准确性
- 💡 **实时反馈** - 即时的动作纠正和鼓励提示
- 📈 **数据分析** - 完整的训练历史记录和可视化统计
- 🎨 **现代 UI** - 基于 React + TypeScript + Tailwind CSS 的响应式界面

---

## ✨ 核心功能

### 1. 实时姿势分析引擎

- **技术栈**: MediaPipe Pose (WASM) 客户端 + Spring Boot REST API 服务端
- **检测能力**: 33 个骨骼关键点（肩膀、肘部、臀部、膝盖、脚踝等）实时检测
- **处理速度**: 支持 30 FPS 的实时分析
- **分析算法**: 基于角度计算和有限状态机的智能分析

### 2. 智能反馈系统

- **状态机逻辑**: 每个运动类型实现独立的状态机（UP、DOWN、DESCENDING、ASCENDING）
- **防抖动机制**: 需要 2-3 连续帧确认状态转换，防止误检
- **冷却期机制**: 计数后 10 帧冷却期，防止重复计数
- **动态评分**: 根据动作深度和质量实时计算分数（0-100）

### 3. 双训练模式

- **自由模式**: 无时间或次数限制，可手动重置计数器
- **计划模式**: 结构化训练计划
  - **简单**: 2 组 × 10 次（深蹲），1 组 × 8 次（俯卧撑）
  - **中等**: 3 组 × 15 次（深蹲），2 组 × 12 次（俯卧撑）
  - **困难**: 4 组 × 20 次（深蹲），3 组 × 15 次（俯卧撑）
  - 包含休息间隔（30-60 秒）和跳过选项

### 4. 数据持久化与分析

- **数据存储**: Neon 云端 PostgreSQL 数据库
- **自动过滤**: 无效记录（次数 < 3 且时长 < 30 秒）自动过滤
- **可视化统计**: 
  - 活动趋势折线图
  - 卡路里消耗柱状图（最近 30 天）
  - 运动类型分布饼图
- **个性化仪表盘**: 卡路里消耗、进度追踪、历史数据

### 5. 用户档案管理

- **用户信息**: 身高、体重、目标（减重、增肌等）
- **BMI 计算**: 自动计算身体质量指数
- **卡路里估算**: 基于 MET（代谢当量）值的卡路里计算
  - 深蹲: 5.0 MET
  - 俯卧撑: 8.0 MET
  - 公式: `卡路里 = MET × 体重(kg) × 时长(小时)`

---

## 🏋️ 支持的运动类型

| 运动类型 | 检测方式 | 视角支持 | 检测方法 | 关键点 |
|---------|---------|---------|---------|--------|
| **深蹲 (Squat)** | 计数型 | 正面 | 髋-膝-踝角度监测 | 23-24 (臀部), 25-26 (膝盖), 27-28 (脚踝) |
| **俯卧撑 (Push-up)** | 计数型 | 正面 + 侧面 | 肘部弯曲和肩部高度追踪 | 11-12 (肩膀), 13-14 (肘部), 15-16 (手腕) |
| **平板支撑 (Plank)** | 计时型 | 正面 + 侧面 | 肩-髋-踝线性度分析 | 11-12 (肩膀), 23-24 (臀部), 27-28 (脚踝) |
| **开合跳 (Jumping Jack)** | 计数型 | 正面 | 垂直位移和手臂高度分析 | 15-16 (手腕), 11-12 (肩膀), 27-28 (脚踝) |

### 算法特点

- **深蹲**: 监测髋-膝-踝角度（阈值: 140°），支持左右腿独立分析
- **俯卧撑**: 追踪肘部弯曲角度和躯干对齐度，双臂独立计算
- **平板支撑**: 测量肩-髋-踝线性度，实时计时和质量评分
- **开合跳**: 检测垂直位移和手臂高度变化，完整动作循环检测

---

## 🛠️ 技术栈

### 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| **Spring Boot** | 3.2.0 | 应用框架 |
| **Spring Data JPA** | - | 数据访问层 |
| **Spring Web** | - | RESTful API |
| **Spring Validation** | - | 数据验证 |
| **PostgreSQL** | 15 | 生产数据库 |
| **H2 Database** | - | 开发环境（可选） |
| **Apache Commons Math** | 3.6.1 | 数学计算 |
| **OpenCV** | 4.9.0 | 计算机视觉支持（可选） |
| **SpringDoc OpenAPI** | 2.2.0 | API 文档 |
| **Spring Boot Actuator** | - | 监控和健康检查 |

### 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| **React** | 19.1.0 | UI 框架 |
| **TypeScript** | 4.9.5 | 类型安全 |
| **MediaPipe Pose** | 0.5.1675469404 | 姿势检测 |
| **Tailwind CSS** | 3.4.17 | 样式框架 |
| **Recharts** | 2.15.3 | 数据可视化 |
| **Lucide React** | 0.511.0 | 图标库 |

### 开发工具

- **Maven** - 项目构建管理
- **Docker** - 容器化部署
- **Git** - 版本控制

---

## 📁 项目结构

```
FitnessAI/
├── FitnessAI-Java/              # 后端服务
│   ├── src/main/java/com/fitnessai/
│   │   ├── FitnessAiApplication.java    # 主应用程序
│   │   ├── config/                      # 配置类
│   │   │   ├── CorsConfig.java          # CORS 跨域配置
│   │   │   └── DatabaseHealthIndicator.java  # 数据库健康检查
│   │   ├── controller/                  # 控制器层
│   │   │   ├── MainController.java       # 主控制器
│   │   │   ├── ExerciseController.java  # 运动分析 API
│   │   │   └── UserController.java      # 用户管理 API
│   │   ├── service/                     # 业务逻辑层
│   │   │   └── UserService.java         # 用户服务
│   │   ├── model/                       # 数据模型
│   │   │   ├── ExerciseType.java        # 运动类型枚举
│   │   │   ├── PoseLandmark.java        # 姿势关键点模型
│   │   │   ├── User.java                # 用户实体
│   │   │   ├── ExerciseRecord.java      # 运动记录实体
│   │   │   └── DailyStats.java          # 每日统计实体
│   │   ├── dto/                         # 数据传输对象
│   │   │   ├── PoseAnalysisRequest.java
│   │   │   └── PoseAnalysisResponse.java
│   │   ├── analyzer/                    # 姿势分析器
│   │   │   ├── PoseAnalyzer.java        # 分析器基类
│   │   │   ├── PoseAnalyzerFactory.java # 工厂类
│   │   │   ├── SquatAnalyzer.java       # 深蹲分析器
│   │   │   ├── PushupAnalyzer.java      # 俯卧撑分析器
│   │   │   ├── PlankAnalyzer.java       # 平板支撑分析器
│   │   │   └── JumpingJackAnalyzer.java # 开合跳分析器
│   │   └── repository/                  # 数据访问层
│   │       ├── UserRepository.java
│   │       ├── ExerciseRecordRepository.java
│   │       └── DailyStatsRepository.java
│   ├── src/main/resources/
│   │   ├── application.properties        # 应用配置
│   │   └── cleanup_invalid_records.sql  # 数据清理脚本
│   ├── pom.xml                          # Maven 配置
│   └── Dockerfile                       # Docker 镜像配置
│
├── frontend/                           # 前端应用
│   ├── src/
│   │   ├── components/                 # React 组件
│   │   │   ├── CameraView.tsx          # 摄像头视图
│   │   │   ├── Dashboard.tsx          # 仪表盘
│   │   │   ├── ExerciseSelector.tsx   # 运动选择器
│   │   │   ├── TrainingMode.tsx        # 训练模式
│   │   │   ├── StatsPanel.tsx          # 统计面板
│   │   │   └── ...
│   │   ├── hooks/
│   │   │   └── usePoseDetection.ts     # 姿势检测 Hook
│   │   ├── services/
│   │   │   └── api.ts                  # API 服务
│   │   ├── utils/
│   │   │   └── apiTest.ts              # API 测试工具
│   │   └── App.tsx                     # 主应用组件
│   ├── package.json                    # 依赖配置
│   ├── tailwind.config.js              # Tailwind 配置
│   └── Dockerfile                      # Docker 镜像配置
│
├── docker-compose.yml                  # Docker Compose 配置
├── DEVELOPMENT_GUIDE.md               # 开发指南
├── PROJECT_REPORT.md                   # 项目报告
└── README.md                           # 项目说明（本文件）
```

---

## 🚀 快速开始

### 环境要求

| 工具 | 版本 | 说明 |
|------|------|------|
| **Java JDK** | 17+ | 后端运行环境 |
| **Node.js** | 18+ | 前端运行环境 |
| **Maven** | 3.6+ | 后端构建工具（可选，IDE 也可） |
| **Docker** | 20+ | 容器化部署（可选） |
| **Git** | 任意 | 版本控制 |

### 方式一：本地开发

#### 1. 克隆项目

```bash
git clone <repository-url>
cd FitnessAI
```

#### 2. 启动后端服务

```bash
cd FitnessAI-Java

# 编译项目
mvn clean compile

# 运行应用
mvn spring-boot:run

# 或打包后运行
mvn clean package
java -jar target/fitnessai-backend-1.0.0.jar
```

后端服务将在 `http://localhost:8080` 启动

#### 3. 启动前端应用

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm start
```

前端应用将在 `http://localhost:3000` 启动

#### 4. 访问应用

- **前端应用**: http://localhost:3000
- **后端 API**: http://localhost:8080
- **API 文档 (Swagger)**: http://localhost:8080/swagger-ui.html
- **健康检查**: http://localhost:8080/api/health
- **系统信息**: http://localhost:8080/api/system

### 方式二：Docker 部署

#### 使用 Docker Compose（推荐）

```bash
# 在项目根目录执行
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务启动后：
- **前端**: http://localhost:3000
- **后端**: http://localhost:8080

#### 单独构建 Docker 镜像

```bash
# 构建后端镜像
cd FitnessAI-Java
docker build -t fitnessai-backend .

# 构建前端镜像
cd ../frontend
docker build -t fitnessai-frontend .

# 运行容器
docker run -p 8080:8080 fitnessai-backend
docker run -p 3000:80 fitnessai-frontend
```

---

## 🌐 API 接口文档

### 基础接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api` | API 状态检查 |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/system` | 系统信息 |
| `GET` | `/api/exercises` | 获取支持的运动类型 |
| `GET` | `/api/recommendations` | 获取个性化推荐 |

### 姿势分析接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/analytics/pose` | 实时姿势分析 |
| `POST` | `/api/analyzer/reset/{exerciseType}` | 重置分析器状态 |

**请求示例** (`POST /api/analytics/pose`):

```json
{
  "exerciseType": "SQUAT",
  "landmarks": [
    {"x": 0.5, "y": 0.3, "z": 0.1, "visibility": 0.9},
    ...
  ]
}
```

**响应示例**:

```json
{
  "count": 5,
  "score": 85,
  "feedback": "很好！下蹲姿势正确，请站起来完成动作",
  "state": "DOWN",
  "angle": 120.5
}
```

### 用户管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/user/{userId}/profile` | 获取用户档案 |
| `PUT` | `/api/user/{userId}/profile` | 更新用户档案 |
| `POST` | `/api/user/{userId}/records` | 保存运动记录 |
| `GET` | `/api/user/{userId}/records` | 获取历史记录 |
| `GET` | `/api/user/{userId}/stats/today` | 获取今日统计 |
| `GET` | `/api/user/{userId}/stats/today/{exerciseType}` | 获取今日特定运动统计 |
| `GET` | `/api/user/{userId}/dashboard` | 获取仪表盘数据 |

### API 文档访问

访问 Swagger UI 查看完整的 API 文档和交互式测试界面：

```
http://localhost:8080/swagger-ui.html
```

---

## 📊 数据库配置

项目使用 **Neon 云端 PostgreSQL 数据库**，所有团队成员共享同一个数据库。

### 连接信息

```
Host:     ep-weathered-star-a1x699tf-pooler.ap-southeast-1.aws.neon.tech
Port:     5432
Database: neondb
Username: neondb_owner
Password: npg_Oqet2AQ4WlIc
SSL Mode: require
```

### 数据模型

- **User** - 用户信息（身高、体重、目标等）
- **ExerciseRecord** - 运动记录（运动类型、次数、时长、卡路里等）
- **DailyStats** - 每日统计（按运动类型聚合）

### 数据质量控制

系统自动过滤无效记录：
- 次数 < 3 次
- 时长 < 30 秒

这些记录不会写入数据库，确保数据质量。

---

## 🔧 开发指南

### 添加新的运动类型

1. 在 `ExerciseType` 枚举中添加新类型
2. 创建新的分析器类继承 `PoseAnalyzer`
3. 在 `PoseAnalyzerFactory` 中注册新分析器
4. 更新前端组件和 API 文档

**示例代码**:

```java
public class CustomAnalyzer extends PoseAnalyzer {
    @Override
    public PoseAnalysisResponse analyze(List<PoseLandmark> landmarks) {
        // 实现自定义分析逻辑
        return response;
    }

    @Override
    public ExerciseType getExerciseType() {
        return ExerciseType.CUSTOM;
    }
}
```

### 自定义分析算法

分析器基类 `PoseAnalyzer` 提供了以下核心方法：

- `calculateAngle()` - 计算三点角度
- `calculateDistance()` - 计算两点距离
- `isLandmarkVisible()` - 检查关键点可见性

### 前端开发

#### 添加新组件

```typescript
// src/components/NewComponent.tsx
import React from 'react';

export const NewComponent: React.FC = () => {
  return <div>新组件</div>;
};
```

#### API 调用

```typescript
import { api } from '../services/api';

// 调用 API
const response = await api.post('/api/analytics/pose', {
  exerciseType: 'SQUAT',
  landmarks: [...]
});
```

---

## 🧪 测试

### 后端测试

```bash
cd FitnessAI-Java

# 运行单元测试
mvn test

# 运行集成测试
mvn verify
```

### 前端测试

```bash
cd frontend

# 运行测试
npm test

# 构建生产版本
npm run build
```

### API 测试

1. 访问 Swagger UI: http://localhost:8080/swagger-ui.html
2. 使用 Postman 或 curl 测试接口
3. 查看前端 `src/utils/apiTest.ts` 中的测试工具

---

## 📈 性能特性

### 处理能力

- **实时处理**: 支持 30 FPS 的实时姿势分析
- **低延迟**: 单次分析延迟 < 10ms
- **内存效率**: 基于内存会话管理
- **并发支持**: 多用户同时在线

### 扩展性

- **微服务架构**: 可独立部署和扩展
- **数据库支持**: 可轻松切换到生产数据库
- **负载均衡**: 支持水平扩展
- **缓存机制**: Redis 集成（可选）

---

## 🔒 安全特性

- **CORS 配置**: 严格的跨域访问控制
- **输入验证**: 全面的请求参数验证
- **SQL 注入防护**: JPA 参数化查询
- **日志审计**: 完整的操作日志记录

---

## 🚀 部署指南

### 生产环境部署

#### 1. 环境变量配置

创建 `.env` 文件：

```env
# 数据库配置
SPRING_DATASOURCE_URL=jdbc:postgresql://your-db-host/dbname
SPRING_DATASOURCE_USERNAME=your-username
SPRING_DATASOURCE_PASSWORD=your-password

# 前端 API 地址
REACT_APP_API_URL=https://api.yourdomain.com
```

#### 2. 构建生产版本

```bash
# 后端
cd FitnessAI-Java
mvn clean package -DskipTests

# 前端
cd frontend
npm run build
```

#### 3. Docker 部署

```bash
docker-compose -f docker-compose.prod.yml up -d
```

#### 4. 监控和日志

- **健康检查**: http://your-domain/actuator/health
- **指标监控**: http://your-domain/actuator/metrics
- **日志管理**: 配置 ELK Stack 或类似工具

---

## 🆘 故障排除

### 常见问题

#### 1. CORS 错误

**问题**: 前端无法访问后端 API

**解决方案**:
- 检查 `CorsConfig.java` 中的允许来源配置
- 确认前端运行在 `http://localhost:3000`
- 检查浏览器控制台的错误信息

#### 2. 数据库连接失败

**问题**: 无法连接到 PostgreSQL 数据库

**解决方案**:
- 检查 `application.properties` 中的数据库配置
- 确认数据库服务正在运行
- 验证网络连接和防火墙设置
- 检查 SSL 模式配置

#### 3. 端口占用

**问题**: 端口 8080 或 3000 已被占用

**解决方案**:
- 修改 `application.properties` 中的 `server.port`
- 修改前端 `.env` 文件中的端口配置
- 使用 `netstat` 或 `lsof` 查找占用端口的进程

#### 4. MediaPipe 加载失败

**问题**: 前端无法加载 MediaPipe 模型

**解决方案**:
- 检查网络连接
- 清除浏览器缓存
- 确认浏览器支持 WebAssembly
- 检查浏览器控制台的错误信息

#### 5. 姿势检测不准确

**问题**: 运动计数不准确或误检

**解决方案**:
- 确保光线充足
- 保持摄像头稳定
- 确保身体关键点可见
- 调整摄像头角度和距离
- 检查算法参数（稳定帧数、冷却期等）

### 日志查看

**后端日志**:
```bash
# 查看应用日志
tail -f logs/application.log

# 或查看控制台输出
mvn spring-boot:run
```

**前端日志**:
- 打开浏览器开发者工具（F12）
- 查看 Console 和 Network 标签

**Docker 日志**:
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f frontend
```

---

## 📝 更新日志

### v1.0.0 (2024)

- ✨ 初始版本发布
- 🎯 支持四种运动类型（深蹲、俯卧撑、平板支撑、开合跳）
- 📊 完整的用户数据管理和统计功能
- 🎨 现代化 React + TypeScript 前端界面
- 🐳 Docker 容器化支持
- 📚 完整的 API 文档（Swagger）

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 来改进项目！

### 贡献流程

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 代码规范

- 遵循 Java 和 TypeScript 编码规范
- 添加必要的注释和文档
- 确保所有测试通过
- 更新相关文档

---

## 📄 许可证

本项目基于 MIT 许可证开源。

---

## 📚 相关文档

- [开发指南](DEVELOPMENT_GUIDE.md) - 详细的开发环境配置和开发流程
- [项目报告](PROJECT_REPORT.md) - 完整的项目技术文档和实现细节
- [后端 README](FitnessAI-Java/README.md) - 后端服务详细说明
- [前端 README](frontend/README.md) - 前端应用说明

---

## 🔗 相关链接

- [Spring Boot 官方文档](https://spring.io/projects/spring-boot)
- [React 官方文档](https://react.dev/)
- [MediaPipe Pose 文档](https://google.github.io/mediapipe/solutions/pose)
- [PostgreSQL 官方文档](https://www.postgresql.org/docs/)

---

<div align="center">

**FitnessAI** - 让健身更智能！ 🏃‍♀️💪

Made with ❤️ by FitnessAI Team

</div>

