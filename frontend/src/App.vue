<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import {
  Activity, Check, ChevronDown, CircleAlert, Code2,
  LoaderCircle, Search, Send, Shuffle, UserRound, X,
} from 'lucide-vue-next'
import FieldInput from './FieldInput.vue'
import ResultCard from './ResultCard.vue'
import AssistantText from './AssistantText.vue'
import ArticleList from './ArticleList.vue'
import { firstFields, knownLabels, moreFields, pickArguments } from './fields.js'

const caseValues = reactive({})
const sample = ref({})
const model = reactive({})
const catalogs = reactive({})
const activeArea = ref('case')
const source = ref('stdio')
const selected = ref('pf_ratio')
const catalogError = ref('')
const catalogBusy = ref(false)
const caseError = ref('')
const caseBusy = ref(false)
const caseResults = reactive({})
const toolResult = ref(null)
const scenario = ref(null)
const scenarioBusy = ref(false)
const demoDefaults = ref(false)
const toolBusy = ref(false)
const caseDescription = ref('')
const evidenceCase = ref('')
const evidenceTerms = ref('')
let caseVersion = 0
let chatController
const searchTool = 'pubmed_search_articles'
const fetchTool = 'pubmed_fetch_articles'
const researchBusy = ref(false)
const researchError = ref('')
const articles = ref([])
const selectedRecord = ref(null)
const researchNotice = ref('')
const agentAvailable = ref(false)
const chatBusy = ref(false)
const message = ref('')
const conversation = ref([])
const mcpLog = ref([])
const chatScroll = ref(null)
const logScroll = ref(null)
const packets = ref([])
const packetIndex = ref(0)
const inspector = ref(null)
const toolTitle = call => knownLabels[call.tool] || call.tool
const pretty = value => JSON.stringify(value, null, 2)
const packet = computed(() => packets.value[packetIndex.value])
const articlesCurrent = computed(() => evidenceCase.value === caseDescription.value.trim())
const toolArticles = computed(() => articleList(toolResult.value?.result))
const toolName = tool => knownLabels[tool.name] || tool.title

const targets = computed(() => scenario.value?.targets || [])
const caseFields = computed(() => Object.assign({}, ...targets.value.map(([kind, name]) =>
  catalogs[kind]?.find(tool => tool.name === name)?.schema.properties || {},
)))
const caseOrder = computed(() => [...new Set([...firstFields, ...moreFields, ...Object.keys(caseFields.value)])]
  .filter(key => key in caseFields.value))
const headlineFields = computed(() => caseOrder.value.filter(key => !moreFields.includes(key)))
const additionalFields = computed(() => caseOrder.value.filter(key => moreFields.includes(key)))
const catalog = computed(() => catalogs[source.value] || [])
const activeTool = computed(() => catalog.value.find(t => t.name === selected.value))
const formulaFields = computed(() => Object.entries(activeTool.value?.schema.properties || {})
  .filter(([key]) => source.value !== 'pubmed' || ['pmids', 'query', 'maxResults'].includes(key))
  .map(([key, field]) => [key, { ...field, title: {
    pmids: 'PMID через запятую', query: 'Поисковый запрос', maxResults: 'Число статей',
  }[key] || field.title || key }]))


async function json(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error('Не удалось выполнить запрос к приложению.')
  return response.json()
}

function keepCall(call) {
  packets.value.unshift(call)
  if (packets.value.length > 40) packets.value.pop()
  packetIndex.value = 0
}

function beginCall(source, tool) {
  const step = reactive({ source, tool, pending: true, call: null, error: '' })
  mcpLog.value.push(step)
  if (mcpLog.value.length > 40) mcpLog.value.shift()
  nextTick(() => {
    if (logScroll.value) logScroll.value.scrollTop = logScroll.value.scrollHeight
  })
  return step
}

function finishCall(step, call, version) {
  if (version !== caseVersion) return
  step.call = call
  step.pending = false
  keepCall(call)
}

