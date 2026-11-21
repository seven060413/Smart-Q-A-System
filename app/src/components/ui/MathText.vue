<template>
  <!-- App-vue 和 H5 用 renderjs + KaTeX；其他平台回退成纯文本 -->
  <!-- #ifdef H5 || APP-PLUS -->
  <view
    class="math-text"
    :class="{ 'math-text--inline': inline }"
    :data-source="text"
    :prop="text"
    :change:prop="math.render"
  ></view>
  <!-- #endif -->
  <!-- #ifndef H5 -->
  <!-- #ifndef APP-PLUS -->
  <text class="math-text" :class="{ 'math-text--inline': inline }">{{ plainText }}</text>
  <!-- #endif -->
  <!-- #endif -->
</template>

<script setup>
import { computed } from 'vue'
// #ifdef H5 || APP-PLUS
import '../../static/katex/katex.min.css'
// #endif
import { textToPlain } from '../../math/latex.js'

const props = defineProps({
  text: { type: [String, Number], default: '' },
  inline: { type: Boolean, default: false },
})

const plainText = computed(() => textToPlain(props.text))
</script>

<script module="math" lang="renderjs">
import katex from 'katex'
import { splitMathSegments } from '../../math/latex.js'

function appendText(fragment, value) {
  const text = String(value == null ? '' : value)
  text.split('\n').forEach((line, index) => {
    if (index) fragment.appendChild(document.createElement('br'))
    if (line) fragment.appendChild(document.createTextNode(line))
  })
}

export default {
  data() {
    return { el: null }
  },
  mounted() {
    // H5 下 this.$el 可用；App 端以 change:prop 回调里的 instance.$el 为准。
    this.el = this.$el || null
    const source = this.el && this.el.getAttribute('data-source')
    if (source != null) this.render(source)
  },
  methods: {
    render(value, oldValue, ownerInstance, instance) {
      if (instance && instance.$el) this.el = instance.$el
      const el = this.el || this.$el
      if (!el) return

      const fragment = document.createDocumentFragment()
      for (const segment of splitMathSegments(value)) {
        if (segment.type === 'text') {
          appendText(fragment, segment.value)
          continue
        }

        const node = document.createElement(segment.display ? 'div' : 'span')
        if (segment.display) node.className = 'math-display'
        try {
          katex.render(segment.value, node, {
            displayMode: segment.display,
            throwOnError: false,
            strict: 'ignore',
            trust: false,
            output: 'html',
            errorColor: '#cc0000',
          })
        } catch (error) {
          node.textContent = segment.raw
        }
        fragment.appendChild(node)
      }

      el.innerHTML = ''
      el.appendChild(fragment)
    },
  },
}
</script>

<style>
.math-text {
  display: block;
  word-break: break-word;
}

.math-text--inline {
  display: inline-block;
  vertical-align: baseline;
}

.math-text :deep(.katex) {
  font-size: 1.05em;
  white-space: nowrap;
}

.math-text :deep(.katex-display) {
  margin: 0.4em 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.math-text :deep(.math-display) {
  display: block;
  text-align: center;
  overflow-x: auto;
  overflow-y: hidden;
}
</style>
