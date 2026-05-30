<template>
  <div :class="['app', { dark: isDark }]" @click="closePanel">

    <!-- NAV BAR -->
    <nav class="navbar" @click.stop>
      <span class="nav-logo">✦ AI Agent</span>
      <div class="nav-items">
        <div v-for="item in navItems" :key="item.id" class="nav-item">
          <button
            @click="togglePanel(item.id)"
            :class="['nav-btn', { active: activePanel === item.id }]"
          >
            {{ item.icon }} {{ item.label }}
          </button>
          <div v-if="activePanel === item.id" class="dropdown">
            <h4 class="dropdown-title">{{ item.label }}</h4>
            <ul>
              <li v-for="entry in item.entries" :key="entry">{{ entry }}</li>
            </ul>
          </div>
        </div>
      </div>
      <button class="theme-btn" @click.stop="toggleDark" :title="isDark ? 'Light Mode' : 'Dark Mode'">
        {{ isDark ? '☀️' : '🌙' }}
      </button>
    </nav>

    <!-- CHAT AREA -->
    <main class="chat-area" ref="chatArea">
      <div class="messages">

        <div v-if="messages.length === 0" class="welcome">
          <div class="welcome-icon">✦</div>
          <h2>Wie kann ich dir helfen?</h2>
          <p>Stelle eine Frage oder lade ein Dokument hoch.</p>
        </div>

        <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
          <div class="bubble">
            <template v-if="msg.role === 'assistant'">
              <div v-if="!loading || i < messages.length - 1"
                   class="bubble-text markdown"
                   v-html="renderMarkdown(msg.content)">
              </div>
              <span v-else class="bubble-text">{{ msg.content }}<span class="cursor">▋</span></span>
            </template>
            <span v-else class="bubble-text">{{ msg.content }}</span>
          </div>
        </div>

      </div>
    </main>

    <!-- INPUT BAR -->
    <div class="input-bar">
      <div class="input-container">
        <label class="upload-btn" title="PDF hochladen">
          📎
          <input type="file" accept=".pdf" @change="uploadFile" hidden />
        </label>
        <textarea
          v-model="prompt"
          placeholder="Frage eingeben..."
          @keydown.enter.exact.prevent="sendPrompt"
          @input="resizeTextarea"
          ref="textarea"
          rows="1"
        ></textarea>
        <button @click="sendPrompt" :disabled="loading || !prompt.trim()" class="send-btn">
          ↑
        </button>
      </div>
      <p v-if="uploadStatus" class="upload-status">{{ uploadStatus }}</p>
    </div>

  </div>
</template>

<script>
import { marked } from 'marked'

marked.use({ breaks: true })

