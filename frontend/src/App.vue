<script setup lang="ts">
import { reactive, ref } from 'vue'

type Capability = {
  title: string
  desc: string
  tag: string
}

type WorkflowStep = {
  title: string
  detail: string
  gate: string
}

type MetricItem = {
  value: string
  label: string
  note: string
}

type FaqItem = {
  q: string
  a: string
}

const navItems = [
  { href: '#capabilities', label: '核心能力' },
  { href: '#workflow', label: '训练闭环' },
  { href: '#metrics', label: '指标体系' },
  { href: '#faq', label: '常见问题' },
]

const capabilities: Capability[] = [
  {
    title: '本地规则可配置',
    desc: '支持四人杭麻、财神、吃碰杠胡与座位轮换。可快速扩展到不同市场方言规则。',
    tag: 'Rule-First',
  },
  {
    title: '可控训练路径',
    desc: 'RuleBot 冷启动 + BC 预热 + MaskablePPO 微调，训练过程可验收、可回放、可复现。',
    tag: 'Train-Ready',
  },
  {
    title: '面向商业评测',
    desc: 'Duplicate 固定牌山评测，减少方差噪声，支持版本对比与上线前风控门禁。',
    tag: 'Market-Proof',
  },
  {
    title: '工程化交付',
    desc: '测试门禁、日志模板、任务队列与运行手册齐备，可直接进入团队协作与持续交付。',
    tag: 'Ops-Safe',
  },
]

const workflow: WorkflowStep[] = [
  {
    title: '规则引擎与环境建模',
    detail: '定义 47 动作空间、obs 契约与 mask 防线，先保证环境稳定可训练。',
    gate: 'Mask never all-false',
  },
  {
    title: 'RuleBot 产数据 + BC 预热',
    detail: '通过合成牌谱快速让策略“先像人”，降低 RL 冷启动成本。',
    gate: 'Mask-aware supervised loss',
  },
  {
    title: 'MaskablePPO 微调',
    detail: '在合法动作约束下迭代策略，持续记录训练元数据和版本产物。',
    gate: 'No NaN, reproducible seeds',
  },
  {
    title: 'Duplicate 复式评测',
    detail: '固定 seed + 座位轮换统计分差与置信区间，支撑真实产品化决策。',
    gate: 'CI95 + mean diff report',
  },
]

const metrics: MetricItem[] = [
  { value: '47', label: '离散动作空间', note: '含通用候选槽位 43~46' },
  { value: '40×4×9', label: '标准观测形状', note: '多通道决策语义编码' },
  { value: '1000 局', label: '稳定性回归门禁', note: '连续运行无崩溃' },
  { value: 'Duplicate', label: '低方差评测', note: '固定牌山 + 座位轮换' },
]

const faqs: FaqItem[] = [
  {
    q: '这个版本适合直接上线吗？',
    a: '适合做商业演示和封闭测试。要大规模上线，建议先扩充规则覆盖与大样本 Duplicate 评测。',
  },
  {
    q: '为什么不是直接从零开始强化学习？',
    a: '麻将动作空间复杂且方差高。先 BC 预热再 PPO 微调，收敛更快、成本更可控。',
  },
  {
    q: '如何证明模型真的在进步？',
    a: '以 Duplicate 固定 seed 对比不同版本 mean_diff、std_diff、ci95，而不是单看胜率。',
  },
  {
    q: '支持对手池 self-play 吗？',
    a: '支持。环境内可按比例替换旧策略对手，平滑引入 self-play 避免训练震荡。',
  },
]

const activeFaq = ref<number | null>(0)
const menuOpen = ref(false)
const submitting = ref(false)
const submitted = ref(false)
const submitError = ref('')

const form = reactive({
  name: '',
  email: '',
  company: '',
  goal: '',
})

const formErrors = reactive({
  name: '',
  email: '',
  goal: '',
})

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function toggleFaq(idx: number) {
  activeFaq.value = activeFaq.value === idx ? null : idx
}

function validateForm() {
  formErrors.name = form.name.trim() ? '' : '请输入姓名'
  formErrors.email = emailRegex.test(form.email.trim()) ? '' : '请输入有效邮箱'
  formErrors.goal = form.goal.trim() ? '' : '请填写你的业务目标'
  return !formErrors.name && !formErrors.email && !formErrors.goal
}

async function submitLead() {
  submitted.value = false
  submitError.value = ''
  if (!validateForm()) {
    return
  }
  submitting.value = true
  try {
    const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || ''
    const endpoint = apiBase ? `${apiBase.replace(/\/+$/, '')}/api/leads` : '/api/leads'
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: form.name.trim(),
        email: form.email.trim(),
        company: form.company.trim(),
        goal: form.goal.trim(),
      }),
    })

    if (!response.ok) {
      let message = '提交失败，请稍后重试。'
      try {
        const body = (await response.json()) as { detail?: string }
        if (body?.detail) {
          message = body.detail
        }
      } catch {
        // Keep fallback message when response is not json.
      }
      throw new Error(message)
    }

    submitted.value = true
    form.name = ''
    form.email = ''
    form.company = ''
    form.goal = ''
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : '网络异常，请稍后重试。'
  } finally {
    submitting.value = false
  }
}

const currentYear = new Date().getFullYear()
</script>

