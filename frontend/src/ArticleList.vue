<script setup>
import { ArrowUpRight } from 'lucide-vue-next'

defineProps({ articles: { type: Array, required: true } })
const emit = defineEmits(['select'])
</script>

<template>
  <ol class="article-list" aria-label="Статьи PubMed">
    <li v-for="article in articles" :key="article.pmid">
      <button type="button" class="article-title" @click="emit('select', article)">{{ article.title }}</button>
      <div class="article-meta">
        <span v-if="article.source || article.pubDate">{{ [article.source, article.pubDate?.slice(0, 4)].filter(Boolean).join(' · ') }}</span>
        <a :href="'https://pubmed.ncbi.nlm.nih.gov/' + article.pmid + '/'" target="_blank" rel="noopener noreferrer">
          PMID {{ article.pmid }} <ArrowUpRight :size="12" />
        </a>
      </div>
    </li>
  </ol>
</template>
