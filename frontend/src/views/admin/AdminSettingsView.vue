<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as settingsApi from '../../api/admin/settings'
import RefreshButton from '../../components/admin/RefreshButton.vue'
import type { SpxTranscodeStatus } from '../../types/settings'

const loading = ref(true)
const saving = ref(false)
// 运行时状态而非配置：容器里有没有 ffmpeg、已经转了多少
const spxStatus = ref<SpxTranscodeStatus | null>(null)
const redetecting = ref(false)

/**
 * 重新探测 ffmpeg。
 *
 * 后端默认把探测结果缓存在进程里（容器里的 ffmpeg 不会中途出现或消失），所以刚挂上
 * 必须让它重新探一次——否则这个按钮点了永远不变。
 */
async function redetectFfmpeg() {
  redetecting.value = true
  try {
    spxStatus.value = await settingsApi.getSpxTranscodeStatus(true)
    ElMessage.success(spxStatus.value.available ? '已检测到 ffmpeg' : '仍未检测到 ffmpeg')
  } finally {
    redetecting.value = false
  }
}

const form = reactive({
  open_access: false,
  allow_registration: true,
  spx_online_transcode: true,
  token_default_daily_limit: 1000,
  anonymous_ip_rate_limit_per_min: 60,
  user_ip_rate_limit_per_min: 120,
  vocab_max_items_per_owner: null as number | null,
  site_name: 'MyDict',
  search_hint_text: '小搜一下, 大进一步',
})

const vocabUnlimited = computed({
  get: () => form.vocab_max_items_per_owner === null,
  set: (unlimited: boolean) => {
    form.vocab_max_items_per_owner = unlimited ? null : 100
  },
})

