<script setup>
import { computed } from 'vue'

const props = defineProps({ text: String })

function inline(text) {
  const pattern = /\[([^\]]+)\]\((https:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/\d{1,12}\/?)\)/g
  const parts = []
  let start = 0
  for (const match of text.matchAll(pattern)) {
    parts.push({ text: text.slice(start, match.index) }, { text: match[1], href: match[2] })
    start = match.index + match[0].length
  }
  parts.push({ text: text.slice(start) })
  return parts.map(part => ({
    ...part, text: part.text.replace(/^#{1,6}\s+/gm, '').replace(/\*\*([^*]*)\*\*/g, '$1'),
  }))
}

function rowCells(line) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim())
}

const blocks = computed(() => {
  const result = []
  const lines = (props.text || '').split('\n')
  let text = []
  const flush = () => {
    if (text.length) result.push({ parts: inline(text.join('\n').trim()) })
    text = []
  }
  for (let i = 0; i < lines.length; i += 1) {
    const header = rowCells(lines[i])
    const separator = lines[i + 1] === undefined ? [] : rowCells(lines[i + 1])
    if (header.length < 2 || separator.length !== header.length
        || !separator.every(cell => /^:?-{3,}:?$/.test(cell))) {
      text.push(lines[i])
      continue
    }
    flush()
    i += 1
    const rows = []
    while (lines[i + 1]?.includes('|') && rowCells(lines[i + 1]).length === header.length) {
      i += 1
      rows.push(rowCells(lines[i]).map(inline))
    }
    result.push({ header: header.map(inline), rows })
  }
  flush()
  return result
})
</script>

<template>
  <div v-for="(block, i) in blocks" :key="i" :class="block.header ? 'assistant-table' : 'assistant-paragraph'">
    <table v-if="block.header">
      <thead><tr><th v-for="(cell, c) in block.header" :key="c">
        <template v-for="(part, p) in cell" :key="p">{{ part.text }}</template>
      </th></tr></thead>
      <tbody><tr v-for="(row, r) in block.rows" :key="r"><td v-for="(cell, c) in row" :key="c">
        <template v-for="(part, p) in cell" :key="p">
          <a v-if="part.href" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.text }}</a>
          <template v-else>{{ part.text }}</template>
        </template>
      </td></tr></tbody>
    </table>
    <template v-else>
      <template v-for="(part, p) in block.parts" :key="p">
        <a v-if="part.href" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.text }}</a>
        <template v-else>{{ part.text }}</template>
      </template>
    </template>
  </div>
</template>
