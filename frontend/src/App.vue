<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api'

const tab = ref('home')
const busy = ref(false)
const message = ref('')
const error = ref('')
const stats = ref(null)
const words = ref([])
const sources = ref([])
const search = ref('')
const reviewMode = ref('visual')
const queue = ref([])
const revealed = ref(false)
const importText = ref('')
const importData = ref(null)
const preview = ref(null)
const importResult = ref(null)
const editing = ref(null)
const wordForm = ref(blankWord())
const sourceForm = ref({ name: '', type: 'reading', date: new Date().toISOString().slice(0, 10), description: '' })

function blankWord() {
  return { word: '', lemma: '', phonetic: '', meaningsText: 'n. | ', familyText: '', priority: 'normal', note: '', context: '' }
}

function flash(text, isError = false) {
  if (isError) error.value = text; else message.value = text
  setTimeout(() => { message.value = ''; error.value = '' }, 4000)
}

async function loadDashboard() { stats.value = await api.dashboard() }
async function loadWords() { words.value = await api.words(search.value) }
async function loadSources() { sources.value = await api.sources() }
async function switchTab(name) {
  tab.value = name
  try {
    if (name === 'home') await loadDashboard()
    if (name === 'words') await loadWords()
    if (name === 'sources') await loadSources()
    if (name === 'review') await loadQueue()
  } catch (e) { flash(e.message, true) }
}

const current = computed(() => queue.value[0])
async function loadQueue() {
  busy.value = true
  try { queue.value = await api.reviewQueue(reviewMode.value); revealed.value = false }
  catch (e) { flash(e.message, true) }
  finally { busy.value = false }
}
async function answer(rating) {
  if (!current.value) return
  try {
    await api.answer({ word_id: current.value.id, mode: reviewMode.value, rating })
    queue.value.shift(); revealed.value = false
  } catch (e) { flash(e.message, true) }
}