export default {
  data() {
    return {
      prompt: '',
      messages: [],
      loading: false,
      activePanel: null,
      uploadStatus: '',
      isDark: false,
      navItems: [
        {
          id: 'pruefungen',
          label: 'Prüfungen',
          icon: '📅',
          entries: ['15.06 Datenbanken', '22.06 Statistik', '01.07 Programmierung']
        },
        {
          id: 'lernplan',
          label: 'Lernplan',
          icon: '📚',
          entries: ['SQL Basics', 'JOINs üben', 'Statistik wiederholen']
        },
        {
          id: 'quiz',
          label: 'Quiz',
          icon: '🧠',
          entries: ['SQL – 5 Fragen', 'Statistik Aufgaben']
        },
        {
          id: 'career',
          label: 'Career',
          icon: '💼',
          entries: ['SQL: ⭐⭐☆☆☆', 'Python: ⭐⭐⭐☆☆', 'Power BI: ⭐☆☆☆☆', 'Job Fit: 62%']
        }
      ]
    }
  },
  mounted() {
    this.isDark = localStorage.getItem('darkMode') === 'true'
  },
  methods: {
    toggleDark() {
      this.isDark = !this.isDark
      localStorage.setItem('darkMode', this.isDark)
    },
    togglePanel(id) {
      this.activePanel = this.activePanel === id ? null : id
    },
    closePanel() {
      this.activePanel = null
    },
    renderMarkdown(text) {
      if (!text) return ''
      return marked.parse(text)
    },
    resizeTextarea() {
      const el = this.$refs.textarea
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 140) + 'px'
    },
    scrollToBottom() {
      const el = this.$refs.chatArea
      if (el) el.scrollTop = el.scrollHeight
    },
    async sendPrompt() {
      if (!this.prompt.trim() || this.loading) return

      const userPrompt = this.prompt
      this.prompt = ''
      this.$nextTick(() => { this.$refs.textarea.style.height = 'auto' })

      this.messages.push({ role: 'user', content: userPrompt })
      this.messages.push({ role: 'assistant', content: '' })
      this.loading = true

      await this.$nextTick()
      this.scrollToBottom()

      try {
        const res = await fetch('/api/prompt/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: userPrompt })
        })
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6)
            if (raw === '[DONE]' || raw === '[ERROR]') return
            let data
            try { data = JSON.parse(raw) } catch { data = raw }
            this.messages[this.messages.length - 1].content += data
            this.$nextTick(() => this.scrollToBottom())
          }
        }
      } catch (e) {
        this.messages[this.messages.length - 1].content = 'Fehler: Backend nicht erreichbar.'
      } finally {
        this.loading = false
      }
    },
    async uploadFile(event) {
      const file = event.target.files[0]
      if (!file) return
      this.uploadStatus = `"${file.name}" wird hochgeladen...`
      const formData = new FormData()
      formData.append('file', file)
      try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData })
        if (res.ok) {
          this.uploadStatus = ''
          this.messages.push({ role: 'assistant', content: `📄 **"${file.name}"** wurde hochgeladen und wird verarbeitet.` })
          this.$nextTick(() => this.scrollToBottom())
        } else {
          this.uploadStatus = 'Fehler beim Hochladen.'
        }
      } catch (e) {
        this.uploadStatus = 'Fehler: Backend nicht erreichbar.'
      }
      event.target.value = ''
    }
  }
}
</script>

<style>
*, *::before, *::after { box-sizing: border-box; }

/* CSS VARIABLES */
:root {
  --bg: #f9fafb;
  --surface: #ffffff;
  --surface-hover: #f3f4f6;
  --border: #e5e7eb;
  --text: #111827;
  --text-muted: #6b7280;
  --primary: #6366f1;
  --primary-hover: #4f46e5;
  --primary-dim: #ede9fe;
  --user-bubble-bg: #6366f1;
  --user-bubble-text: #ffffff;
  --assistant-bubble-bg: #ffffff;
  --assistant-bubble-text: #111827;
  --code-bg: #f3f4f6;
  --code-text: #be185d;
  --input-bg: #ffffff;
  --shadow: 0 2px 12px rgba(0,0,0,0.06);
}

.dark {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface-hover: #22263a;
  --border: #2e3247;
  --text: #f1f3f9;
  --text-muted: #8b92a9;
  --primary: #818cf8;
  --primary-hover: #6366f1;
  --primary-dim: #1e1b4b;
  --user-bubble-bg: #4f46e5;
  --user-bubble-text: #ffffff;
  --assistant-bubble-bg: #1a1d27;
  --assistant-bubble-text: #f1f3f9;
  --code-bg: #0f1117;
  --code-text: #f472b6;
  --input-bg: #1a1d27;
  --shadow: 0 2px 12px rgba(0,0,0,0.3);
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  transition: background 0.2s, color 0.2s;
}

/* NAV */
.navbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 20px;
  height: 52px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  z-index: 100;
}

.nav-logo {
  font-weight: 700;
  font-size: 15px;
  color: var(--primary);
  margin-right: 12px;
  white-space: nowrap;
}

.nav-items {
  display: flex;
  gap: 2px;
  flex: 1;
}

.nav-item { position: relative; }

