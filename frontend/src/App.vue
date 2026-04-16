<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const sourceType = ref("requirements");
const result = ref(null);
const loading = ref(false);
const status = ref("请导入文件并配置 Prompt 后生成黑盒测试 Markdown");
const historyRecords = ref([]);
const historyLoading = ref(false);
const deletingHistoryId = ref(null);
const activeHistoryRecord = ref(null);
const uploadedDocs = ref([]);
const chatPrompt = ref("");
const fileInputRef = ref(null);
const resultWindowRef = ref(null);
const resultScrollTop = ref(0);
const showSettings = ref(false);
const showHistoryModal = ref(false);

function openHistoryModal() {
  if (resultWindowRef.value) {
    resultScrollTop.value = resultWindowRef.value.scrollTop;
  }
  showHistoryModal.value = true;
}

function closeHistoryModal() {
  showHistoryModal.value = false;
  if (resultWindowRef.value) {
    resultWindowRef.value.scrollTop = resultScrollTop.value;
  }
}

function handleGlobalKeydown(event) {
  if (event.key !== "Escape") {
    return;
  }
  showSettings.value = false;
  closeHistoryModal();
}

marked.setOptions({ gfm: true, breaks: true });

const METHOD_SIGNALS = [
  {
    name: "EP",
    patterns: [/等价类/i, /equivalence\s*partition/i, /\bEP\b/i]
  },
  {
    name: "BVA",
    patterns: [/边界值/i, /boundary\s*value/i, /\bBVA\b/i]
  },
  {
    name: "组合",
    patterns: [/组合/i, /combinatorial/i, /pairwise/i]
  },
  {
    name: "状态迁移",
    patterns: [/状态迁移/i, /state\s*transition/i]
  },
  {
    name: "决策表",
    patterns: [/决策表/i, /decision\s*table/i]
  }
];

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function viewHistory(record) {
  const markdown = String(record.llmRawOutput || "").trim();
  activeHistoryRecord.value = {
    id: record.id,
    createdAt: record.createdAt,
    sourceType: record.sourceType,
    modelName: record.modelName
  };
  result.value = {
    message: "历史记录回填成功",
    technique: record.technique || "black-box",
    prompt: {
      version: record.promptVersion || "unknown",
      used: record.promptUsed || ""
    },
    llmRawOutput: record.llmRawOutput || "",
    data: {
      model: record.modelName || "unknown",
      testTechnique: record.technique || "black-box"
    }
  };

  status.value = `已加载历史记录 #${record.id}${markdown ? "（Markdown 已回填）" : ""}`;
  closeHistoryModal();
}

async function loadHistory(limit = 20) {
  historyLoading.value = true;
  try {
    const response = await fetch(`http://localhost:3000/api/history?limit=${limit}`);
    const payload = await response.json();
    historyRecords.value = response.ok ? (payload.records || []) : [];
    if (!response.ok) {
      status.value = payload.message || "历史记录加载失败";
    }
  } catch (_error) {
    historyRecords.value = [];
    status.value = "历史记录加载失败，请确认后端服务可用";
  } finally {
    historyLoading.value = false;
  }
}

async function deleteHistory(record) {
  if (!record?.id) {
    return;
  }

  const ok = window.confirm(`确认删除历史记录 #${record.id} 吗？此操作不可撤销。`);
  if (!ok) {
    return;
  }

  deletingHistoryId.value = record.id;
  try {
    const response = await fetch(`http://localhost:3000/api/history/${record.id}`, {
      method: "DELETE"
    });
    const payload = await response.json();
    if (!response.ok) {
      status.value = payload.message || "删除失败";
      return;
    }

    status.value = `已删除历史记录 #${record.id}`;
    if (activeHistoryRecord.value?.id === record.id) {
      activeHistoryRecord.value = null;
    }
    await loadHistory();
  } catch (_error) {
    status.value = "删除失败，请确认后端服务可用";
  } finally {
    deletingHistoryId.value = null;
  }
}

function onFileChange(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    return;
  }

  Promise.all(
    files.map(
      (file) =>
        new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            resolve({
              name: file.name,
              size: file.size,
              type: file.type || "text/plain",
              content: String(reader.result || "")
            });
          };
          reader.onerror = () => reject(new Error("read failed"));
          reader.readAsText(file, "utf-8");
        })
    )
  )
    .then((docs) => {
      uploadedDocs.value = [...uploadedDocs.value, ...docs];
      const totalChars = uploadedDocs.value.reduce((acc, item) => acc + item.content.length, 0);
      status.value = `已导入 ${uploadedDocs.value.length} 个文件（共 ${totalChars} 字符）`;
    })
    .catch(() => {
      status.value = "文件读取失败，请重试";
    });

  if (event.target) {
    event.target.value = "";
  }
}