async function load() {
  loading.value = true
  try {
    const [settings, spx] = await Promise.all([
      settingsApi.getSettings(),
      settingsApi.getSpxTranscodeStatus(),
    ])
    Object.assign(form, settings)
    spxStatus.value = spx
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function save() {
  saving.value = true
  try {
    const updated = await settingsApi.updateSettings({ ...form })
    Object.assign(form, updated)
    ElMessage.success('设置已保存')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="title-row">
      <h1>系统设置</h1>
      <RefreshButton :loading="loading" @refresh="load" />
    </div>

    <el-form label-position="top" class="settings-form">
      <section class="panel">
        <h2>开放使用</h2>
        <el-form-item>
          <div class="switch-row">
            <el-switch v-model="form.open_access" />
            <span>
              {{
                form.open_access
                  ? '已开启：访客可直接查询，匿名 API 调用也放行'
                  : '已关闭：查询需要登录或有效 Token'
              }}
            </span>
          </div>
        </el-form-item>
        <el-form-item>
          <div class="switch-row">
            <el-switch v-model="form.allow_registration" />
            <span>{{ form.allow_registration ? '允许用户自助注册' : '已关闭自助注册' }}</span>
          </div>
        </el-form-item>
      </section>

      <section class="panel">
        <h2>限流设置</h2>
        <el-form-item label="Token 默认每日调用上限">
          <el-input-number v-model="form.token_default_daily_limit" :min="1" style="width: 220px" />
        </el-form-item>
        <el-form-item label="匿名访问单 IP 每分钟请求上限">
          <el-input-number
            v-model="form.anonymous_ip_rate_limit_per_min"
            :min="1"
            style="width: 220px"
          />
        </el-form-item>
        <el-form-item label="登录用户单 IP 每分钟请求上限">
          <el-input-number
            v-model="form.user_ip_rate_limit_per_min"
            :min="1"
            style="width: 220px"
          />
        </el-form-item>
      </section>

      <section class="panel">
        <h2>生词本</h2>
        <el-form-item>
          <el-checkbox v-model="vocabUnlimited">不限容量</el-checkbox>
        </el-form-item>
        <el-form-item v-if="!vocabUnlimited" label="单用户/单 Token 生词本容量上限">
          <el-input-number v-model="form.vocab_max_items_per_owner" :min="1" style="width: 220px" />
        </el-form-item>
      </section>

      <section class="panel">
        <h2>站点信息</h2>
        <el-form-item label="站点名称">
          <el-input v-model="form.site_name" style="width: 320px" />
        </el-form-item>
        <el-form-item label="搜索提示语（登录用户在首页搜索框下方看到，限 100 字以内）">
          <el-input
            v-model="form.search_hint_text"
            maxlength="100"
            show-word-limit
            style="width: 320px"
          />
        </el-form-item>
      </section>

      <section class="panel">
        <h2>发音转码（ffmpeg）</h2>

        <p class="hint intro">
          ffmpeg 是<strong>可选</strong>依赖：没有它应用照常运行，只是「播放时就地转码」与
          词典管理页的「转码」按钮不可用（点缺少 mp3 的发音会提示格式不支持）。它不随镜像
          分发——GPL/LGPL 与本项目的 MIT 授权不兼容。
        </p>

        <el-form-item>
          <div class="switch-row">
            <el-switch
              v-model="form.spx_online_transcode"
              :disabled="!spxStatus || !spxStatus.available"
            />
            <span v-if="!spxStatus">正在检测 ffmpeg…</span>
            <span v-else-if="!spxStatus.available">容器里没有找到 ffmpeg，此项不可用</span>
            <span v-else-if="form.spx_online_transcode">
              已开启：播放缺少 mp3 的发音时就地转一个（约 60ms），产物落盘后复用
            </span>
            <span v-else>已关闭：缺少 mp3 的发音直接提示格式不支持</span>
          </div>
        </el-form-item>

        <div class="status-row">
          <span class="hint">
            当前状态：
            <template v-if="spxStatus?.available">
              已检测到 {{ spxStatus.ffmpeg_version ?? '未知版本' }}（{{ spxStatus.ffmpeg_path }}）；
              已转 {{ spxStatus.converted }} 个、失败 {{ spxStatus.failed }} 个，最多同时转
              {{ spxStatus.max_concurrent }} 个。
            </template>
            <template v-else>未检测到可用的 ffmpeg。</template>
          </span>
          <el-button size="small" :loading="redetecting" @click="redetectFfmpeg">
            重新检测
          </el-button>
        </div>

        <el-collapse class="install-guide">
          <el-collapse-item name="how">
            <template #title>如何安装 ffmpeg</template>

            <p class="step">
              <strong>A. 挂载静态构建（推荐）</strong>——不用改镜像，只挂一个二进制文件。
              静态构建自带依赖库，所以不需要再挂一堆 <code>.so</code>。
            </p>
            <pre class="code"># 1. 在宿主机下载（也可用任意静态构建源）
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar xf ffmpeg-release-amd64-static.tar.xz
install -m755 ffmpeg-*-static/ffmpeg /opt/mydict/ffmpeg

# 2. 在 compose 里加一行只读挂载
services:
  mydict:
    volumes:
      - ./data:/data
      - /opt/mydict/ffmpeg:/usr/local/bin/ffmpeg:ro

# 3. 重新部署，然后回本页点「重新检测」</pre>
            <p class="step">
              后端只在进程内探测一次，所以<strong>挂上之后必须重启容器</strong>，
              或者回本页点「重新检测」。
            </p>

            <p class="step">
              <strong>B. 不走容器，跑离线脚本</strong>——在宿主机执行：
            </p>
            <pre class="code">python3 scripts/transcode_spx.py --root &lt;词典资源目录&gt; --jobs 8 --prune-source</pre>
            <p class="step">
              加 <code>--dry-run</code> 可以先看工作量。转好的文件会被前端直接命中，
              与「播放时就地转码」不冲突。
            </p>

            <p class="step">
              <strong>C. 自建镜像</strong>——<code>FROM poxenstudio/mydict</code> 之后自行安装
              ffmpeg。注意这样分发会引入 GPL/LGPL 依赖，官方镜像刻意不做这件事。
            </p>
          </el-collapse-item>
        </el-collapse>
      </section>

      <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
    </el-form>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: var(--space-6) auto;
  padding: 0 var(--space-4);
}

.title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}

h1 {
  font-size: var(--text-xl);
  color: var(--color-text-primary);
  margin: 0;
}

.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevation-1);
  padding: var(--space-5);
  margin-bottom: var(--space-4);
}

.panel h2 {
  font-size: var(--text-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-4);
}

.switch-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.hint {
  margin: var(--space-3) 0 0;
  font-size: var(--text-xs);
  line-height: var(--leading-body);
  color: var(--color-text-tertiary);
}

.hint code {
  font-family: var(--font-family-mono);
  color: var(--color-text-secondary);
}

.intro {
  margin: 0 0 var(--space-4);
  line-height: var(--leading-body);
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.install-guide {
  margin-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.step {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xs);
  line-height: var(--leading-body);
  color: var(--color-text-secondary);
}

.code {
  margin: 0 0 var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  font-family: var(--font-family-mono);
  font-size: var(--text-xs);
  line-height: var(--leading-body);
  overflow-x: auto;
  white-space: pre;
}
</style>
