<template>
  <div class="layout">

    <!-- SIDEBAR -->
    <div class="sidebar">

      <h2>AI Agent</h2>

      <div class="box">
        <h3>📄 PDF Upload</h3>
        <input type="file" />
      </div>

      <div class="box">
        <h3>💬 Prompt</h3>
        <textarea v-model="prompt" placeholder="Frage eingeben..."></textarea>
        <button @click="sendPrompt" :disabled="loading">
          {{ loading ? 'Lädt...' : 'Senden' }}
        </button>

        <div v-if="response || loading" class="response-box">
          <p class="response-label">Antwort</p>
          <p class="response-text">{{ response }}<span v-if="loading" class="cursor">▋</span></p>
        </div>
      </div>

    </div>

    <!-- MAIN -->
    <div class="main">

      <h1>Study & Career Dashboard</h1>

      <p class="subtitle">
        Adaptive Learning · AI Tutor · Career Matching
      </p>

      <!-- extra spacing -->
      <div class="spacer"></div>

      <div class="grid">

        <div class="card c1">
          <h2>Prüfungen</h2>
          <ul>
            <li>15.06 Datenbanken</li>
            <li>22.06 Statistik</li>
            <li>01.07 Programmierung</li>
          </ul>
        </div>

        <div class="card c2">
          <h2>Lernplan</h2>
          <ul>
            <li>SQL Basics</li>
            <li>JOINs üben</li>
            <li>Statistik wiederholen</li>
          </ul>
        </div>

        <div class="card c3">
          <h2>Quiz</h2>
          <ul>
            <li>SQL 5 Fragen</li>
            <li>Statistik Aufgaben</li>
          </ul>
        </div>

        <div class="card c4">
          <h2>Career / Skills</h2>
          <p>SQL: ⭐⭐☆☆☆</p>
          <p>Python: ⭐⭐⭐☆☆</p>
          <p>Power BI: ⭐☆☆☆☆</p>
          <p><b>Job Fit: 62%</b></p>
        </div>

      </div>

    </div>

  </div>
</template>

<script>
export default {
  data() {
    return {
      prompt: "",
      response: "",
      loading: false
    }
  },
  methods: {
    async sendPrompt() {
      this.loading = true
      this.response = ''
      try {
        const res = await fetch('/api/prompt/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: this.prompt })
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
            const data = line.slice(6)
            if (data === '[DONE]' || data === '[ERROR]') return
            this.response += data
          }
        }
      } catch (e) {
        this.response = 'Fehler: Backend nicht erreichbar.'
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style>
/* GLOBAL */
body {
  margin: 0;
  font-family: Arial, sans-serif;
  background: #f5f6f8;
}

/* LAYOUT */
.layout {
  display: flex;
  height: 100vh;
}

/* SIDEBAR (hellgrau wie gewünscht) */
.sidebar {
  width: 300px;
  background: #e5e7eb;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 15px;
  border-right: 1px solid #d1d5db;
}

.sidebar h2 {
  margin-bottom: 10px;
  color: #111827;
}

.box {
  background: #f9fafb;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;


}

textarea {
  width: 100%;
  height: 80px;
  margin-top: 5px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  padding: 8px;
  background: white;
  color: #111827;
}

button {
  margin-top: 10px;
  width: 100%;
  padding: 8px;
  background: #6366f1;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.response-box {
  margin-top: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 10px 12px;
}

.response-label {
  font-size: 11px;
  font-weight: 600;
  color: #0369a1;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.response-text {
  font-size: 13px;
  color: #1e3a5f;
  line-height: 1.5;
  white-space: pre-wrap;
}

.cursor {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* MAIN */
.main {
  flex: 1;
  padding: 40px;
}

/* HEADER */
h1 {
  margin: 0;
  color: #111827;
}

/* Abstand zwischen Titel und Kacheln */
.subtitle {
  margin-top: 20px;
  color: #6b7280;
}

.spacer {
  height: 35px;
}

/* GRID */
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 18px;
}

/* CARDS (sehr hell & clean) */
.card {
  padding: 18px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

/* leicht unterschiedliche Pastell-Töne */
.c1 { background: #fef3c7; }
.c2 { background: #dbeafe; }
.c3 { background: #dcfce7; }
.c4 { background: #f3e8ff; }

ul {
  padding-left: 18px;
}
</style>