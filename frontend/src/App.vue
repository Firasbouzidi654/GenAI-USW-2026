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
          <div v-if="activePanel === item.id" :class="['dropdown', { 'dropdown--wide': item.id === 'kalender', 'dropdown--extra-wide': item.id === 'noten' || item.id === 'planner' }]">
            <h4 class="dropdown-title">{{ item.label }}</h4>
            <ul>
              <li v-for="entry in item.entries" :key="entry">{{ entry }}</li>
            </ul>
            <div v-if="item.id === 'career'" class="job-agent-section">
              <button
                @click.stop="launchJobAgent"
                :disabled="jobAgentLoading"
                class="job-agent-btn"
              >
                {{ jobAgentLoading ? '⏳ Launching...' : '🚀 Launch Job Search Agent' }}
              </button>
              <p v-if="jobAgentStatus" :class="['job-agent-status', jobAgentStatus.type]">
                {{ jobAgentStatus.message }}
              </p>
            </div>

            <div v-if="item.id === 'kalender'" class="kalender-section">

              <!-- Toolbar -->
              <div class="kalender-toolbar">
                <label class="kalender-upload-label">
                  📂 .ics laden
                  <input type="file" accept=".ics" @change="uploadIcsFile" hidden />
                </label>
                <button
                  v-if="calendarEvents.length > 0"
                  @click.stop="clearCalendar"
                  :disabled="calendarClearing"
                  class="kalender-clear-btn"
                  title="Kalender leeren"
                >🗑</button>
              </div>

              <p v-if="icsUploadStatus" :class="['kalender-status', icsUploadStatus.type]">
                {{ icsUploadStatus.message }}
              </p>

              <!-- Search -->
              <input
                v-if="calendarEvents.length > 0"
                v-model="calendarSearch"
                @click.stop
                class="kalender-search"
                placeholder="Kurs suchen..."
                type="text"
              />

              <!-- Empty states -->
              <div v-if="calendarEvents.length === 0" class="kalender-empty">
                Noch keine Ereignisse geladen.
              </div>
              <div v-else-if="filteredCalendarEvents.length === 0" class="kalender-empty">
                Kein Kurs gefunden.
              </div>

              <!-- Grouped event cards -->
              <div v-else class="kalender-groups">
                <div v-for="group in visibleGroupedEvents" :key="group.date" class="kalender-group">
                  <div class="kalender-date-header">{{ group.label }}</div>
                  <div
                    v-for="event in group.events"
                    :key="event.id"
                    :class="['kalender-card', eventTypeClass(event.title)]"
                  >
                    <div class="kalender-card-body">
                      <div class="kalender-card-top">
                        <span class="kalender-card-name">{{ parseCourseName(event.title) }}</span>
                        <span v-if="parseEventType(event.title)" class="kalender-card-badge">
                          {{ parseEventType(event.title) }}
                        </span>
                      </div>
                      <div class="kalender-card-time">
                        🕐 {{ formatTime(event.start_time) }} – {{ formatTime(event.end_time) }}
                      </div>
                      <div v-if="event.location" class="kalender-card-meta">
                        📍 {{ event.location }}
                      </div>
                      <div v-if="extractProfessor(event.description)" class="kalender-card-meta">
                        👤 {{ extractProfessor(event.description) }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Show all / less toggle -->
              <button
                v-if="filteredCalendarEvents.length > 10"
                @click.stop="calendarShowAll = !calendarShowAll"
                class="kalender-toggle-btn"
              >
                {{ calendarShowAll ? '▲ Weniger anzeigen' : `▼ Alle ${filteredCalendarEvents.length} anzeigen` }}
              </button>

            </div>

            <div v-if="item.id === 'noten'" class="noten-section">
              <div class="noten-toolbar">
                <label class="noten-upload-label">
                  📂 PDF auswählen
                  <input type="file" accept=".pdf" @change="selectGradesPdf" hidden />
                </label>
              </div>
              <p v-if="gradesFileName" class="noten-filename">📄 {{ gradesFileName }}</p>
              <button
                v-if="gradesFileName"
                @click.stop="extractGrades"
                :disabled="gradesLoading"
                class="noten-extract-btn"
              >
                {{ gradesLoading ? '⏳ Extrahieren...' : '🔍 Noten extrahieren' }}
              </button>
              <p v-if="gradesStatus" :class="['noten-status', gradesStatus.type]">
                {{ gradesStatus.message }}
              </p>
              <div v-if="gradesData && gradesData.courses.length > 0" class="noten-results">
                <div v-if="gradesData.studentName || gradesData.totalCredits" class="noten-summary">
                  <span v-if="gradesData.studentName" class="noten-student">{{ gradesData.studentName }}</span>
                  <span v-if="gradesData.totalCredits" class="noten-credits">{{ gradesData.totalCredits }} ECTS gesamt</span>
                </div>
                <div class="noten-table-wrap">
                  <table class="noten-table">
                    <thead>
                      <tr>
                        <th>Kurs</th>
                        <th>Sem.</th>
                        <th>Note</th>
                        <th>ECTS</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(c, i) in sortedGradesCourses" :key="i">
                        <td>{{ c.courseName }}</td>
                        <td>{{ c.semester }}</td>
                        <td class="noten-grade">{{ c.grade }}</td>
                        <td>{{ c.credits }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div v-else-if="gradesData" class="noten-empty">
                Keine Noten gefunden.
              </div>
              <div v-else class="noten-empty">
                Noch keine Noten geladen.
              </div>
            </div>

            <div v-if="item.id === 'planner'" class="planner-section" @click.stop>
              <form @submit.prevent="submitPlannerEvent" class="planner-form">
                <input v-model="plannerForm.title" placeholder="Titel *" required class="planner-input" @click.stop />
                <input v-model="plannerForm.course_name" placeholder="Kursname *" required class="planner-input" @click.stop />
                <select v-model="plannerForm.type" class="planner-input" @click.stop>
                  <option value="EXAM">Prüfung (EXAM)</option>
                  <option value="ASSIGNMENT">Abgabe (ASSIGNMENT)</option>
                  <option value="PRESENTATION">Präsentation (PRESENTATION)</option>
                </select>
                <input type="date" v-model="plannerForm.date" required class="planner-input" @click.stop />
                <input v-model="plannerForm.description" placeholder="Beschreibung (optional)" class="planner-input" @click.stop />
                <button type="submit" :disabled="plannerSubmitting" class="planner-submit-btn">
                  {{ plannerSubmitting ? '⏳ Speichern...' : '+ Event hinzufügen' }}
                </button>
              </form>
              <p v-if="plannerStatus" :class="['planner-status', plannerStatus.type]">{{ plannerStatus.message }}</p>

              <div v-if="plannerEvents.length === 0" class="planner-empty">Noch keine Events eingetragen.</div>
              <div v-else class="planner-list">
                <div v-for="event in plannerEvents" :key="event.id" class="planner-card">
                  <div class="planner-card-header">
                    <span class="planner-card-title">{{ event.title }}</span>
                    <button @click.stop="deletePlannerEvent(event.id)" class="planner-delete-btn" title="Löschen">✕</button>
                  </div>
                  <div class="planner-card-meta">
                    <span class="planner-course">{{ event.course_name }}</span>
                    <span :class="['planner-type-badge', 'ptype-' + event.type.toLowerCase()]">{{ plannerTypeLabel(event.type) }}</span>
                  </div>
                  <div class="planner-card-footer">
                    <span class="planner-date">📅 {{ formatPlannerDate(event.date) }}</span>
                    <span class="planner-days">{{ event.days_remaining }} Tage verbleibend</span>
                    <span :class="['planner-priority', 'pprio-' + event.priority.toLowerCase()]">{{ event.priority }}</span>
                  </div>
                </div>
              </div>
            </div>

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
        <label :class="['upload-btn', { 'upload-btn--busy': uploading }]" :title="uploading ? 'Wird hochgeladen...' : 'PDF hochladen'">
          {{ uploading ? '⏳' : '📎' }}
          <input type="file" accept=".pdf" @change="uploadFile" :disabled="uploading" hidden />
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
      uploading: false,
      activePanel: null,
      uploadStatus: '',
      jobAgentLoading: false,
      jobAgentStatus: null,
      isDark: false,
      calendarEvents: [],
      icsUploadStatus: null,
      calendarSearch: '',
      calendarShowAll: false,
      calendarClearing: false,
      gradesFile: null,
      gradesFileName: '',
      gradesLoading: false,
      gradesStatus: null,
      gradesData: null,
      plannerEvents: [],
      plannerSubmitting: false,
      plannerStatus: null,
      plannerForm: { title: '', course_name: '', type: 'EXAM', date: '', description: '' },
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
        },
        {
          id: 'kalender',
          label: 'Kalender',
          icon: '📆',
          entries: []
        },
        {
          id: 'noten',
          label: 'Noten',
          icon: '🎓',
          entries: []
        },
        {
          id: 'planner',
          label: 'Planner',
          icon: '📋',
          entries: []
        }
      ]
    }
  },
  computed: {
    filteredCalendarEvents() {
      const now = new Date()
      const q = this.calendarSearch.trim().toLowerCase()
      return this.calendarEvents
        .filter(e => new Date(e.start_time) >= now)
        .filter(e => !q || e.title.toLowerCase().includes(q) || (e.location || '').toLowerCase().includes(q))
        .sort((a, b) => new Date(a.start_time) - new Date(b.start_time))
    },
    sortedGradesCourses() {
      if (!this.gradesData?.courses) return []
      const parse = g => parseFloat((g || '').replace(',', '.')) || Infinity
      return [...this.gradesData.courses].sort((a, b) => parse(a.grade) - parse(b.grade))
    },
    visibleGroupedEvents() {
      const events = this.calendarShowAll
        ? this.filteredCalendarEvents
        : this.filteredCalendarEvents.slice(0, 10)
      const groups = {}
      for (const event of events) {
        const key = event.start_time.slice(0, 10)
        if (!groups[key]) {
          groups[key] = { date: key, label: this.formatDateHeader(event.start_time), events: [] }
        }
        groups[key].events.push(event)
      }
      return Object.values(groups)
    }
  },
  mounted() {
    this.isDark = localStorage.getItem('darkMode') === 'true'
    this.fetchCalendarEvents()
    this.fetchPlannerEvents()
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
    // --- STUDY ADVISOR: keyword list that triggers the planner-aware AI ---
    isPlannerQuestion(text) {
      const keywords = [
        // Planner / deadline keywords
        'focus', 'priority', 'deadline', 'study plan', 'this week', 'today',
        'exam', 'assignment', 'presentation', 'planner', 'urgent', 'schedule',
        'what should i', 'am i at risk', 'risk', 'prepare', 'review',
        // Calendar / class keywords
        'class', 'classes', 'lecture', 'course', 'kalender', 'calendar',
        'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
        'saturday', 'sunday', 'timetable', 'time table', 'what time',
        'when is', 'when do i', 'what do i have', 'show my', 'upcoming classes',
        'my schedule', 'my classes', 'my lectures'
      ]
      const lower = text.toLowerCase()
      return keywords.some(kw => lower.includes(kw))
    },
    // --- END STUDY ADVISOR keyword detection ---

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

      // --- STUDY ADVISOR: route planner-related questions to the Study Advisor ---
      if (this.isPlannerQuestion(userPrompt)) {
        try {
          const res = await fetch('/api/ai/study-advisor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: userPrompt })
          })
          if (res.ok) {
            const data = await res.json()
            this.messages[this.messages.length - 1].content = data.answer
          } else {
            this.messages[this.messages.length - 1].content =
              'The Study Advisor could not process your request. Please try again.'
          }
        } catch {
          this.messages[this.messages.length - 1].content = 'Fehler: Backend nicht erreichbar.'
        } finally {
          this.loading = false
        }
        return
      }
      // --- END STUDY ADVISOR routing ---

      // Existing streaming chat for all non-planner questions
      try {
        const res = await fetch('/api/prompt', {
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
    async launchJobAgent() {
      this.jobAgentLoading = true
      this.jobAgentStatus = null
      try {
        const res = await fetch('/api/job-agent/run', { //F appeler B 
          method: 'POST',//Je ne veux pas seulement lire des données.Je veux déclencher une action.
          headers: { 'Content-Type': 'application/json' }, //BE : Je vais t'envoyer du JSON.
          body: JSON.stringify({}) 
        })
        if (res.ok) {
          this.jobAgentStatus = { type: 'success', message: 'Job Search Agent launched!' }
        } else {
          const data = await res.json().catch(() => ({}))
          this.jobAgentStatus = { type: 'error', message: data.detail || 'Failed to launch agent.' }
        }
      } catch {
        this.jobAgentStatus = { type: 'error', message: 'Error: Backend not reachable.' }
      } finally {
        this.jobAgentLoading = false
      }
    },
    async fetchCalendarEvents() {
      try {
        const res = await fetch('/api/calendar/events')
        if (res.ok) {
          this.calendarEvents = await res.json()
        }
      } catch {
        // Backend nicht erreichbar beim Start — kein Fehler anzeigen
      }
    },
    formatTime(isoString) {
      return new Date(isoString).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
    },
    formatDateHeader(isoString) {
      const d = new Date(isoString)
      const today = new Date()
      const tomorrow = new Date(today)
      tomorrow.setDate(today.getDate() + 1)
      if (d.toDateString() === today.toDateString()) return 'Heute'
      if (d.toDateString() === tomorrow.toDateString()) return 'Morgen'
      return d.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' })
    },
    parseEventType(title) {
      if (!title) return ''
      const m = title.match(/\b(PCÜ|SL|VL|UEb|UE|Ü|PR|SE|GK|TU|VO|KO|BS|EX)\s*$/i)
      return m ? m[1].toUpperCase() : ''
    },
    parseCourseName(title) {
      if (!title) return title
      return title.replace(/\s*\b(PCÜ|SL|VL|UEb|UE|Ü|PR|SE|GK|TU|VO|KO|BS|EX)\s*$/i, '').trim()
    },
    eventTypeClass(title) {
      const map = { SL: 'etype-sl', PCÜ: 'etype-pcu', VL: 'etype-vl', UE: 'etype-ue', Ü: 'etype-ue', UEB: 'etype-ue', PR: 'etype-pr', SE: 'etype-se' }
      return map[this.parseEventType(title)] || 'etype-other'
    },
    extractProfessor(description) {
      if (!description) return ''
      const m = description.match(/((?:Prof\.|Dr\.|Dipl\.)[^\n,]{2,40})/i)
      if (m) return m[1].trim()
      if (description.length > 0 && description.length < 60) return description.trim()
      return ''
    },
    //send(file) not possible
    async uploadIcsFile(event) {
      const file = event.target.files[0]
      if (!file) return
      event.target.value = ''

      const webhookUrl = import.meta.env.VITE_N8N_CALENDAR_WEBHOOK_URL
      if (!webhookUrl) {
        this.icsUploadStatus = { type: 'error', message: 'VITE_N8N_CALENDAR_WEBHOOK_URL nicht konfiguriert.' }
        return
      }

      this.icsUploadStatus = { type: 'info', message: `"${file.name}" wird gesendet...` }
      const formData = new FormData()
      formData.append('file', file)

      try {
        const res = await fetch(webhookUrl, { method: 'POST', body: formData })
        if (res.ok) {
          this.icsUploadStatus = { type: 'success', message: 'Kalender erfolgreich synchronisiert!' }
          setTimeout(() => this.fetchCalendarEvents(), 2000)
        } else {
          this.icsUploadStatus = { type: 'error', message: `Fehler vom n8n-Webhook (${res.status}).` }
        }
      } catch {
        this.icsUploadStatus = { type: 'error', message: 'n8n-Webhook nicht erreichbar.' }
      }
    },
    async clearCalendar() {
      if (!confirm('Alle Kalender-Events löschen?')) return
      this.calendarClearing = true
      try {
        const res = await fetch('/api/calendar/events', { method: 'DELETE' })
        if (res.ok) {
          this.calendarEvents = []
          this.calendarSearch = ''
          this.calendarShowAll = false
          this.icsUploadStatus = { type: 'success', message: 'Kalender geleert.' }
        } else {
          this.icsUploadStatus = { type: 'error', message: 'Fehler beim Löschen.' }
        }
      } catch {
        this.icsUploadStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.calendarClearing = false
      }
    },
    async uploadFile(event) {
      const file = event.target.files[0]
      if (!file || this.uploading) return
      event.target.value = ''

      if (file.type !== 'application/pdf') {
        this.uploadStatus = 'Nur PDF-Dateien sind erlaubt.'
        return
      }

      this.uploading = true
      this.uploadStatus = `"${file.name}" wird hochgeladen...`

      const formData = new FormData()
      formData.append('file', file)

      try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData })
        if (res.ok) {
          this.uploadStatus = ''
          this.messages.push({
            role: 'assistant',
            content:
              `✅ **"${file.name}"** wurde erfolgreich hochgeladen.\n\n` +
              `Das Dokument wird im Hintergrund verarbeitet. Du kannst in wenigen Sekunden Fragen dazu stellen.`
          })
          this.$nextTick(() => this.scrollToBottom())
        } else {
          const data = await res.json().catch(() => ({}))
          this.uploadStatus = data.detail || 'Fehler beim Hochladen.'
        }
      } catch {
        this.uploadStatus = 'Fehler: Backend nicht erreichbar.'
      } finally {
        this.uploading = false
      }
    },
    selectGradesPdf(event) {
      const file = event.target.files[0]
      if (!file) return
      this.gradesFile = file
      this.gradesFileName = file.name
      this.gradesData = null
      this.gradesStatus = null
      event.target.value = ''
    },
    async extractGrades() {
      if (!this.gradesFile) return
      this.gradesLoading = true
      this.gradesStatus = { type: 'info', message: 'PDF wird verarbeitet...' }
      const formData = new FormData()
      formData.append('file', this.gradesFile)
      try {
        const res = await fetch('/api/grades/upload', { method: 'POST', body: formData })
        if (res.ok) {
          this.gradesData = await res.json()
          this.gradesStatus = this.gradesData.courses.length > 0
            ? { type: 'success', message: `${this.gradesData.courses.length} Kurse extrahiert.` }
            : { type: 'info', message: 'Keine Noten im Dokument gefunden.' }
        } else {
          const data = await res.json().catch(() => ({}))
          this.gradesStatus = { type: 'error', message: data.detail || 'Fehler bei der Extraktion.' }
        }
      } catch {
        this.gradesStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.gradesLoading = false
      }
    },
    async fetchPlannerEvents() {
      try {
        const res = await fetch('/api/planner/events')
        if (res.ok) this.plannerEvents = await res.json()
      } catch {
        // Backend nicht erreichbar beim Start — kein Fehler anzeigen
      }
    },
    async submitPlannerEvent() {
      if (!this.plannerForm.title.trim() || !this.plannerForm.course_name.trim() || !this.plannerForm.date) return
      this.plannerSubmitting = true
      this.plannerStatus = null
      try {
        const res = await fetch('/api/planner/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: this.plannerForm.title.trim(),
            course_name: this.plannerForm.course_name.trim(),
            type: this.plannerForm.type,
            date: this.plannerForm.date,
            description: this.plannerForm.description.trim() || null,
          })
        })
        if (res.ok) {
          this.plannerStatus = { type: 'success', message: 'Event gespeichert!' }
          this.plannerForm = { title: '', course_name: '', type: 'EXAM', date: '', description: '' }
          await this.fetchPlannerEvents()
          setTimeout(() => { this.plannerStatus = null }, 3000)
        } else {
          const data = await res.json().catch(() => ({}))
          this.plannerStatus = { type: 'error', message: data.detail || 'Fehler beim Speichern.' }
        }
      } catch {
        this.plannerStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.plannerSubmitting = false
      }
    },
    async deletePlannerEvent(id) {
      try {
        const res = await fetch(`/api/planner/events/${id}`, { method: 'DELETE' })
        if (res.ok || res.status === 204) {
          this.plannerEvents = this.plannerEvents.filter(e => e.id !== id)
        }
      } catch {
        // silent
      }
    },
    plannerTypeLabel(type) {
      const map = { EXAM: 'Prüfung', ASSIGNMENT: 'Abgabe', PRESENTATION: 'Präsentation' }
      return map[type] || type
    },
    formatPlannerDate(dateStr) {
      return new Date(dateStr + 'T00:00:00').toLocaleDateString('de-DE', {
        day: '2-digit', month: '2-digit', year: 'numeric'
      })
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
.upload-btn--busy { opacity: 0.5; cursor: default; pointer-events: none; }

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

/* JOB AGENT */
.job-agent-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.job-agent-btn {
  width: 100%;
  padding: 8px 12px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.job-agent-btn:hover:not(:disabled) { background: var(--primary-hover); }
.job-agent-btn:disabled { background: var(--border); cursor: default; }

.job-agent-status {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}

.job-agent-status.success { color: #16a34a; }
.job-agent-status.error { color: #dc2626; }

/* KALENDER */
.dropdown--wide { min-width: 360px; max-width: 400px; }

.kalender-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.kalender-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
}

.kalender-upload-label {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 7px 10px;
  background: var(--primary);
  color: #fff;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.kalender-upload-label:hover { background: var(--primary-hover); }

.kalender-clear-btn {
  padding: 7px 10px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  color: var(--text-muted);
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}

.kalender-clear-btn:hover:not(:disabled) { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }
.kalender-clear-btn:disabled { opacity: 0.5; cursor: default; }

.kalender-search {
  width: 100%;
  margin-top: 8px;
  padding: 6px 10px;
  font-size: 12px;
  font-family: inherit;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.kalender-search:focus { border-color: var(--primary); }
.kalender-search::placeholder { color: var(--text-muted); }

.kalender-status {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}

.kalender-status.success { color: #16a34a; }
.kalender-status.error   { color: #dc2626; }
.kalender-status.info    { color: var(--text-muted); }

.kalender-empty {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 8px 0;
}

.kalender-groups {
  margin-top: 10px;
  max-height: 380px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kalender-date-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.kalender-card {
  display: flex;
  border-radius: 8px;
  border: 1px solid var(--border);
  overflow: hidden;
  margin-bottom: 6px;
  background: var(--surface-hover);
  border-left-width: 3px;
}

.kalender-card:last-child { margin-bottom: 0; }

/* Type accent colors via left border */
.etype-sl    { border-left-color: #6366f1; }
.etype-pcu   { border-left-color: #10b981; }
.etype-vl    { border-left-color: #3b82f6; }
.etype-ue    { border-left-color: #f59e0b; }
.etype-pr    { border-left-color: #14b8a6; }
.etype-se    { border-left-color: #8b5cf6; }
.etype-other { border-left-color: var(--border); }

.kalender-card-body {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.kalender-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.kalender-card-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kalender-card-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--primary-dim);
  color: var(--primary);
  white-space: nowrap;
  flex-shrink: 0;
}

.kalender-card-time {
  font-size: 11px;
  color: var(--primary);
  font-weight: 500;
}

.kalender-card-meta {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kalender-toggle-btn {
  width: 100%;
  margin-top: 10px;
  padding: 6px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.kalender-toggle-btn:hover { background: var(--surface-hover); color: var(--text); }

/* NOTEN */
.dropdown--extra-wide { min-width: 560px; max-width: 620px; }

.noten-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.noten-toolbar { display: flex; gap: 6px; }

.noten-upload-label {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 7px 10px;
  background: var(--primary);
  color: #fff;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.noten-upload-label:hover { background: var(--primary-hover); }

.noten-filename {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.noten-extract-btn {
  width: 100%;
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.noten-extract-btn:hover:not(:disabled) { background: var(--primary-hover); }
.noten-extract-btn:disabled { background: var(--border); cursor: default; }

.noten-status {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}

.noten-status.success { color: #16a34a; }
.noten-status.error   { color: #dc2626; }
.noten-status.info    { color: var(--text-muted); }

.noten-empty {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 8px 0;
}

.noten-results { margin-top: 12px; }

.noten-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.noten-student {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.noten-credits {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--primary-dim);
  color: var(--primary);
}

.noten-table-wrap {
  max-height: 320px;
  overflow-y: auto;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.noten-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.noten-table thead tr {
  background: var(--surface-hover);
  position: sticky;
  top: 0;
  z-index: 1;
}

.noten-table th {
  padding: 6px 8px;
  text-align: left;
  font-weight: 600;
  color: var(--text-muted);
  font-size: 11px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.noten-table td {
  padding: 6px 8px;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.noten-table tbody tr:last-child td { border-bottom: none; }
.noten-table tbody tr:hover { background: var(--surface-hover); }

.noten-grade {
  font-weight: 600;
  color: var(--primary);
}

/* PLANNER */
.planner-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.planner-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.planner-input {
  width: 100%;
  padding: 7px 10px;
  font-size: 12px;
  font-family: inherit;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.planner-input:focus { border-color: var(--primary); }
.planner-input::placeholder { color: var(--text-muted); }

.planner-submit-btn {
  width: 100%;
  padding: 8px 12px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  margin-top: 2px;
}

.planner-submit-btn:hover:not(:disabled) { background: var(--primary-hover); }
.planner-submit-btn:disabled { background: var(--border); cursor: default; }

.planner-status {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}

.planner-status.success { color: #16a34a; }
.planner-status.error   { color: #dc2626; }
.planner-status.info    { color: var(--text-muted); }

.planner-empty {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 8px 0;
}

.planner-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.planner-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--surface-hover);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.planner-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.planner-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.planner-delete-btn {
  background: none;
  border: none;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px 5px;
  border-radius: 4px;
  flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
}

.planner-delete-btn:hover { color: #dc2626; background: #fee2e2; }

.planner-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.planner-course {
  font-size: 11px;
  color: var(--text-muted);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.planner-type-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}

.ptype-exam         { background: #ede9fe; color: #7c3aed; }
.ptype-assignment   { background: #fef3c7; color: #d97706; }
.ptype-presentation { background: #dcfce7; color: #16a34a; }

.planner-card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.planner-date {
  font-size: 11px;
  color: var(--text-muted);
}

.planner-days {
  font-size: 11px;
  color: var(--text-muted);
  flex: 1;
}

.planner-priority {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 10px;
  white-space: nowrap;
}

.pprio-urgent { background: #fee2e2; color: #dc2626; }
.pprio-high   { background: #fef3c7; color: #d97706; }
.pprio-normal { background: #dcfce7; color: #16a34a; }
</style>