<template>
  <div class="page-shell">
    <header class="topbar">
      <a class="brand" href="#hero">
        <span class="brand-dot" />
        杭麻AI Studio
      </a>

      <nav class="desktop-nav">
        <a v-for="item in navItems" :key="item.href" :href="item.href">{{ item.label }}</a>
      </nav>

      <div class="topbar-actions">
        <a class="btn ghost" href="#workflow">查看方案</a>
        <a class="btn solid" href="#demo">预约演示</a>
        <button class="menu-toggle" type="button" @click="menuOpen = !menuOpen">
          {{ menuOpen ? '关闭' : '菜单' }}
        </button>
      </div>
    </header>

    <nav class="mobile-nav" :class="{ open: menuOpen }">
      <a v-for="item in navItems" :key="item.href" :href="item.href" @click="menuOpen = false">
        {{ item.label }}
      </a>
      <a href="#demo" @click="menuOpen = false">预约演示</a>
    </nav>

    <main>
      <section id="hero" class="hero reveal">
        <div class="hero-copy">
          <p class="eyebrow">Commercial-ready Hangzhou Mahjong AI</p>
          <h1>把“能跑通”升级为“能推广”的杭州麻将 AI 产品页面</h1>
          <p class="hero-desc">
            面向市场化推广，提供规则可配置、训练可控、评测可信的完整产品叙事。
            适合投资人演示、渠道合作、客户售前与团队内部对齐。
          </p>
          <div class="hero-actions">
            <a class="btn solid large" href="#demo">立即预约演示</a>
            <a class="btn ghost large" href="#metrics">查看核心指标</a>
          </div>
        </div>

        <div class="hero-card">
          <h3>产品上线前的三道门</h3>
          <ul>
            <li><span>01</span> 规则引擎与 mask 门禁稳定</li>
            <li><span>02</span> BC + PPO 训练产物可回放</li>
            <li><span>03</span> Duplicate 报告可比较可追踪</li>
          </ul>
          <div class="hero-mini-metrics">
            <div>
              <strong>7/7</strong>
              <p>测试门禁</p>
            </div>
            <div>
              <strong>47</strong>
              <p>动作维度</p>
            </div>
            <div>
              <strong>4 Seats</strong>
              <p>座位轮换</p>
            </div>
          </div>
        </div>
      </section>

      <section id="capabilities" class="section reveal">
        <div class="section-head">
          <p>Core Capabilities</p>
          <h2>市场化推广需要的不只是模型，更是可交付能力</h2>
        </div>

        <div class="cap-grid">
          <article v-for="cap in capabilities" :key="cap.title" class="cap-card">
            <p class="chip">{{ cap.tag }}</p>
            <h3>{{ cap.title }}</h3>
            <p>{{ cap.desc }}</p>
          </article>
        </div>
      </section>

      <section id="workflow" class="section reveal">
        <div class="section-head">
          <p>Product Workflow</p>
          <h2>从规则到评测，一条可复现的训练闭环</h2>
        </div>

        <div class="workflow-grid">
          <article v-for="(step, idx) in workflow" :key="step.title" class="workflow-card">
            <div class="workflow-top">
              <span class="idx">{{ String(idx + 1).padStart(2, '0') }}</span>
              <p>{{ step.gate }}</p>
            </div>
            <h3>{{ step.title }}</h3>
            <p>{{ step.detail }}</p>
          </article>
        </div>
      </section>

      <section id="metrics" class="section reveal">
        <div class="section-head">
          <p>Delivery Metrics</p>
          <h2>一眼看懂这个项目为什么“可商用推进”</h2>
        </div>

        <div class="metric-grid">
          <article v-for="item in metrics" :key="item.label" class="metric-card">
            <h3>{{ item.value }}</h3>
            <p class="metric-title">{{ item.label }}</p>
            <p class="metric-note">{{ item.note }}</p>
          </article>
        </div>
      </section>

      <section id="faq" class="section reveal">
        <div class="section-head">
          <p>FAQ</p>
          <h2>常见商业与技术问题</h2>
        </div>

        <div class="faq-list">
          <article v-for="(item, idx) in faqs" :key="item.q" class="faq-item">
            <button class="faq-q" type="button" @click="toggleFaq(idx)">
              <span>{{ item.q }}</span>
              <span class="faq-icon">{{ activeFaq === idx ? '−' : '+' }}</span>
            </button>
            <p v-if="activeFaq === idx" class="faq-a">{{ item.a }}</p>
          </article>
        </div>
      </section>

      <section id="demo" class="section demo reveal">
        <div class="demo-copy">
          <p>Book a Demo</p>
          <h2>把你的麻将业务想法，变成可验证的 AI 产品方案</h2>
          <p>
            留下你的需求，我们会基于当前引擎和训练框架提供一版演示计划，含成本估算与上线里程碑建议。
          </p>
        </div>

        <form class="lead-form" @submit.prevent="submitLead">
          <label>
            姓名
            <input v-model="form.name" type="text" placeholder="张三" />
            <small>{{ formErrors.name }}</small>
          </label>

          <label>
            邮箱
            <input v-model="form.email" type="email" placeholder="you@company.com" />
            <small>{{ formErrors.email }}</small>
          </label>

          <label>
            公司/团队
            <input v-model="form.company" type="text" placeholder="可选" />
          </label>

          <label>
            业务目标
            <textarea
              v-model="form.goal"
              rows="4"
              placeholder="例如：我们希望做杭州麻将线上陪练产品，首月目标 DAU 5000。"
            />
            <small>{{ formErrors.goal }}</small>
          </label>

          <button class="btn solid large submit" :disabled="submitting" type="submit">
            {{ submitting ? '提交中...' : '提交需求' }}
          </button>
          <p v-if="submitError" class="error-msg">{{ submitError }}</p>
          <p v-if="submitted" class="success-msg">已收到你的需求，我们会尽快联系你。</p>
        </form>
      </section>
    </main>

    <footer class="footer">
      <p>© {{ currentYear }} Hangzhou Mahjong AI Studio</p>
      <p>Powered by Vue3 + Vite · Rule Engine + BC + MaskablePPO + Duplicate Eval</p>
    </footer>
  </div>
</template>