function parseMeanings(text) {
  return text.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const [pos, ...rest] = line.split('|')
    return { pos: pos.trim() || 'other', zh: rest.join('|').trim() }
  }).filter(x => x.zh)
}
async function saveWord() {
  const payload = {
    word: wordForm.value.word, lemma: wordForm.value.lemma || wordForm.value.word,
    phonetic: wordForm.value.phonetic || null, meanings: parseMeanings(wordForm.value.meaningsText),
    word_family: wordForm.value.familyText.split(',').map(x => x.trim()).filter(Boolean),
    priority: wordForm.value.priority, note: wordForm.value.note || null,
  }
  if (!editing.value) payload.context = wordForm.value.context || null
  try {
    if (editing.value) await api.updateWord(editing.value, payload); else await api.createWord(payload)
    flash(editing.value ? '词条已更新' : '词条已添加'); cancelEdit(); await loadWords()
  } catch (e) { flash(e.message, true) }
}
function editWord(word) {
  editing.value = word.id
  wordForm.value = { word: word.word, lemma: word.lemma, phonetic: word.phonetic || '',
    meaningsText: word.meanings.map(x => `${x.pos} | ${x.zh}`).join('\n'), familyText: word.word_family.join(', '),
    priority: word.priority, note: word.note || '', context: '' }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function cancelEdit() { editing.value = null; wordForm.value = blankWord() }
async function removeWord(word) {
  if (!confirm(`删除 “${word.word}” 及其所有复习和遭遇记录？`)) return
  try { await api.deleteWord(word.id); await loadWords(); flash('已删除') } catch (e) { flash(e.message, true) }
}

async function addSource() {
  try { await api.createSource({ ...sourceForm.value, date: sourceForm.value.date || null }); await loadSources(); flash('来源已添加') }
  catch (e) { flash(e.message, true) }
}
async function removeSource(source) {
  if (!confirm(`删除来源 “${source.name}” 及其遭遇记录？词条本身会保留。`)) return
  try { await api.deleteSource(source.id); await loadSources(); flash('来源已删除') } catch (e) { flash(e.message, true) }
}

function parseImport() {
  try { importData.value = JSON.parse(importText.value); preview.value = null; importResult.value = null; return true }
  catch (e) { flash(`JSON 格式错误：${e.message}`, true); return false }
}
async function previewImport() {
  if (!parseImport()) return
  try { preview.value = await api.previewImport(importData.value) } catch (e) { flash(e.message, true) }
}
async function runImport() {
  if (!importData.value && !parseImport()) return
  try { importResult.value = await api.runImport(importData.value); preview.value = null; flash('导入完成') }
  catch (e) { flash(e.message, true) }
}
function loadFile(event) {
  const file = event.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { importText.value = reader.result; parseImport() }
  reader.readAsText(file)
}

const typeNames = { reading: '阅读', listening: '听力', writing: '写作', translation: '翻译', other: '其他' }
const priorityNames = { high: '重点', normal: '普通', low: '低频' }
onMounted(async () => { try { await loadDashboard() } catch (e) { flash('无法连接服务：' + e.message, true) } })
</script>

<template>
  <div class="shell">
    <header>
      <button class="brand" @click="switchTab('home')"><span class="brand-mark">L</span><span>Leo Vocabulary<small>真题驱动的 CET-4 词库</small></span></button>
      <nav>
        <button v-for="item in [['home','概览'],['review','复习'],['words','词库'],['import','导入'],['sources','来源']]" :key="item[0]" :class="{active:tab===item[0]}" @click="switchTab(item[0])">{{ item[1] }}</button>
      </nav>
    </header>

    <main>
      <div v-if="message" class="toast success">{{ message }}</div><div v-if="error" class="toast danger">{{ error }}</div>

      <section v-if="tab==='home'" class="page">
        <div class="hero"><div><p class="eyebrow">TODAY</p><h1>今天，认识几个真正遇到过的词。</h1><p>不是背一份陌生词表，而是补上你阅读里真实出现的缺口。</p></div><button class="primary big" @click="switchTab('review')">开始今日复习 →</button></div>
        <div v-if="stats" class="stat-grid">
          <article><span>今日待复习</span><strong>{{ stats.due_today }}</strong><small>视觉与听觉任务</small></article>
          <article><span>本周新词</span><strong>{{ stats.new_words }}</strong><small>近 7 天加入</small></article>
          <article><span>已掌握</span><strong>{{ stats.mastered }}</strong><small>视觉熟练度 ≥ 80</small></article>
          <article><span>词库总量</span><strong>{{ stats.total_words }}</strong><small>按 lemma 去重</small></article>
        </div>
        <div v-if="stats" class="two-col">
          <article class="panel"><div class="panel-title"><h2>近期来源</h2><button class="link" @click="switchTab('sources')">全部来源</button></div>
            <div v-if="!stats.recent_sources.length" class="empty">还没有导入记录。</div>
            <div v-for="s in stats.recent_sources" :key="s.id" class="row"><span class="source-icon">{{ s.type==='listening'?'耳':'阅' }}</span><div><b>{{ s.name }}</b><small>{{ typeNames[s.type] }} · {{ s.date || '未注明日期' }}</small></div><strong>{{ s.count }} 词</strong></div>
          </article>
          <article class="panel"><div class="panel-title"><h2>最顽固的词</h2><span class="muted">按忘记次数</span></div>
            <div v-if="!stats.stubborn_words.length" class="empty">复习后，这里会显示需要重点照顾的词。</div>
            <div v-for="w in stats.stubborn_words" :key="w.id" class="row"><div><b>{{ w.word }}</b><small>{{ w.lemma }}</small></div><span class="pill warm">忘记 {{ w.lapses }} 次</span></div>
          </article>
        </div>
      </section>

      <section v-if="tab==='review'" class="page narrow">
        <div class="page-head"><div><p class="eyebrow">REVIEW</p><h1>今日复习</h1></div><div class="segmented"><button :class="{active:reviewMode==='visual'}" @click="reviewMode='visual';loadQueue()">看词识义</button><button :class="{active:reviewMode==='audio'}" @click="reviewMode='audio';loadQueue()">听音识义</button></div></div>
        <div v-if="busy" class="empty">正在准备卡片…</div>
        <article v-else-if="current" class="review-card" @click="revealed=true">
          <div class="card-progress"><span>还剩 {{ queue.length }} 个</span><span>{{ reviewMode==='visual'?'视觉':'听觉' }}通道</span></div>
          <template v-if="reviewMode==='visual'"><h2>{{ current.word }}</h2><p class="phonetic">{{ current.phonetic || '暂无音标' }}</p></template>
          <template v-else><button class="sound" title="TTS 将在后续版本接入">♪</button><p class="muted">先回想这个词的读音与含义</p><h2 v-if="revealed">{{ current.word }}</h2></template>
          <button v-if="!revealed" class="reveal">点击查看答案</button>
          <div v-else class="answer"><div v-for="m in current.meanings" :key="m.pos+m.zh"><em>{{ m.pos }}</em> {{ m.zh }}</div><p v-if="current.encounters[0]?.context">“{{ current.encounters[0].context }}”</p></div>
        </article>
        <div v-if="current && revealed" class="ratings"><button @click="answer(0)"><b>忘了</b><small>明天再来</small></button><button @click="answer(1)"><b>模糊</b><small>需要巩固</small></button><button @click="answer(2)"><b>认识</b><small>正常推进</small></button><button class="good" @click="answer(3)"><b>秒懂</b><small>延长间隔</small></button></div>
        <article v-if="!busy && !current" class="done"><span>✓</span><h2>今天的任务完成了</h2><p>两个通道分别排期，切换通道可能还有卡片。</p><button class="secondary" @click="loadQueue">刷新队列</button></article>
      </section>

      <section v-if="tab==='words'" class="page">
        <div class="page-head"><div><p class="eyebrow">LIBRARY</p><h1>我的词库</h1></div><div class="search"><input v-model="search" @keyup.enter="loadWords" placeholder="搜索单词或 lemma"><button @click="loadWords">搜索</button></div></div>
        <details class="editor" :open="!!editing"><summary>{{ editing ? '编辑词条' : '手动添加词条' }}</summary>
          <form @submit.prevent="saveWord" class="form-grid"><label>单词<input v-model="wordForm.word" required></label><label>Lemma<input v-model="wordForm.lemma" placeholder="留空则同单词"></label><label>音标<input v-model="wordForm.phonetic" placeholder="/…/"></label><label>优先级<select v-model="wordForm.priority"><option value="high">重点</option><option value="normal">普通</option><option value="low">低频</option></select></label><label class="full">释义（每行：词性 | 中文）<textarea v-model="wordForm.meaningsText" required rows="3"></textarea></label><label class="full">词族（逗号分隔）<input v-model="wordForm.familyText"></label><label class="full">笔记<textarea v-model="wordForm.note" rows="2"></textarea></label><label v-if="!editing" class="full">首次语境<textarea v-model="wordForm.context" rows="2"></textarea></label><div class="full actions"><button class="primary" type="submit">{{ editing ? '保存修改' : '添加词条' }}</button><button v-if="editing" type="button" class="ghost" @click="cancelEdit">取消</button></div></form>
        </details>
        <div v-if="!words.length" class="empty panel">词库还是空的，可以手动添加或导入 JSON。</div>
        <div class="word-list"><article v-for="word in words" :key="word.id" class="word-item"><div class="word-main"><div><h2>{{ word.word }} <span>{{ word.phonetic }}</span></h2><p><template v-for="m in word.meanings" :key="m.pos+m.zh"><em>{{ m.pos }}</em> {{ m.zh }}　</template></p><small>lemma: {{ word.lemma }} · 遭遇 {{ word.encounter_count }} 次<span v-if="word.word_family.length"> · 词族 {{ word.word_family.join(', ') }}</span></small></div><span class="pill" :class="word.priority">{{ priorityNames[word.priority] }}</span></div><p v-if="word.encounters[0]?.context" class="context">“{{ word.encounters[0].context }}”</p><div class="item-actions"><button @click="editWord(word)">编辑</button><button class="danger-text" @click="removeWord(word)">删除</button></div></article></div>
      </section>

      <section v-if="tab==='import'" class="page narrow">
        <div class="page-head"><div><p class="eyebrow">IMPORT</p><h1>导入生词 JSON</h1><p class="muted">仅接受 Import Schema v1。先预览，再确认写入。</p></div><label class="file-button">选择 JSON 文件<input type="file" accept="application/json,.json" @change="loadFile"></label></div>
        <textarea class="json-editor" v-model="importText" spellcheck="false" placeholder='粘贴 {"schema_version":1,...}'></textarea>
        <div class="actions"><button class="secondary" @click="previewImport">校验并预览</button><button class="primary" :disabled="!preview" @click="runImport">确认导入</button></div>
        <article v-if="preview" class="panel result"><h2>预览通过</h2><div class="result-grid"><div><strong>{{ preview.total }}</strong><span>总记录</span></div><div><strong>{{ preview.create_count }}</strong><span>新建词条</span></div><div><strong>{{ preview.merge_count }}</strong><span>合并遭遇</span></div></div><p>来源将{{ preview.source_action==='create'?'新建':'复用' }}。重复 lemma 会合并释义与词族，并新增一条遭遇记录。</p></article>
        <article v-if="importResult" class="panel result"><h2>导入完成</h2><p>新建 {{ importResult.created }} 个词条，合并 {{ importResult.merged }} 个词条，新增 {{ importResult.encounters_added }} 次遭遇、{{ importResult.meanings_added }} 条释义、{{ importResult.family_members_added }} 个词族成员。</p></article>
      </section>

      <section v-if="tab==='sources'" class="page">
        <div class="page-head"><div><p class="eyebrow">SOURCES</p><h1>学习来源</h1></div></div>
        <form class="source-form panel" @submit.prevent="addSource"><input v-model="sourceForm.name" required placeholder="来源名称，如 2025-12 CET4 第一套"><select v-model="sourceForm.type"><option v-for="(name,key) in typeNames" :key="key" :value="key">{{ name }}</option></select><input v-model="sourceForm.date" type="date"><button class="primary">添加来源</button></form>
        <div v-if="!sources.length" class="empty">暂无来源。</div><div class="source-grid"><article v-for="source in sources" :key="source.id" class="panel source-card"><span class="source-icon">{{ source.type==='listening'?'耳':'阅' }}</span><div><h2>{{ source.name }}</h2><p>{{ typeNames[source.type] }} · {{ source.date || '未注明日期' }}</p><strong>{{ source.encounter_count }} 次遭遇</strong></div><button class="danger-text" @click="removeSource(source)">删除</button></article></div>
      </section>
    </main>
    <footer>Leo Vocabulary · v0.1 · 数据保存在你自己的服务器</footer>
  </div>
</template>
