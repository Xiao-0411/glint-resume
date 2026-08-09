<template>
  <div class="chat-bubble" :class="`role-${role}`">
    <div class="avatar" v-if="role === 'ai'">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
    </div>
    <div class="bubble-wrap">
      <div class="bubble">
        <span class="bubble-text">
          <template v-for="(part, index) in renderedParts" :key="index">
            <br v-if="part.type === 'break'" />
            <strong v-else-if="part.type === 'strong'">{{ part.text }}</strong>
            <template v-else>{{ part.text }}</template>
          </template>
        </span>
        <span v-if="typing || streaming" class="cursor"></span>
        <!-- 快捷回复（仅AI最后一条显示） -->
        <div v-if="quickReplies && quickReplies.length" class="quick-chips">
          <button
            v-for="item in quickReplies"
            :key="item"
            class="quick-chip"
            @click="$emit('quick', item)"
          >
            {{ item }}
          </button>
        </div>
      </div>
      <div class="meta" v-if="!typing && !streaming">
        <span>{{ role === 'ai' ? '识光简历' : '我' }}</span>
        <span class="dot">·</span>
        <span>{{ formattedTime }}</span>
      </div>
    </div>
    <div class="avatar avatar-user" v-if="role === 'user'">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'

const props = defineProps({
  role: {
    type: String,
    required: true,
    validator: v => ['ai', 'user'].includes(v)
  },
  text: { type: String, required: true },
  ts: { type: Number, default: () => Date.now() },
  typewriter: { type: Boolean, default: false },
  streaming: { type: Boolean, default: false },
  quickReplies: { type: Array, default: () => [] }
})

const emit = defineEmits(['typing-done', 'quick'])

const displayed = ref('')
const typing = ref(false)

const renderedParts = computed(() => parseMarkdown(displayed.value))

const formattedTime = computed(() => {
  const d = new Date(props.ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
})

onMounted(() => {
  if (props.role === 'ai' && props.typewriter && !props.streaming) {
    runTypewriter(props.text)
  } else {
    displayed.value = props.text
  }
})

watch(() => props.text, (val) => {
  if (props.role === 'ai' && props.typewriter && !props.streaming) {
    runTypewriter(val)
  } else {
    displayed.value = val
  }
})

watch(() => props.streaming, (val, oldVal) => {
  if (oldVal && !val && props.role === 'ai') {
    emit('typing-done')
  }
})

function runTypewriter(fullText) {
  typing.value = true
  displayed.value = ''
  let i = 0
  const total = fullText.length
  const speed = total < 30 ? 60 : total < 80 ? 28 : 18
  const timer = setInterval(() => {
    i++
    displayed.value = fullText.slice(0, i)
    if (i >= total) {
      clearInterval(timer)
      typing.value = false
      emit('typing-done')
    }
  }, speed)
}

function parseMarkdown(text) {
  if (!text) return []
  const parts = []
  const lines = text.split('\n')

  lines.forEach((line, lineIndex) => {
    // Triple emphasis is rendered as strong; unmatched marker runs are hidden
    // so partial or malformed model Markdown never leaks into the chat UI.
    const strongPattern = /\*\*\*([^*]+?)\*\*\*|\*\*([^*]+?)\*\*/g
    let cursor = 0
    let match

    while ((match = strongPattern.exec(line)) !== null) {
      if (match.index > cursor) {
        pushPlainText(parts, line.slice(cursor, match.index))
      }
      parts.push({ type: 'strong', text: match[1] || match[2] })
      cursor = match.index + match[0].length
    }

    if (cursor < line.length) pushPlainText(parts, line.slice(cursor))
    if (lineIndex < lines.length - 1) parts.push({ type: 'break' })
  })

  return parts
}

function pushPlainText(parts, text) {
  const cleaned = text.replace(/\*{2,}/g, '')
  if (cleaned) parts.push({ type: 'text', text: cleaned })
}
</script>

<style scoped>
.chat-bubble {
  display: flex;
  gap: 14px;
  margin-bottom: 24px;
  animation: fadeInUp 0.4s var(--ease-out);
}

.role-user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  background: var(--gradient-primary);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  position: relative;
}

.role-ai .avatar {
  background: var(--gradient-primary);
}

.role-ai .avatar::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.18), transparent 50%);
  pointer-events: none;
}

.avatar-user {
  background: linear-gradient(135deg, #374151, #111827);
  box-shadow: 0 4px 12px rgba(17, 24, 39, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.bubble-wrap {
  max-width: 80%;
  display: flex;
  flex-direction: column;
}

.role-user .bubble-wrap {
  align-items: flex-end;
}

.bubble {
  position: relative;
  padding: 16px 20px;
  border-radius: var(--radius-md);
  font-size: 1.25rem;
  line-height: 1.7;
  word-break: break-word;
  letter-spacing: -0.1px;
}

.role-ai .bubble {
  background: linear-gradient(180deg, #FFFFFF 0%, #FAFBFD 100%);
  border: 1px solid var(--color-border-light);
  color: var(--color-text);
  border-top-left-radius: var(--radius-xs);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}

.role-ai .bubble::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--gradient-primary);
  border-radius: 2px 0 0 2px;
  opacity: 0.85;
}

.role-user .bubble {
  background: var(--gradient-primary);
  color: white;
  border-top-right-radius: var(--radius-xs);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.bubble-text :deep(strong) {
  color: var(--color-primary-dark);
  font-weight: 700;
}

.role-user .bubble-text :deep(strong) {
  color: #DBEAFE;
}

.cursor {
  display: inline-block;
  width: 7px;
  height: 1em;
  margin-left: 2px;
  background: var(--color-primary);
  vertical-align: middle;
  animation: blink 0.9s infinite;
  border-radius: 2px;
}

/* ============ 快捷回复 ============ */
.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--color-border);
}

.quick-chip {
  padding: 7px 16px;
  background: linear-gradient(180deg, #FFFFFF 0%, #F9FAFB 100%);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  font-size: 1.02rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  transition: all 0.25s var(--ease-out);
  box-shadow: var(--shadow-xs);
}

.quick-chip:hover {
  border-color: rgba(37, 99, 235, 0.4);
  color: var(--color-primary-dark);
  background: linear-gradient(180deg, #FFFFFF 0%, var(--color-primary-soft) 100%);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.12);
}

.meta {
  font-size: 0.82rem;
  color: var(--color-text-muted);
  margin-top: 8px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  letter-spacing: 0.1px;
  font-weight: 500;
}

.dot {
  opacity: 0.4;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
</style>
