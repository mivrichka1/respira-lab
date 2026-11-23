<script setup>
import { enumLabels } from './fields.js'
const props = defineProps({ entry: Object, modelValue: [Number, String, Boolean, Array], id: String })
const emit = defineEmits(['update:modelValue'])

function setNumber(event) {
  const raw = event.target.value
  emit('update:modelValue', raw === '' ? null : Number(raw))
}
</script>
<template>
  <label v-if="entry.type === 'boolean'" class="check-field" :for="id">
    <input :id="id" type="checkbox" :checked="modelValue === true"
           @change="emit('update:modelValue', $event.target.checked)" />
    {{ entry.title }}
  </label>
  <div v-else class="field">
    <label :for="id">{{ entry.title }}</label>
    <select v-if="entry.enum" :id="id" :value="modelValue ?? ''"
            @change="emit('update:modelValue', $event.target.value || null)">
      <option disabled value="">Выберите</option>
      <option v-for="option in entry.enum" :key="option" :value="option">
        {{ enumLabels[option] || option }}
      </option>
    </select>
    <div v-else-if="entry.type === 'array'" class="field-control">
      <input :id="id" type="text" :value="(modelValue || []).join(', ')"
             @change="emit('update:modelValue', $event.target.value.split(',').map(item => item.trim()).filter(Boolean))" />
    </div>
    <div v-else class="field-control">
      <input :id="id" :type="['number', 'integer'].includes(entry.type) ? 'number' : 'text'"
             :value="modelValue ?? ''" :min="entry.minimum" :max="entry.maximum"
             :step="entry.type === 'integer' ? 1 : 'any'"
             :aria-describedby="entry.unit ? id + '-unit' : undefined"
             @input="['number', 'integer'].includes(entry.type) ? setNumber($event) : emit('update:modelValue', $event.target.value)" />
      <span v-if="entry.unit" :id="id + '-unit'" class="unit">{{ entry.unit }}</span>
    </div>
  </div>
</template>
