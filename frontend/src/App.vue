<script setup>
import { ref } from "vue";

const sourceType = ref("requirements");
const content = ref("");
const result = ref(null);
const loading = ref(false);
const status = ref("可导入 FitnessAI.md 或粘贴需求/模块描述进行黑盒测试生成");

function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function onFileChange(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    content.value = String(reader.result || "");
    status.value = `已导入文件: ${file.name}（${content.value.length} 字符）`;
  };
  reader.onerror = () => {
    status.value = "文件读取失败，请重试";
  };
  reader.readAsText(file, "utf-8");
}

function fillFitnessDemo() {
  sourceType.value = "requirements";
  content.value = [
    "FitnessAI 健身系统黑盒测试范围:",
    "1) /api/analytics/pose 姿势分析接口，支持 SQUAT/PUSHUP/PLANK/JUMPING_JACK",
    "2) 计划模式与自由模式切换，包含组数、次数、休息时间",
    "3) 记录过滤规则：次数<3 且时长<30 秒不入库",
    "4) 用户档案更新与仪表盘统计接口"
  ].join("\n");
  status.value = "已填充 FitnessAI 场景示例，可直接生成";
}

async function generateCases() {
  if (!content.value.trim()) {
    status.value = "请输入内容后再生成";
    return;
  }

  loading.value = true;
  result.value = null;
  status.value = "AI 正在生成黑盒测试用例并计算覆盖度...";

  try {
    const response = await fetch("http://localhost:3000/api/testcases/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceType: sourceType.value,
        content: content.value,
        testTechnique: "black-box"
      })
    });
    result.value = await response.json();
    status.value = response.ok ? "生成完成" : "生成失败，请检查输入或服务状态";
  } catch (error) {
    result.value = { message: "请求失败", detail: String(error) };
    status.value = "请求失败，请确认后端已启动";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="page">
    <section class="hero">
      <div>
        <p class="eyebrow">Assignment1 Black-box Studio</p>
        <h1>FitnessAI 黑盒测试生成与评估平台</h1>
        <p class="lead">
          支持 EP、BVA、组合输入、状态迁移、决策表五类方法；自动生成用例、统计覆盖度并写入数据库。
        </p>
      </div>
      <p class="status">{{ status }}</p>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>输入区域</h2>

        <label>
          来源类型
          <select v-model="sourceType">
            <option value="requirements">需求文档</option>
            <option value="codebase">代码仓库/模块</option>
          </select>
        </label>

        <label>
          导入文件（推荐 FitnessAI.md）
          <input type="file" accept=".md,.txt,.json,.java,.ts,.js" @change="onFileChange" />
        </label>

        <label>
          输入内容
          <textarea v-model="content" rows="12" placeholder="粘贴需求文档、接口说明或模块描述"></textarea>
        </label>

        <div class="row">
          <button class="ghost" :disabled="loading" @click="fillFitnessDemo">填充 FitnessAI 示例</button>
          <button :disabled="loading" @click="generateCases">
            {{ loading ? "生成中..." : "生成黑盒测试用例" }}
          </button>
        </div>
      </article>

      <article class="panel result" v-if="result">
        <h2>结果总览</h2>
        <p class="msg">{{ result.message || "已返回结果" }}</p>

        <div class="metrics" v-if="result.quality">
          <div class="metric">
            <span>质量评分</span>
            <strong>{{ result.quality.qualityScore }}</strong>
          </div>
          <div class="metric">
            <span>方法覆盖度</span>
            <strong>{{ formatPercent(result.quality.methodCoverage) }}</strong>
          </div>
          <div class="metric">
            <span>用例数量</span>
            <strong>{{ result.quality.caseCount }}</strong>
          </div>
        </div>

        <div class="chips" v-if="result.quality?.coveredMethods?.length">
          <span v-for="method in result.quality.coveredMethods" :key="method" class="chip ok">{{ method }}</span>
        </div>
        <div class="chips" v-if="result.quality?.missingMethods?.length">
          <span v-for="method in result.quality.missingMethods" :key="method" class="chip warn">缺失 {{ method }}</span>
        </div>

        <div class="cases" v-if="result.data?.testcases?.length">
          <article class="case" v-for="item in result.data.testcases" :key="item.id">
            <header>
              <h3>{{ item.id }} · {{ item.title }}</h3>
              <span class="badge">{{ item.designMethod }} / {{ item.priority }}</span>
            </header>
            <p><b>前置条件:</b> {{ item.precondition }}</p>
            <p><b>输入:</b> {{ item.input }}</p>
            <p><b>步骤:</b> {{ item.steps }}</p>
            <p><b>预期:</b> {{ item.expected }}</p>
          </article>
        </div>

        <pre>{{ JSON.stringify(result, null, 2) }}</pre>
      </article>
    </section>
  </main>
</template>