function openFilePicker() {
  fileInputRef.value?.click();
}

function removeUploadedDoc(index) {
  uploadedDocs.value = uploadedDocs.value.filter((_, idx) => idx !== index);
  status.value = `已移除 1 个文件，当前 ${uploadedDocs.value.length} 个文件`;
}

function clearUploadedDocs() {
  uploadedDocs.value = [];
  status.value = "已清空已上传文件";
}

async function generateCases() {
  const hasDocuments = uploadedDocs.value.some((item) => String(item?.content || "").trim());
  if (!hasDocuments) {
    status.value = "请先上传至少一个文件后再生成";
    return;
  }

  loading.value = true;
  result.value = null;
  activeHistoryRecord.value = null;
  const promptText = String(chatPrompt.value || "").trim();
  status.value = "AI 正在生成黑盒测试 Markdown...";

  try {
    const response = await fetch("http://localhost:3000/api/testcases/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceType: sourceType.value,
        content: "",
        promptMode: promptText ? "custom" : "default",
        customPrompt: promptText,
        documents: uploadedDocs.value.map((item) => ({
          name: item.name,
          type: item.type,
          content: item.content
        })),
        testTechnique: "black-box"
      })
    });
    result.value = await response.json();
    status.value = response.ok ? "生成完成" : "生成失败，请检查输入或服务状态";
    if (response.ok) {
      chatPrompt.value = "";
      await loadHistory();
    }
  } catch (error) {
    result.value = { message: "请求失败", detail: String(error) };
    status.value = "请求失败，请确认后端已启动";
  } finally {
    loading.value = false;
  }
}

const markdownStats = computed(() => {
  const text = String(result.value?.llmRawOutput || "").trim();
  if (!text) {
    return null;
  }

  const coveredMethods = METHOD_SIGNALS.filter((signal) => signal.patterns.some((pattern) => pattern.test(text))).map(
    (signal) => signal.name
  );
  const missingMethods = METHOD_SIGNALS.filter((signal) => !coveredMethods.includes(signal.name)).map((signal) => signal.name);

  return {
    coveredMethods,
    missingMethods
  };
});

