<script setup>
import { ChevronDown, ExternalLink } from 'lucide-vue-next'
import { formatValue, knownLabels } from './fields.js'

defineProps({ title: String, source: String, outcome: Object, loading: Boolean })
</script>
<template>
  <article class="result-tile" :class="outcome?.result?.tone || 'neutral'">
    <div class="tile-title">{{ title }}</div>
    <p v-if="outcome?.error" class="error tile-error">{{ outcome.error }}</p>
    <div v-else class="result-value">
      {{ outcome?.result?.value !== undefined ? formatValue(outcome.result.value) : '—' }}
      <small v-if="outcome?.result?.unit">{{ outcome.result.unit }}</small>
    </div>
    <div class="result-foot">
      <span>{{ loading ? 'Расчет…' : 'Источник: ' + knownLabels[source] }}</span>
      <span v-if="outcome?.result?.category" class="score-status">{{ outcome.result.category }}</span>
    </div>
    <details v-if="outcome?.result?.components" class="result-details">
      <summary>Разбор расчета <ChevronDown :size="15" /></summary>
      <dl>
        <template v-for="(value, name) in outcome.result.components" :key="name">
          <dt>{{ name }}</dt><dd>{{ formatValue(value) }}</dd>
        </template>
      </dl>
      <p>{{ outcome.result.guidance }}</p>
      <a :href="outcome.result.source" target="_blank" rel="noopener noreferrer">Источник методики <ExternalLink :size="13" /></a>
    </details>
  </article>
</template>