async function invoke(source, tool, arguments_, teachingCase = false) {
  const version = caseVersion
  const step = beginCall(source, tool)
  try {
    const call = await json('/api/call', { source, tool, arguments: arguments_, teaching_case: teachingCase })
    finishCall(step, call, version)
    return call
  } catch (error) {
    step.pending = false
    step.error = error.message
    throw error
  }
}

async function loadCatalog(name) {
  if (catalogs[name]?.length) return
  const result = await json('/api/tools/' + name)
  if (result.error) throw new Error(result.error)
  catalogs[name] = result.tools
}

async function calculateCase() {
  const version = caseVersion
  const description = caseDescription.value.trim()
  caseBusy.value = true
  caseError.value = ''
  const results = await Promise.allSettled(targets.value.map(async ([kind, name]) => {
    await loadCatalog(kind)
    const tool = catalogs[kind].find(t => t.name === name)
    if (!tool) throw new Error('Шкала ' + knownLabels[name] + ' недоступна.')
    if (version !== caseVersion) return
    const result = await invoke(kind, name, pickArguments(tool.schema, caseValues))
    if (version === caseVersion) caseResults[name] = { ...result, description }
  }))
  if (version !== caseVersion) return
  const failure = results.find(result => result.status === 'rejected')
  if (failure) caseError.value = failure.reason.message
  caseBusy.value = false
}

function loadScenario(next) {
  caseVersion += 1
  chatController?.abort()
  chatBusy.value = false
  scenario.value = next
  for (const key of Object.keys(caseValues)) delete caseValues[key]
  Object.assign(caseValues, next.values)
  for (const key of Object.keys(caseResults)) delete caseResults[key]
  caseBusy.value = false
  caseError.value = ''
  conversation.value = []
  mcpLog.value = []
  packets.value = []
  packetIndex.value = 0
  toolResult.value = null
  if (inspector.value) inspector.value.open = false
  message.value = ''
  caseDescription.value = next.description
  evidenceCase.value = ''
  evidenceTerms.value = ''
  articles.value = []
  selectedRecord.value = null
  researchBusy.value = false
  researchError.value = ''
  researchNotice.value = ''
}

async function generateScenario() {
  if (scenarioBusy.value || !scenario.value) return
  scenarioBusy.value = true
  caseError.value = ''
  try {
    const previous = encodeURIComponent(scenario.value.id)
    loadScenario(await json('/api/scenario?previous=' + previous))
  } catch (error) { caseError.value = error.message }
  finally { scenarioBusy.value = false }
}

async function chooseSource(nextSource) {
  source.value = nextSource
  chooseTool('')
  catalogBusy.value = true
  catalogError.value = ''
  demoDefaults.value = false
  try {
    await loadCatalog(nextSource)
    if (source.value === nextSource) chooseTool(catalogs[nextSource][0]?.name || '')
  } catch (error) {
    if (source.value === nextSource) catalogError.value = error.message
  } finally {
    if (source.value === nextSource) catalogBusy.value = false
  }
}

function chooseTool(name) {
  selected.value = name
  for (const key of Object.keys(model)) delete model[key]
  toolResult.value = null
  demoDefaults.value = false
}

async function runTool() {
  if (!activeTool.value) return
  toolBusy.value = true
  catalogError.value = ''
  try {
    const arguments_ = pickArguments(activeTool.value.schema, model)
    // A blank teaching form uses the server preset; an unchecked visible flag is explicit.
    for (const [key, def] of formulaFields.value) {
      if (def.type === 'boolean' && !(key in arguments_) && !demoDefaults.value) arguments_[key] = false
    }
    const requestedSource = source.value
    const name = activeTool.value.name
    if (name === searchTool) {
      arguments_.maxResults ??= 4
      arguments_.summaryCount = Math.min(arguments_.maxResults,
        activeTool.value.schema.properties.summaryCount?.maximum ?? 50)
      arguments_.hasAbstract = true
    }
    if (name === fetchTool) arguments_.includeMesh = false
    const version = caseVersion
    const call = await invoke(requestedSource, name, arguments_, demoDefaults.value)
    if (version === caseVersion && source.value === requestedSource && selected.value === name) {
      toolResult.value = call
      if (!call.error) for (const key of call.defaults) model[key] = call.arguments[key]
    }
  } catch (error) { catalogError.value = error.message }
  finally { toolBusy.value = false }
}