function exportMarkdown() {
  const markdown = String(result.value?.llmRawOutput || "").trim();
  if (!markdown) {
    status.value = "当前没有可导出的内容";
    return;
  }

  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `blackbox-testcases-${Date.now()}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  status.value = "Markdown 报告已导出";
}

const markdownPreviewHtml = computed(() => {
  const raw = String(result.value?.llmRawOutput || "").trim();
  if (!raw) {
    return "";
  }

  const html = marked.parse(raw);
  return DOMPurify.sanitize(String(html));
});

const assistantSummary = computed(() => {
  if (!result.value) {
    return "";
  }
  return result.value.message || "已返回结果";
});

onMounted(() => {
  window.addEventListener("keydown", handleGlobalKeydown);
  loadHistory();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
});
</script>

<template>
  <main class="page">
    <header class="topbar">
      <div>
        <p class="eyebrow">Assignment1 Black-box Studio</p>
        <h1>FitnessAI LLM Workspace</h1>
      </div>
      <p class="status">{{ status }}</p>
      <div class="topbar-actions">
        <div class="settings-wrap">
          <button class="ghost small-btn" @click="showSettings = !showSettings">会话设置</button>

          <section class="settings-popover" v-if="showSettings">
            <div class="panel-head compact">
              <h2>会话设置</h2>
              <button class="ghost small-btn" @click="showSettings = false">关闭</button>
            </div>
            <label>
              来源类型
              <select v-model="sourceType">
                <option value="requirements">需求文档</option>
                <option value="codebase">代码仓库/模块</option>
              </select>
            </label>
            <div class="uploaded-box compact" v-if="uploadedDocs.length">
              <p class="msg">已挂载 {{ uploadedDocs.length }} 个文件</p>
              <ul class="uploaded-list compact">
                <li v-for="(item, index) in uploadedDocs" :key="item.name + item.size + index">
                  <span>{{ item.name }}</span>
                  <button class="ghost mini" @click="removeUploadedDoc(index)">移除</button>
                </li>
              </ul>
              <button class="ghost" @click="clearUploadedDocs">清空全部文件</button>
            </div>
          </section>
        </div>
        <button class="ghost small-btn" @click="openHistoryModal">历史记录</button>
      </div>
    </header>

    <section class="chat-stage">
      <article class="panel result" v-if="result">
        <div class="result-head">
          <div>
            <h2>结果显示区</h2>
            <p class="msg">{{ assistantSummary || "等待生成回复" }}</p>
          </div>
          <div class="result-tools">
            <span class="badge">{{ result?.data?.model || "assistant" }}</span>
            <button class="ghost export-main-btn" v-if="result" @click="exportMarkdown">导出 Markdown</button>
          </div>
        </div>

        <div class="history-focus" v-if="activeHistoryRecord">
          当前回填: #{{ activeHistoryRecord.id }} · {{ activeHistoryRecord.sourceType }} ·
          {{ formatDate(activeHistoryRecord.createdAt) }}
        </div>

        <div class="result-window" v-if="result" ref="resultWindowRef">
          <div class="artifact" v-if="result.prompt?.version || result.data?.model">
            <p><b>Prompt 版本:</b> {{ result.prompt?.version || "unknown" }}</p>
            <p><b>模型:</b> {{ result.data?.model || "unknown" }}</p>
          </div>

          <div class="chips" v-if="markdownStats?.coveredMethods?.length">
            <span v-for="method in markdownStats.coveredMethods" :key="method" class="chip ok">{{ method }}</span>
          </div>
          <div class="chips" v-if="markdownStats?.missingMethods?.length">
            <span v-for="method in markdownStats.missingMethods" :key="method" class="chip warn">未检出 {{ method }}</span>
          </div>

          <div class="markdown-view" v-if="markdownPreviewHtml">
            <h3>LLM 输出</h3>
            <div class="markdown-body" v-html="markdownPreviewHtml"></div>
          </div>
        </div>

      </article>

      <article class="panel result empty-result" v-else>
        <h2>结果显示区</h2>
        <p class="msg">请在页面底部输入 Prompt 并上传文件后发送，结果会显示在这里。</p>
      </article>
    </section>

    <div class="history-modal" v-if="showHistoryModal" @click.self="closeHistoryModal">
      <section class="history-dialog panel">
        <div class="panel-head">
          <h2>历史记录</h2>
          <div class="panel-tools">
            <button class="ghost small-btn" :disabled="historyLoading" @click="loadHistory()">
              {{ historyLoading ? "刷新中..." : "刷新" }}
            </button>
            <button class="ghost small-btn" @click="closeHistoryModal">关闭</button>
          </div>
        </div>
        <p class="msg">共 {{ historyRecords.length }} 条记录，点击“查看详情”可回填。</p>

        <div class="history-list" v-if="historyRecords.length">
          <article
            class="history-item"
            :class="{ active: activeHistoryRecord?.id === item.id }"
            v-for="item in historyRecords"
            :key="item.id"
          >
            <header>
              <h3>#{{ item.id }} · {{ item.sourceType }} · {{ item.modelName }}</h3>
              <span class="badge">{{ formatDate(item.createdAt) }}</span>
            </header>
            <p><b>摘要:</b> {{ item.sourceSummary || "-" }}</p>
            <div class="history-actions">
              <button class="ghost" @click="viewHistory(item)">查看详情</button>
              <button
                class="ghost danger"
                :disabled="deletingHistoryId === item.id"
                @click="deleteHistory(item)"
              >
                {{ deletingHistoryId === item.id ? "删除中..." : "删除" }}
              </button>
            </div>
          </article>
        </div>

        <p class="msg" v-else>暂无历史输出，请先生成一次测试用例。</p>
      </section>
    </div>

    <section class="composer-shell">
      <input
        ref="fileInputRef"
        class="hidden-file-input"
        type="file"
        multiple
        accept=".md,.txt,.json,.java,.ts,.js,.py,.vue,.yaml,.yml"
        @change="onFileChange"
      />
      <div class="composer-files" v-if="uploadedDocs.length">
        <span class="composer-file" v-for="(item, index) in uploadedDocs" :key="item.name + item.size + index">
          {{ item.name }}
          <button class="composer-file-remove" @click="removeUploadedDoc(index)">×</button>
        </span>
      </div>
      <div class="composer-row">
        <textarea
          v-model="chatPrompt"
          rows="2"
          class="composer-input"
          placeholder="输入 Prompt，或留空使用默认 Prompt..."
        ></textarea>
        <div class="composer-actions">
          <button class="ghost attach-btn" :disabled="loading" @click="openFilePicker">导入文件</button>
          <button class="primary send-btn" :disabled="loading" @click="generateCases">
            {{ loading ? "生成中" : "发送" }}
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
