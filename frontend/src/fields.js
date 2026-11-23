export const knownLabels = {
  stdio: 'stdio', sse: 'SSE', pubmed: 'PubMed',
  pf_ratio: 'PaO₂/FiO₂', news2: 'NEWS2', rox: 'Индекс ROX', qsofa: 'qSOFA', curb65: 'CURB-65',
  list_calculators: 'Каталог калькуляторов', pubmed_search_articles: 'Поиск статей',
  pubmed_fetch_articles: 'Аннотации статей',
}
export const enumLabels = {
  alert: 'В сознании', confused: 'Новая спутанность', voice: 'Реакция на голос',
  pain: 'Реакция на боль', unresponsive: 'Нет реакции',
}
export const firstFields = ['pao2', 'fio2', 'spo2', 'resp_rate', 'pulse', 'supplemental_oxygen']
export const moreFields = ['systolic', 'temp', 'consciousness', 'spo2_scale']
export const formatValue = value => typeof value === 'number' ? value.toLocaleString('ru-RU') : value

export function pickArguments(schema, model) {
  return Object.fromEntries(
    Object.keys(schema?.properties || {}).filter(key => model[key] !== undefined
      && model[key] !== null && model[key] !== '').map(key => [key, model[key]]),
  )
}