.nav-btn {
  background: none;
  border: none;
  padding: 5px 11px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

.nav-btn:hover { background: var(--surface-hover); color: var(--text); }
.nav-btn.active { background: var(--primary-dim); color: var(--primary); }

.theme-btn {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
  margin-left: auto;
  flex-shrink: 0;
}

.theme-btn:hover { background: var(--surface-hover); }

.dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 200px;
  box-shadow: var(--shadow);
  z-index: 200;
}

.dropdown-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.dropdown ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.dropdown ul li {
  font-size: 13px;
  color: var(--text-muted);
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
}

.dropdown ul li:last-child { border-bottom: none; }

/* CHAT */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 32px 24px 16px;
  display: flex;
  flex-direction: column;
}

.messages {
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

.welcome {
  text-align: center;
  margin: auto;
  color: var(--text-muted);
}

.welcome-icon {
  font-size: 36px;
  color: var(--primary);
  margin-bottom: 12px;
}

.welcome h2 {
  margin: 0 0 8px;
  color: var(--text);
  font-size: 20px;
  font-weight: 600;
}

.welcome p { margin: 0; font-size: 14px; }

.message { display: flex; }
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }

.bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
}

.message.user .bubble {
  background: var(--user-bubble-bg);
  color: var(--user-bubble-text);
  border-bottom-right-radius: 4px;
}

.message.assistant .bubble {
  background: var(--assistant-bubble-bg);
  color: var(--assistant-bubble-text);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  box-shadow: var(--shadow);
}

/* MARKDOWN STYLES */
.markdown { white-space: normal; }
.markdown p { margin: 0 0 8px; }
.markdown p:last-child { margin-bottom: 0; }
.markdown strong { font-weight: 600; }
.markdown em { font-style: italic; }
.markdown code {
  font-family: 'Fira Code', 'Cascadia Code', monospace;
  font-size: 12.5px;
  background: var(--code-bg);
  color: var(--code-text);
  padding: 1px 5px;
  border-radius: 4px;
}
.markdown pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.markdown pre code {
  background: none;
  color: var(--text);
  padding: 0;
  font-size: 12.5px;
}
.markdown ul, .markdown ol {
  margin: 4px 0 8px;
  padding-left: 20px;
}
.markdown li { margin: 2px 0; }
.markdown h1, .markdown h2, .markdown h3 {
  margin: 10px 0 6px;
  font-weight: 600;
  color: var(--text);
}
.markdown h1 { font-size: 17px; }
.markdown h2 { font-size: 15px; }
.markdown h3 { font-size: 14px; }
.markdown blockquote {
  border-left: 3px solid var(--primary);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--text-muted);
}
.markdown a { color: var(--primary); text-decoration: underline; }

.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }

/* INPUT BAR */
.input-bar {
  padding: 10px 24px 18px;
  background: var(--bg);
  flex-shrink: 0;
}

.input-container {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 8px 8px 8px 12px;
  box-shadow: var(--shadow);
  transition: border-color 0.2s;
}

.input-container:focus-within { border-color: var(--primary); }

.upload-btn {
  cursor: pointer;
  font-size: 18px;
  padding: 5px;
  border-radius: 7px;
  color: var(--text-muted);
  transition: color 0.15s, background 0.15s;
  flex-shrink: 0;
  line-height: 1;
  margin-bottom: 2px;
}

.upload-btn:hover { color: var(--primary); background: var(--surface-hover); }

.input-container textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  color: var(--text);
  background: transparent;
  line-height: 1.5;
  padding: 4px 0;
  max-height: 140px;
  overflow-y: auto;
}

.input-container textarea::placeholder { color: var(--text-muted); }

.send-btn {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--primary);
  color: white;
  border: none;
  font-size: 18px;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
  padding: 0;
}

.send-btn:hover:not(:disabled) { background: var(--primary-hover); }
.send-btn:disabled { background: var(--border); cursor: default; }

.upload-status {
  max-width: 720px;
  margin: 6px auto 0;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
</style>