function useToolExample() {
  const examples = {
    [searchTool]: { query: 'COPD pulmonary rehabilitation', maxResults: 4 },
    [fetchTool]: { pmids: [articles.value[0]?.pmid || '37286219'] },
  }
  const example = source.value === 'pubmed' ? examples[selected.value] : sample.value
  for (const key of Object.keys(model)) delete model[key]
  for (const [key] of formulaFields.value) if (key in (example || {})) model[key] = example[key]
  toolResult.value = null
}

function openToolArticle(article) {
  if (toolBusy.value) return
  chooseTool(fetchTool)
  model.pmids = [article.pmid]
  return runTool()
}

function inspectCall(call) {
  const index = packets.value.indexOf(call)
  if (index < 0) return
  packetIndex.value = index
  inspector.value.open = true
  inspector.value.scrollIntoView({ block: 'start' })
}

function articleList(result) {
  const items = result?.summaries || result?.articles
  if (!Array.isArray(items)) return []
  return items.filter(item => /^\d{1,12}$/.test(item.pmid || '') && item.title)
}

function showArticles(call, description) {
  articles.value = articleList(call.result)
  evidenceCase.value = description
  evidenceTerms.value = call.arguments.query || ''
  researchNotice.value = call.cached ? 'PubMed · из кэша' : 'PubMed'
  researchError.value = ''
  selectedRecord.value = null
}

async function findArticles() {
  const description = caseDescription.value.trim()
  if (!description || researchBusy.value) return
  const version = caseVersion
  const step = beginCall('pubmed', searchTool)
  researchBusy.value = true
  researchError.value = ''
  researchNotice.value = ''
  selectedRecord.value = null
  try {
    const result = await json('/api/evidence', { description, scenario: scenario.value?.id })
    if (version !== caseVersion) return
    if (result.call) finishCall(step, result.call, version)
    if (result.error) throw new Error(result.error)
    showArticles(result.call, description)
  } catch (error) {
    if (version !== caseVersion) return
    step.pending = false
    step.error = error.message
    articles.value = []
    evidenceCase.value = ''
    evidenceTerms.value = ''
    researchError.value = error.message
  } finally { if (version === caseVersion) researchBusy.value = false }
}

async function fetchArticle(article) {
  const version = caseVersion
  const record = reactive({ ...article, busy: true, error: '', abstractText: '' })
  selectedRecord.value = record
  try {
    const call = await invoke('pubmed', fetchTool, { pmids: [article.pmid], includeMesh: false })
    if (version !== caseVersion) return
    if (call.error) throw new Error(call.error)
    record.abstractText = articleList(call.result).find(item => item.pmid === article.pmid)?.abstractText || ''
  } catch (error) { record.error = error.message }
  finally { record.busy = false }
}

function goTo(area) {
  activeArea.value = area
  if (area === 'tools' && !catalog.value.length && !catalogBusy.value) chooseSource(source.value)
}

function showEvent(event, assistantRow, description, version) {
  if (version !== caseVersion) return
  if (event.type === 'tool_start') {
    assistantRow.step = beginCall(event.source, event.tool)
  } else if (event.type === 'tool') {
    const call = event.call
    finishCall(assistantRow.step || beginCall(call.source, call.tool), call, version)
    assistantRow.step = null
    const target = targets.value.some(([kind, name]) => kind === call.source && name === call.tool)
    if (!call.error && target && matchesCase(call) && caseDescription.value.trim() === description) {
      caseResults[call.tool] = { ...call, description }
    }
    if (!call.error && call.tool === searchTool && caseDescription.value.trim() === description) {
      showArticles(call, description)
    }
  } else if (event.type === 'done') {
    assistantRow.content = event.text || event.error || 'Ответ не получен.'
    assistantRow.error = Boolean(event.error)
  }
}

function matchesCase(call) {
  return Object.entries(call.arguments).every(([key, value]) => caseValues[key] === value)
}

async function send(text = message.value) {
  if (chatBusy.value || scenarioBusy.value || !text.trim() || !agentAvailable.value) return
  message.value = ''
  chatBusy.value = true
  const version = caseVersion
  const controller = new AbortController()
  chatController = controller
  const description = caseDescription.value.trim()
  conversation.value.push({ role: 'user', content: text.trim(), caseKey: description })
  const history = conversation.value.filter(row => !row.error && row.caseKey === description).slice(-12)
    .map(({ role, content }) => ({ role, content }))
  const assistantRow = reactive({ role: 'assistant', content: '', caseKey: description })
  conversation.value.push(assistantRow)
  const selection = articlesCurrent.value ? articles.value.slice(0, 8).map(article => ({
    pmid: article.pmid, title: article.title.slice(0, 500),
  })) : []
  const worksheet = description === scenario.value?.description
  const calculations = Object.values(caseResults)
    .filter(call => call.description === description && !call.error && matchesCase(call)
      && typeof call.result?.value === 'number')
    .map(call => ({ tool: call.tool, value: call.result.value, unit: call.result.unit || '' }))
  try {
    const response = await fetch('/api/agent', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({
        messages: history, description, articles: selection, calculations,
        case: worksheet
          ? pickArguments({ properties: caseFields.value }, caseValues) : {},
      }),
    })
    if (!response.ok || !response.body) throw new Error('Не удалось подключиться к агенту.')
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
    let partial = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      partial += value
      const lines = partial.split('\n')
      partial = lines.pop()
      for (const line of lines) if (line) showEvent(JSON.parse(line), assistantRow, description, version)
    }
    if (partial.trim()) showEvent(JSON.parse(partial), assistantRow, description, version)
    if (!assistantRow.content) throw new Error('Соединение с агентом прервалось.')
  } catch (error) {
    if (version !== caseVersion) return
    assistantRow.content = error.message
    assistantRow.error = true
  } finally {
    if (version === caseVersion) {
      if (assistantRow.step) {
        assistantRow.step.pending = false
        assistantRow.step.error = 'Вызов прерван.'
      }
      chatController = null
      chatBusy.value = false
      await nextTick()
      if (chatScroll.value) chatScroll.value.scrollTop = chatScroll.value.scrollHeight
    }
  }
}

onMounted(async () => {
  try {
    const [health, example] = await Promise.all([json('/api/health'), json('/api/scenario')])
    sample.value = example.values
    agentAvailable.value = health.agent
    loadScenario(example)
    await Promise.all([loadCatalog('stdio'), loadCatalog('sse')])
  } catch (error) { caseError.value = error.message }
})
</script>

<template>
  <header class="topbar">
    <a class="brand" href="#" @click.prevent="goTo('case')">
      <svg width="35" height="35" viewBox="0 0 36 36" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 3v9m0 0-5 6m5-6 5 6M14 11c-4-6-10 4-11 15-.4 4 1 6 4 5l6-3c2-1 2-3 2-6v-7c0-2 0-3-1-4Zm8 0c4-6 10 4 11 15 .4 4-1 6-4 5l-6-3c-2-1-2-3-2-6v-7c0-2 0-3 1-4Z"/>
      </svg> Respira Lab
    </a>
    <nav aria-label="Разделы">
      <button :aria-current="activeArea === 'case' ? 'page' : undefined"
              :class="{ active: activeArea === 'case' }" @click="goTo('case')">Учебный случай</button>
      <button :aria-current="activeArea === 'tools' ? 'page' : undefined"
              :class="{ active: activeArea === 'tools' }" @click="goTo('tools')">Инструменты</button>
    </nav>
    <span class="environment">Синтетические данные</span>
  </header>

  <main class="page">
    <div class="workspace" :class="{ 'tools-workspace': activeArea === 'tools' }">
      <section class="panel case-panel" aria-labelledby="case-heading">
        <h1 id="case-heading">{{ activeArea === 'tools' ? 'Инструменты' : 'Учебный случай' }}</h1>

        <template v-if="activeArea === 'case'">
          <article v-if="scenario" class="scenario-card">
            <h2>{{ scenario.title }}</h2>
            <p>{{ scenario.description }}</p>
            <button type="button" class="secondary scenario-button" :disabled="scenarioBusy" @click="generateScenario">
              <LoaderCircle v-if="scenarioBusy" class="spin" :size="17" /><Shuffle v-else :size="17" /> Новый случай
            </button>
          </article>
          <form @submit.prevent="calculateCase" class="case-form" novalidate>
            <FieldInput v-for="key in headlineFields" :key="key" :entry="caseFields[key]" :id="'case-' + key"
                        v-model="caseValues[key]" />
            <details v-if="additionalFields.length" class="extra">
              <summary>Дополнительные показатели <ChevronDown :size="16" /></summary>
              <FieldInput v-for="key in additionalFields" :key="key" :entry="caseFields[key]" :id="'case-' + key"
                          v-model="caseValues[key]" />
            </details>
            <button class="primary full" :disabled="caseBusy || scenarioBusy || !caseOrder.length">
              <LoaderCircle v-if="caseBusy" class="spin" :size="17" /> Рассчитать показатели
            </button>
            <p v-if="caseError" class="error" role="alert">{{ caseError }}</p>
          </form>
        </template>

        <template v-else>
          <div class="segmented" role="group" aria-label="Источник MCP">
            <button v-for="kind in ['stdio', 'sse', 'pubmed']" :key="kind" :class="{ active: source === kind }"
                    :aria-pressed="source === kind" @click="chooseSource(kind)">
              {{ knownLabels[kind] }}
            </button>
          </div>
          <label v-if="catalog.length" class="tool-picker">
            <span>Инструмент</span>
            <select :value="selected" @change="chooseTool($event.target.value)">
              <option v-for="item in catalog" :key="item.name" :value="item.name">{{ toolName(item) }}</option>
            </select>
          </label>
          <p v-if="catalogBusy" class="muted loading" role="status"><LoaderCircle class="spin" :size="16" /> Загружаю инструменты…</p>
          <form v-if="activeTool" class="case-form" @submit.prevent="runTool" novalidate>
            <p class="muted">{{ activeTool.specialty ? activeTool.specialty + ' · ' : '' }}{{ activeTool.description }}</p>
            <FieldInput v-for="[key, entry] in formulaFields" :key="key" :entry="entry" :id="'tool-' + key"
                        v-model="model[key]" />
            <button v-if="formulaFields.length" type="button" class="secondary full" @click="useToolExample">
              Подставить учебный пример
            </button>
            <label v-if="source === 'sse' && formulaFields.length" class="check-field">
              <input v-model="demoDefaults" type="checkbox" /> Smart Defaults для учебного примера
            </label>
            <button class="primary full" :disabled="toolBusy">
              <LoaderCircle v-if="toolBusy" class="spin" :size="17" /> Выполнить
            </button>
          </form>
          <p v-if="catalogError" class="error" role="alert">{{ catalogError }}
            <button v-if="!catalog.length" type="button" class="link-button" @click="chooseSource(source)">Повторить</button>
          </p>
        </template>
      </section>

      <section v-if="activeArea === 'case'" class="panel center-panel">
        <h2>Результаты</h2>
        <div class="score-grid">
          <ResultCard v-for="[kind, name] in targets" :key="name" :title="knownLabels[name]" :source="kind"
                      :outcome="caseResults[name]" :loading="caseBusy" />
        </div>
        <div class="section-rule"></div>
        <h2>Статьи по случаю</h2>
        <form class="case-search" @submit.prevent="findArticles">
          <label for="case-description">Описание учебного случая</label>
          <textarea id="case-description" v-model="caseDescription" maxlength="2500" rows="3"
                    placeholder="Например, ХОБЛ и легочная реабилитация после обострения" />
          <button type="submit" class="primary" :disabled="researchBusy || scenarioBusy || !caseDescription.trim()">
            <LoaderCircle v-if="researchBusy" class="spin" :size="17" /><Search v-else :size="17" />
            Подобрать статьи
          </button>
        </form>
        <p v-if="researchError" class="error" role="alert">{{ researchError }} <button class="link-button" @click="findArticles">Повторить</button></p>
        <p v-else-if="researchBusy" class="muted loading" role="status">
          <LoaderCircle class="spin" :size="16" /> Ищу статьи в PubMed…
        </p>
        <template v-else-if="articlesCurrent && researchNotice">
          <p class="muted study-attribution">{{ researchNotice }}<span v-if="evidenceTerms"> · {{ evidenceTerms }}</span></p>
          <ArticleList v-if="articles.length" :articles="articles" @select="fetchArticle" />
          <p v-else class="muted">Статей по этому случаю не найдено. Уточните описание.</p>
          <button v-if="articles.length && agentAvailable" type="button" class="secondary discuss-button"
                  :disabled="chatBusy || scenarioBusy"
                  @click="send('Сравни найденные статьи по аннотациям. Объясни, что в них полезно для разбора этого случая. Дай ссылки на PubMed.')">
            Обсудить статьи с агентом
          </button>
        </template>
        <p v-else-if="articles.length" class="muted study-attribution">Описание изменилось. Подберите статьи для нового случая.</p>
        <article v-if="selectedRecord && articlesCurrent" class="record">
          <div class="panel-heading">
            <h3>{{ selectedRecord.title }}</h3>
            <button class="icon-button" aria-label="Закрыть аннотацию" @click="selectedRecord = null"><X :size="17" /></button>
          </div>
          <p v-if="selectedRecord.busy" class="muted" role="status">Загружаю аннотацию…</p>
          <p v-else-if="selectedRecord.error" class="error" role="alert">{{ selectedRecord.error }}</p>
          <p v-else class="pre-line">{{ selectedRecord.abstractText || 'Аннотация недоступна в PubMed.' }}</p>
        </article>
      </section>

      <section v-else class="panel tool-output">
        <div class="panel-heading">
          <h2>Результат вызова</h2>
          <button v-if="toolResult" type="button" class="icon-button" title="Открыть пакеты"
                  aria-label="Открыть пакеты этого вызова" @click="inspectCall(toolResult)">
            <Code2 :size="21" />
          </button>
        </div>
        <p v-if="toolBusy" role="status" class="muted loading"><LoaderCircle class="spin" :size="17" /> Выполняю запрос…</p>
        <div v-else-if="!toolResult" class="tool-empty">
          <Code2 :size="25" /><p>Выберите инструмент, заполните параметры и нажмите «Выполнить».</p>
        </div>
        <template v-else>
          <p v-if="toolResult.cached" class="muted">Результат из кэша</p>
          <ResultCard v-if="toolResult.result?.components || toolResult.error" :title="toolTitle(toolResult)"
                      :source="toolResult.source" :outcome="toolResult" />
          <template v-else-if="toolResult.tool === searchTool">
            <ArticleList v-if="toolArticles.length" :articles="toolArticles" @select="openToolArticle" />
            <p v-else class="muted">Статей по этому запросу не найдено.</p>
          </template>
          <template v-else-if="toolResult.tool === fetchTool">
            <article v-for="item in toolArticles" :key="item.pmid" class="record">
              <h3>{{ item.title }}</h3>
              <a :href="'https://pubmed.ncbi.nlm.nih.gov/' + item.pmid + '/'"
                 target="_blank" rel="noopener noreferrer">PMID {{ item.pmid }}</a>
              <p class="pre-line">{{ item.abstractText || 'Аннотация недоступна в PubMed.' }}</p>
            </article>
            <p v-if="!toolArticles.length" class="muted">По указанным PMID статьи не найдены.</p>
          </template>
          <pre v-else class="json">{{ pretty(toolResult.result) }}</pre>
          <p v-if="toolResult.defaults.length" class="muted">Smart Defaults: {{ toolResult.defaults.join(', ') }}</p>
        </template>
      </section>

      <section class="panel agent-panel">
        <h2>Чат с агентом</h2>
        <div ref="chatScroll" class="chat-scroll" aria-live="polite">
          <template v-if="!conversation.length">
            <button v-if="scenario && caseDescription.trim() === scenario.description" class="demo-message" type="button" :disabled="!agentAvailable || scenarioBusy || caseBusy"
                    @click="send(scenario.prompt)">
              <UserRound :size="20" />
              <span><strong>Разобрать сценарий</strong><small>{{ scenario.prompt }}</small></span>
            </button>
          </template>
          <div v-for="(row, index) in conversation" :key="index" class="message" :class="[row.role, { error: row.error }]">
            <UserRound v-if="row.role === 'user'" :size="18" />
            <AssistantText v-if="row.role === 'assistant'" :text="row.content" />
            <span v-else>{{ row.content }}</span>
          </div>
          <p v-if="chatBusy" class="muted loading" role="status"><LoaderCircle class="spin" :size="16" /> Агент обрабатывает запрос…</p>
          <p v-if="!agentAvailable" class="muted">Для агента задайте ROUTERAI_API_KEY в локальном .env.</p>
        </div>
        <details class="workflow" open>
          <summary>MCP-вызовы <span class="workflow-count">{{ mcpLog.length }}</span><ChevronDown :size="17" /></summary>
          <ul ref="logScroll" aria-live="polite">
            <li v-if="!mcpLog.length" class="muted"><Activity :size="16" /> Здесь появятся вызовы MCP.</li>
            <li v-for="(step, index) in mcpLog" :key="index">
              <LoaderCircle v-if="step.pending" class="spin" :size="17" />
              <span v-else-if="step.error || step.call?.error" class="step-icon failed"><CircleAlert :size="14" /></span>
              <span v-else class="step-icon"><Check :size="14" /></span>
              <div class="workflow-label">
                <div>{{ knownLabels[step.source] }} · {{ toolTitle(step) }}</div>
                <small v-if="step.error || step.call?.error" class="error">{{ step.error || step.call.error }}</small>
                <small v-else-if="step.call?.cached" class="muted">Из кэша</small>
              </div>
              <button v-if="step.call" type="button" class="icon-button workflow-inspect"
                      :aria-label="'JSON-RPC: ' + toolTitle(step)" @click="inspectCall(step.call)"><Code2 :size="16" /></button>
            </li>
          </ul>
        </details>
        <form class="composer" @submit.prevent="send()">
          <input v-model="message" maxlength="3000" aria-label="Сообщение агенту" placeholder="Сообщение агенту"
                 :disabled="chatBusy || !agentAvailable" />
          <button class="primary send" :disabled="chatBusy || !agentAvailable || !message.trim()" aria-label="Отправить">
            <LoaderCircle v-if="chatBusy" class="spin" :size="18" /><Send v-else :size="18" />
          </button>
        </form>
      </section>
    </div>

    <details ref="inspector" class="inspector">
      <summary><Code2 :size="23" /> Инспектор JSON-RPC <ChevronDown :size="19" /></summary>
      <div class="inspector-body">
        <p v-if="!packet" class="muted">Здесь появятся пакеты после вызова инструмента.</p>
        <template v-else>
          <select v-model.number="packetIndex" aria-label="Выбрать вызов">
            <option v-for="(call, index) in packets" :key="index" :value="index">
              {{ knownLabels[call.source] }} · {{ toolTitle(call) }}{{ call.cached ? ' · из кэша' : '' }}
            </option>
          </select>
          <p v-if="packet.cached" class="muted">Результат из кэша. Повторный сетевой запрос не отправлялся.</p>
          <p v-if="packet.error" class="error">{{ packet.error }}</p>
          <div v-if="packet.request" class="packet-grid">
            <div><h3>Запрос</h3><pre class="json">{{ pretty(packet.request) }}</pre></div>
            <div><h3>Ответ</h3><pre class="json">{{ pretty(packet.response) }}</pre></div>
          </div>
          <pre v-if="packet.cached" class="json">{{ pretty(packet.result) }}</pre>
          <details v-if="packet.trace.length">
            <summary>Все события транспорта</summary>
            <pre class="json">{{ pretty(packet.trace) }}</pre>
          </details>
        </template>
      </div>
    </details>
  </main>
</template>
