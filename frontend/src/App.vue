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
          <div v-if="activePanel === item.id" :class="['dropdown', { 'dropdown--wide': item.id === 'kalender', 'dropdown--extra-wide': item.id === 'noten' || item.id === 'planner' || item.id === 'quiz' || item.id === 'sprachtutor' || item.id === 'career', 'dropdown--focus-full': item.id === 'focus-time' }]">
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

            <div v-if="item.id === 'career'" class="career-section">
              <div class="career-toolbar">
                <span class="career-toolbar-title">Career Profile</span>
                <button
                  @click.stop="fetchCareerAnalysis"
                  :disabled="careerLoading"
                  class="kalender-clear-btn"
                  title="Neu berechnen"
                >🔄</button>
              </div>

              <div class="career-scroll">
              <div v-if="careerLoading" class="career-empty">🤖 AI is analyzing your academic profile...</div>
              <div v-else-if="careerError" class="career-empty">{{ careerError }}</div>
              <div v-else-if="!careerAnalysis || !careerAnalysis.has_data" class="career-empty">
                Upload your Noten PDF first to get a personalized career analysis.
              </div>
              <template v-else>
                <span class="career-source-badge">✨ AI Analysis</span>

                <p v-if="careerAnalysis.summary" class="career-summary-text">{{ careerAnalysis.summary }}</p>

                <div v-if="bestCareerMatch" class="career-spotlight">
                  <p class="career-roles-title">🏆 Best Career Match</p>
                  <div class="career-spotlight-card">
                    <div class="career-spotlight-header">
                      <span class="career-spotlight-title">🥇 {{ bestCareerMatch.title }}</span>
                      <span class="career-spotlight-match">{{ bestCareerMatch.match_percent }}% Match</span>
                    </div>
                    <p class="career-spotlight-reason">{{ bestCareerMatch.reason }}</p>

                    <div class="career-spotlight-row">
                      <span class="career-spotlight-row-label">💼 Average Salary (Germany)</span>
                      <span class="career-spotlight-row-value">{{ bestCareerMatch.salary_range_eur || 'Not available' }}</span>
                    </div>
                    <div class="career-spotlight-row">
                      <span class="career-spotlight-row-label">📈 Market Demand</span>
                      <span class="career-spotlight-row-value">{{ marketDemandStars(bestCareerMatch.market_demand) }} {{ bestCareerMatch.market_demand }}</span>
                    </div>

                    <div v-if="bestCareerMatch.missing_skills.length" class="career-spotlight-block">
                      <span class="career-spotlight-block-label">❌ Missing Skills</span>
                      <ul class="career-role-tag-list">
                        <li v-for="(skill, mi) in bestCareerMatch.missing_skills" :key="mi">{{ skillIcon(skill) }} {{ skill }}</li>
                      </ul>
                    </div>

                    <div v-if="bestCareerMatch.recommended_certifications.length" class="career-spotlight-block">
                      <span class="career-spotlight-block-label">🎓 Recommended Certifications</span>
                      <ul class="career-role-list">
                        <li v-for="(cert, ci) in bestCareerMatch.recommended_certifications" :key="ci">{{ cert }}</li>
                      </ul>
                    </div>

                    <div v-if="bestCareerMatch.recommended_projects.length" class="career-spotlight-block">
                      <span class="career-spotlight-block-label">🚀 Recommended Portfolio Projects</span>
                      <ul class="career-role-list">
                        <li v-for="(proj, pi) in bestCareerMatch.recommended_projects" :key="pi">{{ proj }}</li>
                      </ul>
                    </div>

                    <p class="career-disclaimer">🤖 AI-generated estimate based on your transcript — not a guaranteed fact.</p>
                  </div>
                </div>

                <div class="career-metrics">
                  <div class="career-metric-card">
                    <span class="career-metric-label">🎯 Job Fit</span>
                    <span class="career-metric-value">{{ careerAnalysis.job_fit_percent }}%</span>
                  </div>
                  <div class="career-metric-card">
                    <span class="career-metric-label">🤖 AI Confidence</span>
                    <span class="career-metric-value">{{ careerAnalysis.confidence_percent }}%</span>
                  </div>
                </div>

                <div class="career-skills">
                  <div v-for="skill in careerAnalysis.skills" :key="skill.name" class="career-skill-block">
                    <div class="career-skill-header">
                      <span class="career-skill-name">{{ skill.name }}</span>
                      <span class="career-skill-percent">{{ skill.percent }}%</span>
                    </div>
                    <div class="career-skill-bar">
                      <div class="career-skill-bar-fill" :style="{ width: (careerBarsAnimated ? skill.percent : 0) + '%' }"></div>
                    </div>
                    <p class="career-skill-reason">{{ skill.reason }}</p>
                    <div v-if="skill.matched_courses.length" class="career-skill-courses">
                      <span class="career-skill-courses-label">Based on:</span>
                      <ul>
                        <li v-for="(c, ci) in skill.matched_courses" :key="ci">
                          ✓ {{ c.course_name }}<span v-if="c.grade"> ({{ c.grade }})</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div v-if="careerAnalysis.strengths.length || careerAnalysis.weak_areas.length" class="career-summary">
                  <p v-if="careerAnalysis.strengths.length" class="career-summary-line">
                    <strong>💪 Strengths:</strong> {{ careerAnalysis.strengths.join(', ') }}
                  </p>
                  <p v-if="careerAnalysis.weak_areas.length" class="career-summary-line">
                    <strong>📉 Weak areas:</strong> {{ careerAnalysis.weak_areas.join(', ') }}
                  </p>
                </div>

                <div class="career-roles">
                  <p class="career-roles-title">Empfohlene Rollen</p>
                  <p class="career-disclaimer">
                    🤖 AI-generated recommendations based on your transcript — not guaranteed facts. Verify certifications and requirements before relying on them.
                  </p>
                  <div v-for="role in careerAnalysis.roles" :key="role.title" class="career-role-card">
                    <div class="career-role-header">
                      <span class="career-role-title">{{ role.title }}</span>
                      <span class="career-role-match">{{ role.match_percent }}% Match</span>
                    </div>
                    <div class="career-role-demand">
                      <span class="career-role-demand-label">Market Demand</span>
                      <span :class="['career-demand-badge', 'career-demand-' + role.market_demand.toLowerCase().replace(' ', '-')]">
                        {{ marketDemandIcon(role.market_demand) }} {{ role.market_demand }}
                      </span>
                    </div>
                    <p class="career-role-reason">{{ role.reason }}</p>

                    <div v-if="role.missing_skills.length" class="career-role-block">
                      <span class="career-role-block-label">🧩 Missing Skills</span>
                      <ul class="career-role-tag-list">
                        <li v-for="(skill, mi) in role.missing_skills" :key="mi">{{ skill }}</li>
                      </ul>
                    </div>

                    <div v-if="role.recommended_certifications.length" class="career-role-block">
                      <span class="career-role-block-label">🎓 Recommended Certifications</span>
                      <ul class="career-role-list">
                        <li v-for="(cert, ci) in role.recommended_certifications" :key="ci">{{ cert }}</li>
                      </ul>
                    </div>

                    <div v-if="role.recommended_projects.length" class="career-role-block">
                      <span class="career-role-block-label">🛠️ Recommended Projects</span>
                      <ul class="career-role-list">
                        <li v-for="(proj, pi) in role.recommended_projects" :key="pi">{{ proj }}</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div v-if="careerAnalysis.recommended_learning_path.length" class="career-learning-path">
                  <p class="career-roles-title">📚 Recommended Learning Path</p>
                  <ul>
                    <li v-for="(step, si) in careerAnalysis.recommended_learning_path" :key="si">{{ step }}</li>
                  </ul>
                </div>
              </template>
              </div>
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
                <button
                  v-if="gradesData && gradesData.courses.length > 0"
                  @click.stop="clearGrades"
                  :disabled="gradesClearing"
                  class="kalender-clear-btn"
                  title="Noten löschen"
                >🗑</button>
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

            <div v-if="item.id === 'pruefungen'" class="pruefungen-section">
              <div v-if="upcomingExams.length === 0" class="pruefungen-empty">
                Noch keine Prüfungen eingetragen.<br>
                <span class="pruefungen-hint">Prüfungen im Planner-Tab mit Typ EXAM hinzufügen.</span>
              </div>
              <ul v-else class="pruefungen-list">
                <li v-for="exam in upcomingExams" :key="exam.id" class="pruefungen-item">
                  <span class="pruefungen-date">{{ formatPlannerDate(exam.date) }}</span>
                  <span class="pruefungen-title">{{ exam.title }}</span>
                  <span :class="['pruefungen-badge', 'pprio-' + exam.priority.toLowerCase()]">
                    {{ exam.days_remaining === 0 ? 'Heute' : exam.days_remaining + 'd' }}
                  </span>
                </li>
              </ul>
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

            <div v-if="item.id === 'focus-time'" class="focus-section" @click.stop>
              <div class="focus-config-grid">
                <label class="focus-field">
                  <span>Focus</span>
                  <input type="text" inputmode="decimal" v-model="focusForm.focusMinutes" @change="syncFocusSettings" @click.stop />
                </label>
                <label class="focus-field">
                  <span>Break</span>
                  <input type="text" inputmode="decimal" v-model="focusForm.breakMinutes" @change="syncFocusSettings" @click.stop />
                </label>
                <label class="focus-field">
                  <span>Cycles</span>
                  <input type="number" min="1" max="12" v-model.number="focusForm.cycles" @input="syncFocusSettings" @click.stop />
                </label>
              </div>

              <div v-if="focusThemes.length > 1" class="focus-theme-row">
                <button
                  v-for="theme in focusThemes"
                  :key="theme.id"
                  @click.stop="selectFocusTheme(theme.id)"
                  :class="['focus-theme-btn', { 'focus-theme-btn--active': focusTheme === theme.id }]"
                  type="button"
                >
                  <span>{{ theme.icon }}</span>
                  <span>{{ theme.label }}</span>
                </button>
              </div>

              <div :class="['focus-stage', 'focus-stage--' + focusTheme, { 'focus-stage--break': focusMode === 'break', 'focus-stage--success': focusSuccessPulse, 'focus-stage--final': focusFinalCountdownActive, 'focus-stage--break-starting': focusBreakStarting }]">
                <div class="focus-stage-top">
                  <span class="focus-mode-badge">{{ focusModeLabel }}</span>
                  <span class="focus-route">{{ focusRouteLabel }}</span>
                </div>
                <div class="focus-scene" :style="focusSceneStyle">
                  <template v-if="focusTheme === 'flight'">
                    <div class="flight-sky-layer flight-sky-layer--far"></div>
                    <div class="flight-sky-layer flight-sky-layer--near"></div>
                    <div class="flight-sun"></div>
                    <div class="flight-cloud flight-cloud--one"></div>
                    <div class="flight-cloud flight-cloud--two"></div>
                    <div class="flight-cloud flight-cloud--three"></div>

                    <svg class="flight-map" viewBox="0 0 1000 360" preserveAspectRatio="none" aria-hidden="true">
                      <defs>
                        <linearGradient id="flightRouteGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stop-color="#38bdf8" />
                          <stop offset="52%" stop-color="#f8fafc" />
                          <stop offset="100%" stop-color="#34d399" />
                        </linearGradient>
                      </defs>
                      <path class="flight-route-shadow" d="M92 257 C 280 96, 690 82, 908 238" />
                      <path class="flight-route-base" d="M92 257 C 280 96, 690 82, 908 238" />
                      <path class="flight-route-progress" d="M92 257 C 280 96, 690 82, 908 238" pathLength="100" />
                    </svg>

                    <div class="flight-city flight-city--depart">
                      <span class="flight-city-dot"></span>
                      <span class="flight-city-code">BER</span>
                      <strong>Berlin</strong>
                    </div>
                    <div class="flight-city flight-city--arrive">
                      <span class="flight-city-dot"></span>
                      <span class="flight-city-code">PAR</span>
                      <strong>Paris</strong>
                    </div>

                    <div class="flight-plane-shadow"></div>
                    <div class="flight-jet-trail">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                    <div class="flight-aircraft" aria-hidden="true">
                      <svg viewBox="0 0 260 156" role="img">
                        <defs>
                          <linearGradient id="planeBody" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#ffffff" />
                            <stop offset="42%" stop-color="#dbeafe" />
                            <stop offset="100%" stop-color="#64748b" />
                          </linearGradient>
                          <linearGradient id="planeWing" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#eff6ff" />
                            <stop offset="100%" stop-color="#475569" />
                          </linearGradient>
                          <filter id="planeGlow" x="-20%" y="-20%" width="140%" height="140%">
                            <feDropShadow dx="0" dy="10" stdDeviation="8" flood-color="#0f172a" flood-opacity="0.28" />
                          </filter>
                        </defs>
                        <g filter="url(#planeGlow)">
                          <path d="M98 78 L28 126 C21 131 25 140 34 138 L129 112 Z" fill="url(#planeWing)" />
                          <path d="M104 70 L22 32 C14 28 12 39 20 45 L128 102 Z" fill="url(#planeWing)" />
                          <path d="M54 77 L15 55 C8 51 5 58 10 64 L58 101 Z" fill="#94a3b8" />
                          <path d="M58 72 L22 102 C15 108 20 116 28 112 L72 96 Z" fill="#64748b" />
                          <path d="M36 75 C82 44 184 33 239 60 C252 66 252 80 239 88 C180 122 80 110 36 86 C28 82 28 80 36 75 Z" fill="url(#planeBody)" />
                          <path d="M205 59 C219 62 233 67 242 73 C235 78 220 82 204 84 C213 76 213 67 205 59 Z" fill="#f8fafc" opacity="0.92" />
                          <path d="M81 67 C119 53 169 53 203 64" fill="none" stroke="#0f172a" stroke-width="7" stroke-linecap="round" opacity="0.22" />
                          <g fill="#0ea5e9">
                            <circle cx="101" cy="64" r="4" />
                            <circle cx="119" cy="60" r="4" />
                            <circle cx="138" cy="58" r="4" />
                            <circle cx="157" cy="58" r="4" />
                            <circle cx="176" cy="61" r="4" />
                          </g>
                          <path d="M58 72 C102 49 174 45 223 63" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" opacity="0.55" />
                          <path d="M105 104 C119 102 134 106 139 116 C128 123 112 122 101 115 C98 111 100 106 105 104 Z" fill="#1e293b" />
                          <path d="M93 43 C108 40 123 43 130 52 C119 61 101 60 91 53 C88 49 89 45 93 43 Z" fill="#1e293b" />
                        </g>
                      </svg>
                    </div>

                    <div class="flight-hud">
                      <span>{{ focusModeLabel }}</span>
                      <strong>{{ focusRemainingLabel }}</strong>
                      <small>{{ focusProgressPct }}% · {{ focusCompletedCycles }} / {{ focusForm.cycles }} cycles</small>
                    </div>
                    <div v-if="focusFinalCountdownActive" class="flight-final-countdown">
                      <span>Final approach</span>
                      <strong>{{ focusRemainingSeconds }}</strong>
                    </div>
                    <div v-if="focusBreakStarting" class="flight-break-transition">
                      <span>Now we start the break</span>
                    </div>
                  </template>
                  <div v-if="focusMode === 'break'" class="focus-break-calm">Breathe</div>
                  <div v-if="focusSuccessPulse" class="focus-arrival">Arrived</div>
                </div>
              </div>

              <div class="focus-timer-card">
                <div class="focus-time-display">{{ focusRemainingLabel }}</div>
                <div class="focus-progress-wrap">
                  <div class="focus-progress-bar" :style="{ width: focusProgressPct + '%' }"></div>
                </div>
                <div class="focus-progress-meta">
                  <span>{{ focusProgressPct }}% complete</span>
                  <span>{{ focusCompletedCycles }} / {{ focusForm.cycles }} cycles</span>
                </div>
              </div>

              <div class="focus-action-grid">
                <button @click.stop="startFocusTimer" :disabled="focusStatus === 'running'" class="focus-primary-btn">Start</button>
                <button @click.stop="pauseFocusTimer" :disabled="focusStatus !== 'running'" class="focus-secondary-btn">Pause</button>
                <button @click.stop="resumeFocusTimer" :disabled="focusStatus !== 'paused'" class="focus-secondary-btn">Resume</button>
              </div>

              <div class="focus-stats">
                <div class="focus-stat-card">
                  <span class="focus-stat-value">{{ formatFocusMinutes(focusTodayStats.total_focus_time) }}</span>
                  <span class="focus-stat-label">minutes today</span>
                </div>
                <div class="focus-stat-card">
                  <span class="focus-stat-value">{{ focusTodayStats.sessions }}</span>
                  <span class="focus-stat-label">sessions</span>
                </div>
                <div class="focus-stat-card">
                  <span class="focus-stat-value">{{ focusTodayStats.completed_cycles }}</span>
                  <span class="focus-stat-label">cycles</span>
                </div>
              </div>

              <p class="focus-summary">{{ focusSummaryText }}</p>
              <p class="focus-motivation">{{ focusMotivation }}</p>
              <p v-if="focusStatusMessage" :class="['focus-status', focusStatusMessage.type]">{{ focusStatusMessage.message }}</p>
            </div>

            <!-- AI LANGUAGE TUTOR -->
            <div v-if="item.id === 'sprachtutor'" class="langtutor-section" @click.stop>
              <div class="langtutor-lang-row">
                <button
                  v-for="lang in langTutorLanguages"
                  :key="lang"
                  @click.stop="selectLangTutorLanguage(lang)"
                  :class="['langtutor-lang-chip', { 'langtutor-lang-chip--active': langTutorLanguage === lang }]"
                >{{ lang }}</button>
              </div>

              <div class="langtutor-progress">
                <span class="langtutor-progress-badge">🏆 {{ langTutorProgress.cefr_level }}</span>
                <div class="langtutor-xp-wrap">
                  <div class="langtutor-xp-bar"><div class="langtutor-xp-bar-fill" :style="{ width: langTutorXpBarPct + '%' }"></div></div>
                  <span class="langtutor-progress-xp">⭐ {{ langTutorProgress.xp }} XP</span>
                </div>
              </div>

              <div class="langtutor-messages" ref="langTutorMessages">
                <div v-if="langTutorHistory.length === 0" class="langtutor-empty">
                  Say or type something in {{ langTutorLanguage }} to start practicing!
                </div>
                <div v-for="(turn, i) in langTutorHistory" :key="i" :class="['langtutor-turn', turn.role]">
                  <div v-if="turn.role === 'user'" class="langtutor-bubble langtutor-bubble--user">{{ turn.text }}</div>
                  <div v-else class="langtutor-bubble langtutor-bubble--ai">
                    <p class="langtutor-reply">{{ turn.reply }}</p>
                    <div v-if="turn.correction" class="langtutor-block langtutor-block--correction">
                      <span class="langtutor-block-label">✏️ Correction</span>
                      <p>{{ turn.correction }}</p>
                      <p v-if="turn.explanation" class="langtutor-explanation">{{ turn.explanation }}</p>
                    </div>
                    <div v-if="turn.vocabulary && turn.vocabulary.length" class="langtutor-block langtutor-block--vocab">
                      <span class="langtutor-block-label">📚 Vocabulary</span>
                      <ul>
                        <li v-for="(v, vi) in turn.vocabulary" :key="vi"><strong>{{ v.word }}</strong> — {{ v.meaning }}</li>
                      </ul>
                    </div>
                    <div v-if="turn.better_version" class="langtutor-block langtutor-block--better">
                      <span class="langtutor-block-label">💡 Better version</span>
                      <p>{{ turn.better_version }}</p>
                    </div>
                    <div v-if="turn.next_question" class="langtutor-block langtutor-block--question">
                      <span class="langtutor-block-label">❓ Next question</span>
                      <p>{{ turn.next_question }}</p>
                    </div>
                  </div>
                </div>
                <div v-if="langTutorLoading" class="langtutor-bubble langtutor-bubble--ai langtutor-bubble--loading">⏳ Thinking...</div>
              </div>

              <p v-if="langTutorError" class="langtutor-status error">{{ langTutorError }}</p>
              <p v-if="langTutorSpeechError" class="langtutor-status error">{{ langTutorSpeechError }}</p>

              <div class="langtutor-input-row">
                <input
                  v-model="langTutorInput"
                  type="text"
                  :placeholder="langTutorListening ? 'Listening... I will send it when you stop talking' : `Type or speak in ${langTutorLanguage}...`"
                  @keydown.enter.exact.prevent="sendLangTutorMessage"
                  @click.stop
                  class="langtutor-input"
                />
                <button
                  v-if="speechSupported"
                  @click.stop="toggleLangTutorVoiceInput"
                  :class="['mic-btn', { 'mic-btn--listening': langTutorListening }]"
                  title="Speak"
                  type="button"
                >
                  <span v-if="langTutorListening" class="mic-pulse"></span>
                  🎤
                </button>
                <button
                  @click.stop="sendLangTutorMessage"
                  :disabled="langTutorLoading || !langTutorInput.trim()"
                  class="langtutor-send-btn"
                >➤</button>
              </div>
            </div>

            <!-- TUTOR / QUIZ -->
            <div v-if="item.id === 'quiz'" class="tutor-section" @click.stop>

              <!-- SETUP VIEW -->
              <div v-if="tutorView === 'setup'">
                <div class="tutor-doc-list">
                  <p class="tutor-label">Dokumente auswählen</p>
                  <div v-if="tutorDocuments.length === 0" class="tutor-empty">
                    Noch keine Dokumente hochgeladen. Lade zuerst ein PDF über das Büroklammer-Icon hoch.
                  </div>
                  <label v-for="doc in tutorDocuments" :key="doc" class="tutor-doc-item" @click.stop>
                    <input type="checkbox" :value="doc" v-model="tutorSelectedDocs" @click.stop />
                    <span class="tutor-doc-name">{{ doc }}</span>
                  </label>
                </div>
                <div class="tutor-config">
                  <div class="tutor-slider-row">
                    <span class="tutor-label">Anzahl Fragen</span>
                    <span class="tutor-slider-val">{{ tutorNumQuestions }}</span>
                  </div>
                  <input type="range" min="5" max="20" v-model.number="tutorNumQuestions" class="tutor-slider" @click.stop />
                  <input v-model="tutorCourseName" placeholder="Kursname (optional)" class="tutor-input" @click.stop />
                </div>
                <div class="tutor-action-row">
                  <button @click.stop="generateTutorQuiz" :disabled="tutorGenerating || tutorSelectedDocs.length === 0" class="tutor-generate-btn">
                    {{ tutorGenerating ? '⏳ Wird generiert...' : '✦ Quiz generieren' }}
                  </button>
                  <button @click.stop="fetchTutorStats" class="tutor-stats-btn">📊 Statistiken</button>
                </div>
                <p v-if="tutorStatus" :class="['tutor-status', tutorStatus.type]">{{ tutorStatus.message }}</p>
              </div>

              <!-- STATS VIEW -->
              <div v-if="tutorView === 'stats'">
                <div class="tutor-view-header">
                  <button @click.stop="tutorView = 'setup'" class="tutor-back-btn">← Zurück</button>
                  <span class="tutor-view-title">Meine Statistiken</span>
                </div>
                <div v-if="tutorStatsLoading" class="tutor-empty">Lade Statistiken...</div>
                <div v-else-if="tutorStats">
                  <div class="tutor-stats-summary">
                    <div class="tutor-stat-chip">
                      <span class="tutor-stat-val">{{ tutorStats.total_attempts }}</span>
                      <span class="tutor-stat-lbl">Versuche</span>
                    </div>
                    <div class="tutor-stat-chip">
                      <span class="tutor-stat-val">{{ tutorStats.average_score }}%</span>
                      <span class="tutor-stat-lbl">Ø Score</span>
                    </div>
                  </div>
                  <div v-if="tutorStats.weak_questions.length > 0" class="tutor-stats-block">
                    <p class="tutor-stats-heading">📉 Verbesserungspotenzial</p>
                    <div v-for="q in tutorStats.weak_questions" :key="q.question_id" class="tutor-stats-item tutor-stats-weak">
                      <span class="tutor-stats-rate">{{ q.success_rate }}%</span>
                      <span class="tutor-stats-text">{{ q.question_text }}</span>
                    </div>
                  </div>
                  <div v-if="tutorStats.strong_questions.length > 0" class="tutor-stats-block">
                    <p class="tutor-stats-heading">📈 Du kannst das gut</p>
                    <div v-for="q in tutorStats.strong_questions" :key="q.question_id" class="tutor-stats-item tutor-stats-strong">
                      <span class="tutor-stats-rate">{{ q.success_rate }}%</span>
                      <span class="tutor-stats-text">{{ q.question_text }}</span>
                    </div>
                  </div>
                  <div v-if="tutorStats.weak_questions.length === 0 && tutorStats.strong_questions.length === 0" class="tutor-empty">
                    Noch keine Daten. Mach zuerst ein Quiz!
                  </div>
                </div>
              </div>

              <!-- QUIZ VIEW -->
              <div v-if="tutorView === 'quiz' && tutorQuiz">
                <div class="tutor-quiz-header">
                  <span class="tutor-quiz-title">{{ tutorQuiz.title }}</span>
                  <span class="tutor-quiz-progress">{{ tutorCurrentQuestion + 1 }}&thinsp;/&thinsp;{{ tutorQuiz.questions.length }}</span>
                </div>
                <div class="tutor-progress-bar">
                  <div class="tutor-progress-fill" :style="{ width: tutorProgressPct + '%' }"></div>
                </div>
                <div class="tutor-question-card" v-if="currentQuestion">
                  <p class="tutor-question-text">{{ currentQuestion.question_text }}</p>
                  <div v-if="currentQuestion.question_type === 'MC'" class="tutor-options">
                    <button
                      v-for="opt in currentQuestion.options" :key="opt"
                      :class="['tutor-option', { 'tutor-option--selected': tutorAnswers[currentQuestion.id] === opt[0] }]"
                      @click.stop="selectAnswer(currentQuestion.id, opt[0])"
                    >
                      <span class="tutor-opt-key">{{ opt[0] }}</span>
                      <span class="tutor-opt-text">{{ opt.slice(3) }}</span>
                    </button>
                  </div>
                  <div v-if="currentQuestion.question_type === 'TF'" class="tutor-tf-options">
                    <button :class="['tutor-tf-btn', { 'tutor-tf-btn--selected': tutorAnswers[currentQuestion.id] === 'true' }]" @click.stop="selectAnswer(currentQuestion.id, 'true')">Wahr</button>
                    <button :class="['tutor-tf-btn', { 'tutor-tf-btn--selected': tutorAnswers[currentQuestion.id] === 'false' }]" @click.stop="selectAnswer(currentQuestion.id, 'false')">Falsch</button>
                  </div>
                </div>
                <div class="tutor-nav-row">
                  <button @click.stop="tutorCurrentQuestion--" :disabled="tutorCurrentQuestion === 0" class="tutor-nav-btn">← Zurück</button>
                  <button v-if="tutorCurrentQuestion < tutorQuiz.questions.length - 1" @click.stop="tutorCurrentQuestion++" class="tutor-nav-btn tutor-nav-btn--next">Weiter →</button>
                  <button v-else @click.stop="submitTutorQuiz" :disabled="!tutorAllAnswered || tutorSubmitting" class="tutor-nav-btn tutor-nav-btn--submit">
                    {{ tutorSubmitting ? '⏳' : '✓ Auswerten' }}
                  </button>
                </div>
                <p v-if="!tutorAllAnswered" class="tutor-unanswered">{{ tutorUnansweredCount }} Frage(n) noch offen</p>
              </div>

              <!-- RESULTS VIEW -->
              <div v-if="tutorView === 'results' && tutorResults">
                <div :class="['tutor-score-badge', tutorScoreClass]">
                  <span class="tutor-score-fraction">{{ tutorResults.score }}&thinsp;/&thinsp;{{ tutorResults.total_questions }}</span>
                  <span class="tutor-score-pct">{{ tutorResults.percentage }}%</span>
                </div>
                <div class="tutor-result-list">
                  <div
                    v-for="ans in tutorResults.answers" :key="ans.question_id"
                    :class="['tutor-result-item', ans.is_correct ? 'result-correct' : 'result-wrong']"
                  >
                    <div class="tutor-result-row">
                      <span class="tutor-result-icon">{{ ans.is_correct ? '✓' : '✗' }}</span>
                      <span class="tutor-result-q">{{ questionTextById(ans.question_id) }}</span>
                    </div>
                    <div v-if="!ans.is_correct" class="tutor-result-answer">
                      Deine Antwort: <strong>{{ ans.given_answer }}</strong> · Richtig: <strong>{{ ans.correct_answer }}</strong>
                    </div>
                    <div v-if="ans.explanation" class="tutor-result-explanation">💡 {{ ans.explanation }}</div>
                  </div>
                </div>
                <button @click.stop="resetTutorQuiz" class="tutor-restart-btn">Neues Quiz starten</button>
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
          <div class="welcome-datetime">
            <span class="welcome-date">{{ currentDateTimeStr.date }}</span>
            <span class="welcome-time">{{ currentDateTimeStr.time }}</span>
          </div>

          <div class="welcome-icon">✦</div>
          <h2>Wie kann ich dir helfen?</h2>
          <p>Stelle eine Frage oder lade ein Dokument hoch.</p>

          <div class="welcome-suggestions">
            <button
              v-for="s in quickSuggestions"
              :key="s"
              class="suggestion-btn"
              @click="suggestPrompt(s)"
            >{{ s }}</button>
          </div>

          <div class="welcome-cards">
            <div class="welcome-card">
              <span class="welcome-card-icon">📋</span>
              <div>
                <div class="welcome-card-title">Planner-aware</div>
                <div class="welcome-card-desc">Uses exams, assignments and presentations.</div>
              </div>
            </div>
            <div class="welcome-card">
              <span class="welcome-card-icon">📆</span>
              <div>
                <div class="welcome-card-title">Calendar-aware</div>
                <div class="welcome-card-desc">Uses upcoming classes and events.</div>
              </div>
            </div>
            <div class="welcome-card">
              <span class="welcome-card-icon">🧠</span>
              <div>
                <div class="welcome-card-title">AI Study Advisor</div>
                <div class="welcome-card-desc">Provides personalized study recommendations.</div>
              </div>
            </div>
            <div
              :class="['welcome-card', 'welcome-card--next-class', { 'welcome-card--clickable': nextClass }]"
              @click="nextClass && togglePanel('kalender')"
            >
              <span class="welcome-card-icon">🏫</span>
              <div class="next-class-body">
                <div class="welcome-card-title">Next Class</div>
                <template v-if="nextClass">
                  <div class="next-class-course" :title="nextClass.title">{{ extractCourseName(nextClass.title) }}</div>
                  <div class="next-class-meta">📅 {{ nextClassRelativeDate(nextClass.start_time) }}</div>
                  <div class="next-class-meta">🕐 {{ formatTime(nextClass.start_time) }} – {{ formatTime(nextClass.end_time) }}</div>
                  <div v-if="nextClass.location" class="next-class-meta">📍 {{ extractRoom(nextClass.location) }}</div>
                </template>
                <div v-else class="next-class-meta">No upcoming classes found.</div>
              </div>
            </div>
          </div>
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
          :placeholder="isListening ? 'Listening...' : 'Frage eingeben...'"
          @keydown.enter.exact.prevent="sendPrompt"
          @input="resizeTextarea"
          ref="textarea"
          rows="1"
        ></textarea>
        <select
          v-if="speechSupported"
          v-model="speechLang"
          class="lang-select"
          title="Voice recognition language"
          :disabled="isListening"
          @change="saveSpeechLang"
        >
          <option v-for="opt in speechLangOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <button
          v-if="speechSupported"
          @click="toggleVoiceInput"
          :class="['mic-btn', { 'mic-btn--listening': isListening }]"
          :title="isListening ? 'Stop listening' : 'Speak your question'"
          type="button"
        >
          <span v-if="isListening" class="mic-pulse"></span>
          🎤
        </button>
        <button @click="sendPrompt" :disabled="loading || !prompt.trim()" class="send-btn">
          ↑
        </button>
      </div>
      <p v-if="speechError" class="upload-status upload-status--error">{{ speechError }}</p>
      <p v-else-if="uploadStatus" class="upload-status">{{ uploadStatus }}</p>
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
      currentTime: new Date(),
      quickSuggestions: [
        'What should I focus on this week?',
        'Create a study plan based on my calendar.',
        'What classes do I have this week?',
        'I only have 3 hours today.',
      ],
      uploading: false,
      activePanel: null,
      uploadStatus: '',
      isListening: false,
      speechSupported: false,
      speechError: '',
      speechLang: 'auto',
      speechLangOptions: [
        { value: 'auto', label: 'Auto (' + (navigator.language || 'en-US') + ')' },
        { value: 'en-US', label: 'English (US)' },
        { value: 'en-GB', label: 'English (UK)' },
        { value: 'de-DE', label: 'Deutsch' }
      ],
      jobAgentLoading: false,
      jobAgentStatus: null,
      careerAnalysis: null,
      careerLoading: false,
      careerError: null,
      careerBarsAnimated: false,
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
      gradesClearing: false,
      plannerEvents: [],
      plannerSubmitting: false,
      plannerStatus: null,
      plannerForm: { title: '', course_name: '', type: 'EXAM', date: '', description: '' },
      tutorView: 'setup',
      tutorDocuments: [],
      tutorSelectedDocs: [],
      tutorNumQuestions: 10,
      tutorCourseName: '',
      tutorGenerating: false,
      tutorSubmitting: false,
      tutorStatus: null,
      tutorQuiz: null,
      tutorCurrentQuestion: 0,
      tutorAnswers: {},
      tutorResults: null,
      tutorStats: null,
      tutorStatsLoading: false,
      langTutorLanguages: ['English', 'German', 'French', 'Spanish', 'Italian'],
      langTutorLanguage: 'English',
      langTutorInput: '',
      langTutorHistory: [],
      langTutorLoading: false,
      langTutorError: null,
      langTutorListening: false,
      langTutorSpeechError: '',
      langTutorProgress: { language: 'English', cefr_level: 'A1', xp: 0 },
      focusForm: { focusMinutes: 30, breakMinutes: 5, cycles: 3 },
      focusTheme: 'flight',
      focusThemes: [
        { id: 'flight', label: 'Flight', icon: '✈️' }
      ],
      focusMode: 'focus',
      focusStatus: 'idle',
      focusRemainingSeconds: 30 * 60,
      focusCompletedCycles: 0,
      focusTodayStats: { date: '', sessions: 0, completed_cycles: 0, total_focus_time: 0, themes: [] },
      focusStatusMessage: null,
      focusSuccessPulse: false,
      focusBreakStarting: false,
      focusMotivationIndex: 0,
      focusMotivations: [
        'Small blocks become serious momentum.',
        'One clean interval. Keep the next minute simple.',
        'Deep work now, lighter brain later.',
        'Stay with the task. You are already moving.'
      ],
      navItems: [
        {
          id: 'pruefungen',
          label: 'Prüfungen',
          icon: '📅',
          entries: []
        },
        {
          id: 'quiz',
          label: 'Quiz',
          icon: '🧠',
          entries: []
        },
        {
          id: 'career',
          label: 'Career',
          icon: '💼',
          entries: []
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
        },
        {
          id: 'focus-time',
          label: 'Focus Time',
          icon: '⏱️',
          entries: []
        },
        {
          id: 'sprachtutor',
          label: 'Language Tutor',
          icon: '🗣️',
          entries: []
        }
      ]
    }
  },
  computed: {
    currentDateTimeStr() {
      const d = this.currentTime
      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
      const dd = String(d.getDate()).padStart(2, '0')
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const hh = String(d.getHours()).padStart(2, '0')
      const min = String(d.getMinutes()).padStart(2, '0')
      return {
        date: `${days[d.getDay()]}, ${dd}.${mm}.${d.getFullYear()}`,
        time: `${hh}:${min}`,
      }
    },
    nextClass() {
      // Reactive: re-evaluates every minute when currentTime ticks.
      // Reads from calendarEvents already loaded by fetchCalendarEvents().
      return this.calendarEvents
        .filter(e => new Date(e.start_time) > this.currentTime)
        .sort((a, b) => new Date(a.start_time) - new Date(b.start_time))[0] || null
    },
    upcomingExams() {
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      return this.plannerEvents
        .filter(e => e.type === 'EXAM' && new Date(e.date + 'T00:00:00') >= today)
        .sort((a, b) => new Date(a.date) - new Date(b.date))
    },
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
    langTutorLocale() {
      const map = { English: 'en-US', German: 'de-DE', French: 'fr-FR', Spanish: 'es-ES', Italian: 'it-IT' }
      return map[this.langTutorLanguage] || 'en-US'
    },
    bestCareerMatch() {
      return this.careerAnalysis?.roles?.length ? this.careerAnalysis.roles[0] : null
    },
    langTutorXpBarPct() {
      return this.langTutorProgress.xp % 100
    },
    focusTotalSeconds() {
      const minutes = this.focusMode === 'focus' ? this.focusForm.focusMinutes : this.focusForm.breakMinutes
      return this.focusSecondsFromMinutes(minutes, this.focusMode === 'focus' ? 30 : 5, this.focusMode === 'focus' ? 240 : 120)
    },
    focusProgressPct() {
      const elapsed = Math.max(0, this.focusTotalSeconds - this.focusRemainingSeconds)
      return Math.min(100, Math.round((elapsed / this.focusTotalSeconds) * 100))
    },
    focusSceneStyle() {
      const ratio = this.focusProgressPct / 100
      const takeoff = Math.min(1, ratio / 0.18)
      const landing = Math.max(0, (ratio - 0.82) / 0.18)
      const cruiseBob = Math.sin(ratio * Math.PI * 5) * 5
      const routeArc = Math.sin(ratio * Math.PI) * -82
      const flightY = 36 - (68 * takeoff) + (64 * landing) + routeArc + cruiseBob
      const tilt = ratio < 0.18
        ? -13 + (takeoff * 7)
        : ratio > 0.82
          ? -4 + (landing * 12)
          : Math.sin(ratio * Math.PI * 4) * 3
      return {
        '--focus-progress': this.focusProgressPct + '%',
        '--focus-ratio': ratio,
        '--flight-left': `calc(8% + ${ratio * 84}%)`,
        '--flight-y': flightY + 'px',
        '--flight-tilt': tilt + 'deg',
        '--flight-route-progress': this.focusProgressPct,
        '--flight-trail-opacity': this.focusMode === 'break' ? 0.18 : Math.min(0.82, 0.18 + ratio * 0.7),
        '--flight-shadow-scale': 1.25 - Math.sin(ratio * Math.PI) * 0.45
      }
    },
    focusRemainingLabel() {
      return this.formatFocusSeconds(this.focusRemainingSeconds)
    },
    focusFinalCountdownActive() {
      return this.focusStatus === 'running' && this.focusRemainingSeconds > 0 && this.focusRemainingSeconds <= 10
    },
    focusModeLabel() {
      return this.focusMode === 'focus' ? 'Focus Mode' : 'Break Mode'
    },
    focusRouteLabel() {
      if (this.focusMode === 'break') return 'Calm reset before the next round'
      return 'Berlin to Paris'
    },
    focusSummaryText() {
      return `Today you completed ${this.focusTodayStats.sessions} focus sessions and ${this.formatFocusMinutes(this.focusTodayStats.total_focus_time)} minutes of deep work.`
    },
    focusMotivation() {
      return this.focusMotivations[this.focusMotivationIndex % this.focusMotivations.length]
    },
    currentQuestion() {
      if (!this.tutorQuiz) return null
      return this.tutorQuiz.questions[this.tutorCurrentQuestion] || null
    },
    tutorProgressPct() {
      if (!this.tutorQuiz) return 0
      return ((this.tutorCurrentQuestion + 1) / this.tutorQuiz.questions.length) * 100
    },
    tutorAllAnswered() {
      if (!this.tutorQuiz) return false
      return this.tutorQuiz.questions.every(q => this.tutorAnswers[q.id] !== undefined)
    },
    tutorUnansweredCount() {
      if (!this.tutorQuiz) return 0
      return this.tutorQuiz.questions.filter(q => this.tutorAnswers[q.id] === undefined).length
    },
    tutorScoreClass() {
      if (!this.tutorResults) return ''
      const pct = this.tutorResults.percentage
      if (pct >= 80) return 'score-great'
      if (pct >= 60) return 'score-ok'
      return 'score-poor'
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
    this.fetchTutorDocuments()
    this.fetchGrades()
    this.fetchLangTutorProgress()
    this.fetchCareerAnalysis()
    this.fetchFocusStats()
    this._clockTimer = setInterval(() => { this.currentTime = new Date() }, 60000)
    this.speechSupported = !!(window.SpeechRecognition || window.webkitSpeechRecognition)
    this.speechLang = localStorage.getItem('speechLang') || 'auto'
    if (this.speechSupported) {
      console.log('[VoiceInput] SpeechRecognition supported. isSecureContext =', window.isSecureContext, 'navigator.language =', navigator.language)
      if (!window.isSecureContext) {
        console.warn('[VoiceInput] Page is not a secure context (https or localhost). Microphone access will be blocked by the browser.')
      }
    } else {
      console.warn('[VoiceInput] SpeechRecognition API not found on window. Voice input disabled. Use Chrome or Edge.')
    }
  },
  beforeUnmount() {
    clearInterval(this._clockTimer)
    clearInterval(this._focusTimer)
    if (this._recognition) this._recognition.abort()
    if (this._langTutorRecognition) this._langTutorRecognition.abort()
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
    normalizeFocusNumber(value, fallback, max, min = 0.1) {
      const n = Number(String(value).replace(',', '.'))
      if (!Number.isFinite(n)) return fallback
      return Math.min(max, Math.max(min, Math.round(n * 10) / 10))
    },
    focusSecondsFromMinutes(minutes, fallback, max) {
      return Math.max(1, Math.round(this.normalizeFocusNumber(minutes, fallback, max) * 60))
    },
    syncFocusSettings() {
      this.focusForm.focusMinutes = this.normalizeFocusNumber(this.focusForm.focusMinutes, 30, 240)
      this.focusForm.breakMinutes = this.normalizeFocusNumber(this.focusForm.breakMinutes, 5, 120)
      this.focusForm.cycles = this.normalizeFocusNumber(this.focusForm.cycles, 3, 12, 1)
      if (this.focusStatus === 'idle' || this.focusStatus === 'completed') {
        this.focusMode = 'focus'
        this.focusCompletedCycles = 0
        this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.focusMinutes, 30, 240)
        this.focusStatus = 'idle'
      }
    },
    selectFocusTheme(theme) {
      this.focusTheme = theme
      localStorage.setItem('focusTheme', theme)
    },
    formatFocusSeconds(totalSeconds) {
      const safe = Math.max(0, Math.floor(totalSeconds))
      const minutes = Math.floor(safe / 60)
      const seconds = safe % 60
      return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    },
    formatFocusMinutes(minutes) {
      const n = Number(minutes)
      if (!Number.isFinite(n)) return '0'
      return Number.isInteger(n) ? String(n) : n.toFixed(1)
    },
    todayIsoDate() {
      const d = new Date()
      const yyyy = d.getFullYear()
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      return `${yyyy}-${mm}-${dd}`
    },
    startFocusTimer() {
      this.syncFocusSettings()
      clearInterval(this._focusTimer)
      this.focusMode = 'focus'
      this.focusCompletedCycles = 0
      this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.focusMinutes, 30, 240)
      this.focusStatus = 'running'
      this.focusStatusMessage = null
      this.focusMotivationIndex = 0
      this.focusBreakStarting = false
      this._focusTimer = setInterval(() => this.tickFocusTimer(), 1000)
    },
    pauseFocusTimer() {
      if (this.focusStatus !== 'running') return
      clearInterval(this._focusTimer)
      this.focusStatus = 'paused'
      this.focusStatusMessage = { type: 'info', message: 'Timer paused.' }
    },
    resumeFocusTimer() {
      if (this.focusStatus !== 'paused') return
      clearInterval(this._focusTimer)
      this.focusStatus = 'running'
      this.focusStatusMessage = null
      this.focusBreakStarting = false
      this._focusTimer = setInterval(() => this.tickFocusTimer(), 1000)
    },
    resetFocusTimer() {
      clearInterval(this._focusTimer)
      this.syncFocusSettings()
      this.focusMode = 'focus'
      this.focusStatus = 'idle'
      this.focusCompletedCycles = 0
      this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.focusMinutes, 30, 240)
      this.focusStatusMessage = null
      this.focusSuccessPulse = false
      this.focusBreakStarting = false
    },
    skipToBreak() {
      if (this.focusStatus === 'completed') return
      this.focusMode = 'break'
      this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.breakMinutes, 5, 120)
      this.focusStatusMessage = { type: 'info', message: 'Skipped to break mode.' }
      if (this.focusStatus === 'idle') this.focusStatus = 'paused'
    },
    skipToFocus() {
      if (this.focusStatus === 'completed') return
      this.focusMode = 'focus'
      this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.focusMinutes, 30, 240)
      this.focusStatusMessage = { type: 'info', message: 'Skipped to focus mode.' }
      if (this.focusStatus === 'idle') this.focusStatus = 'paused'
    },
    tickFocusTimer() {
      if (this.focusStatus !== 'running') return
      this.focusRemainingSeconds = Math.max(0, this.focusRemainingSeconds - 1)
      if (this.focusMode === 'focus' && this.focusRemainingSeconds > 0 && this.focusRemainingSeconds % 420 === 0) {
        this.focusMotivationIndex++
      }
      if (this.focusRemainingSeconds === 0) this.completeFocusSegment()
    },
    async completeFocusSegment() {
      clearInterval(this._focusTimer)
      this.playFocusNotification()
      this.focusSuccessPulse = true
      setTimeout(() => { this.focusSuccessPulse = false }, 1400)

      if (this.focusMode === 'focus') {
        this.focusCompletedCycles += 1
        const statsSaved = await this.saveFocusSession()
        if (this.focusCompletedCycles >= this.focusForm.cycles) {
          this.focusStatus = 'completed'
          this.focusRemainingSeconds = 0
          this.focusStatusMessage = statsSaved
            ? { type: 'success', message: 'All focus cycles completed. Nice work.' }
            : { type: 'error', message: 'All cycles completed, but focus stats could not be saved.' }
          return
        }
        this.focusMode = 'break'
        this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.breakMinutes, 5, 120)
        this.focusBreakStarting = true
        setTimeout(() => { this.focusBreakStarting = false }, 2600)
        this.focusStatusMessage = statsSaved
          ? { type: 'success', message: 'Focus complete. Break started automatically.' }
          : { type: 'error', message: 'Break started, but focus stats could not be saved.' }
      } else {
        this.focusMode = 'focus'
        this.focusRemainingSeconds = this.focusSecondsFromMinutes(this.focusForm.focusMinutes, 30, 240)
        this.focusStatusMessage = { type: 'success', message: 'Break complete. Focus mode started automatically.' }
      }

      this.focusStatus = 'running'
      this._focusTimer = setInterval(() => this.tickFocusTimer(), 1000)
    },
    playFocusNotification() {
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext
        if (!AudioContext) return
        const ctx = new AudioContext()
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.setValueAtTime(740, ctx.currentTime)
        osc.frequency.setValueAtTime(940, ctx.currentTime + 0.12)
        gain.gain.setValueAtTime(0.0001, ctx.currentTime)
        gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.02)
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start()
        osc.stop(ctx.currentTime + 0.38)
      } catch {
        // Browsers may block audio until user interaction; the timer still works.
      }
    },
    async saveFocusSession() {
      try {
        const res = await fetch('/api/focus-time/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            date: this.todayIsoDate(),
            focus_minutes: this.focusForm.focusMinutes,
            break_minutes: this.focusForm.breakMinutes,
            completed_cycles: 1,
            selected_theme: this.focusTheme
          })
        })
        if (res.ok) {
          await this.fetchFocusStats()
          return true
        }
      } catch {
        return false
      }
      return false
    },
    async fetchFocusStats() {
      const day = this.todayIsoDate()
      try {
        const res = await fetch(`/api/focus-time/today?day=${day}`)
        if (res.ok) this.focusTodayStats = await res.json()
      } catch {
        // Keep the timer usable even when the backend is unavailable.
      }
      const savedTheme = localStorage.getItem('focusTheme')
      if (savedTheme && this.focusThemes.some(t => t.id === savedTheme)) this.focusTheme = savedTheme
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

    // --- VOICE INPUT (Web Speech API) ---
    saveSpeechLang() {
      localStorage.setItem('speechLang', this.speechLang)
      console.log('[VoiceInput] language set to', this.speechLang)
    },
    toggleVoiceInput() {
      if (!this.speechSupported) {
        this.speechError = 'Voice input is not supported in this browser. Please use Chrome or Edge.'
        console.warn('[VoiceInput] toggleVoiceInput called but speechSupported is false')
        return
      }
      if (this.isListening) {
        console.log('[VoiceInput] Manual stop requested by user')
        this._manualStop = true
        this._recognition?.stop()
      } else {
        this._manualStop = false
        this.startVoiceInput()
      }
    },
    // Asks for the microphone explicitly and "warms up" the capture device
    // before handing off to SpeechRecognition. Without this, Chrome on
    // Windows sometimes needs 1-2s to initialize the audio device after
    // recognition.start() is called, while the no-speech silence timer is
    // already running - causing a spurious "no-speech" error before the
    // user has a real chance to speak. Doing getUserMedia first removes
    // that race and also gives us a clean, separate permission error.
    async ensureMicrophoneAccess() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const tracks = stream.getAudioTracks()
        console.log('[VoiceInput] getUserMedia OK. Track(s):', tracks.map(t => ({ label: t.label, muted: t.muted, readyState: t.readyState })))
        tracks.forEach(t => t.stop())
        return { ok: true }
      } catch (err) {
        console.error('[VoiceInput] getUserMedia FAILED:', err.name, err.message)
        return { ok: false, err }
      }
    },
    async startVoiceInput(isRetry = false) {
      console.group(`[VoiceInput] startVoiceInput(isRetry=${isRetry})`)

      const micCheck = await this.ensureMicrophoneAccess()
      if (!micCheck.ok) {
        this.isListening = false
        const err = micCheck.err
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError' || err.name === 'SecurityError') {
          this.speechError = 'Microphone access was denied. Allow microphone permission for this site in your browser settings and try again.'
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          this.speechError = 'No microphone was found on this device.'
        } else if (err.name === 'NotReadableError') {
          this.speechError = 'The microphone is already in use by another application.'
        } else {
          this.speechError = `Could not access microphone (${err.name}).`
        }
        console.groupEnd()
        return
      }

      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      const recognition = new SpeechRecognition()
      recognition.lang = this.speechLang === 'auto' ? (navigator.language || 'en-US') : this.speechLang
      recognition.continuous = false
      recognition.interimResults = true
      recognition.maxAlternatives = 1

      let audioStarted = false
      let speechStarted = false
      let gotResult = false

      recognition.onstart = () => {
        console.log('[VoiceInput] onstart - session started, lang =', recognition.lang)
        this.isListening = true
        this.speechError = ''
      }
      recognition.onaudiostart = () => {
        audioStarted = true
        console.log('[VoiceInput] onaudiostart - mic audio capture is live')
      }
      recognition.onsoundstart = () => console.log('[VoiceInput] onsoundstart - sound detected (could be noise)')
      recognition.onspeechstart = () => {
        speechStarted = true
        console.log('[VoiceInput] onspeechstart - speech detected')
      }
      recognition.onspeechend = () => console.log('[VoiceInput] onspeechend - speech segment ended')
      recognition.onsoundend = () => console.log('[VoiceInput] onsoundend - sound ended')
      recognition.onaudioend = () => console.log('[VoiceInput] onaudioend - mic audio capture stopped')
      recognition.onnomatch = () => console.warn('[VoiceInput] onnomatch - audio captured but could not be matched to text')
      recognition.onresult = (event) => {
        gotResult = true
        let transcript = ''
        for (let i = 0; i < event.results.length; i++) transcript += event.results[i][0].transcript
        const last = event.results[event.results.length - 1]
        console.log('[VoiceInput] onresult:', JSON.stringify(transcript), 'isFinal =', last.isFinal)
        this.prompt = transcript
        this.$nextTick(() => this.resizeTextarea())
      }
      recognition.onerror = (event) => {
        console.error('[VoiceInput] onerror:', event.error, event.message || '(no message)', { audioStarted, speechStarted })
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          this.speechError = 'Microphone access was denied. Please allow microphone permission and try again.'
        } else if (event.error === 'audio-capture') {
          this.speechError = 'No microphone could be accessed. Check that a mic is connected and not used by another app.'
        } else if (event.error === 'network') {
          this.speechError = 'Voice recognition needs an internet connection to reach the speech service.'
        } else if (event.error === 'no-speech') {
          if (!audioStarted && !isRetry) {
            // Classic startup race: recognition ended before the mic was
            // even live. Safe to silently retry exactly once now that the
            // device has been warmed up by ensureMicrophoneAccess().
            console.warn('[VoiceInput] no-speech fired before onaudiostart - retrying once (startup race)')
            this._autoRetry = true
          } else if (!audioStarted) {
            this.speechError = 'No microphone audio was detected at all. Check Windows microphone privacy settings (Settings > Privacy & security > Microphone) and that the right input device is selected as default.'
          } else if (!speechStarted) {
            this.speechError = 'Microphone is capturing audio, but no speech was detected. Check your input volume/mic placement and try speaking immediately after the mic turns red.'
          } else {
            this.speechError = 'No speech detected. Please try again.'
          }
        } else if (event.error !== 'aborted') {
          this.speechError = `Voice recognition error: ${event.error}`
        }
      }
      recognition.onend = () => {
        console.log('[VoiceInput] onend', { audioStarted, speechStarted, gotResult })
        console.groupEnd()
        this.isListening = false
        this._recognition = null
        if (this._autoRetry && !this._manualStop) {
          this._autoRetry = false
          this.startVoiceInput(true)
        }
      }

      this._recognition = recognition
      try {
        console.log('[VoiceInput] calling recognition.start()')
        recognition.start()
      } catch (err) {
        console.error('[VoiceInput] recognition.start() threw:', err)
        this.speechError = 'Could not start voice recognition.'
        this.isListening = false
        console.groupEnd()
      }
    },
    // --- END VOICE INPUT ---

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

    suggestPrompt(text) {
      this.prompt = text
      this.$nextTick(() => {
        this.resizeTextarea()
        this.sendPrompt()
      })
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
    nextClassRelativeDate(isoString) {
      const eventDay = new Date(isoString)
      eventDay.setHours(0, 0, 0, 0)
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      const diff = Math.round((eventDay - today) / 86400000)
      if (diff === 0) return 'Today'
      if (diff === 1) return 'Tomorrow'
      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
      if (diff <= 6) return days[new Date(isoString).getDay()]
      const d = new Date(isoString)
      return `${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}.${d.getFullYear()}`
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
    // Strip course ID, module code, parenthesised annotations, and event-type suffix
    extractCourseName(title) {
      if (!title) return ''
      return title
        .replace(/^\s*\d{5,}\s*/, '')                                              // leading course ID e.g. 6123612
        .replace(/^\s*[A-Z]{1,4}\d+(?:\.\d+)?\s*/i, '')                           // module code e.g. B5.2, IN4.3
        .replace(/\s*\([^)]*\)/g, '')                                              // anything in (brackets): (PCÜ), (Schleinitz)
        .replace(/\s*\b(PCÜ|SL|VL|UEb|UE|Ü|PR|SE|GK|TU|VO|KO|BS|EX)\s*$/i, '') // bare event type at end
        .trim()
    },
    // Extract just the room identifier from a full location string
    extractRoom(location) {
      if (!location) return ''
      const s = location.trim()
      // Single letter + optional space + number at the end, e.g. "A 143", "A1.34"
      const m = s.match(/\b([A-Z]\.?\s*\d+[\w.]*)\s*$/i)
      if (m) return m[1].trim()
      // Plain number at the end
      const n = s.match(/\b(\d+[\w.]*)\s*$/)
      if (n) return n[1]
      // Fallback: last two tokens if string is long, else original
      const parts = s.split(/\s+/)
      return parts.length > 2 ? parts.slice(-2).join(' ') : s
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
          this.fetchTutorDocuments()
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
            ? { type: 'success', message: `${this.gradesData.courses.length} Kurse extrahiert und gespeichert.` }
            : { type: 'info', message: 'Keine Noten im Dokument gefunden.' }
          this.fetchCareerAnalysis()
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
    async fetchGrades() {
      try {
        const res = await fetch('/api/grades')
        if (res.ok) {
          const data = await res.json()
          if (data.courses && data.courses.length > 0) this.gradesData = data
        }
      } catch {
        // Backend nicht erreichbar beim Start — kein Fehler anzeigen
      }
    },
    async clearGrades() {
      if (!confirm('Alle gespeicherten Noten löschen?')) return
      this.gradesClearing = true
      try {
        const res = await fetch('/api/grades', { method: 'DELETE' })
        if (res.ok) {
          this.gradesData = null
          this.gradesFile = null
          this.gradesFileName = ''
          this.gradesStatus = { type: 'success', message: 'Noten gelöscht.' }
          this.fetchCareerAnalysis()
        } else {
          this.gradesStatus = { type: 'error', message: 'Fehler beim Löschen.' }
        }
      } catch {
        this.gradesStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.gradesClearing = false
      }
    },

    // --- CAREER PROFILE ---
    async fetchCareerAnalysis() {
      this.careerLoading = true
      this.careerError = null
      this.careerBarsAnimated = false
      try {
        const res = await fetch('/api/career/analysis')
        if (res.ok) {
          this.careerAnalysis = await res.json()
          // Render bars at 0% first, then flip to their real width on the next
          // frame so the CSS width transition actually has a "from" state to animate.
          await this.$nextTick()
          requestAnimationFrame(() => { this.careerBarsAnimated = true })
        } else {
          const data = await res.json().catch(() => ({}))
          this.careerError = data.detail || 'Career-Analyse konnte nicht geladen werden.'
        }
      } catch {
        this.careerError = 'Backend nicht erreichbar.'
      } finally {
        this.careerLoading = false
      }
    },
    marketDemandIcon(level) {
      const map = { 'Very High': '🟢', 'High': '🟡', 'Medium': '🟠', 'Low': '🔴' }
      return map[level] || '🟠'
    },
    marketDemandStars(level) {
      const map = { 'Very High': 5, 'High': 4, 'Medium': 3, 'Low': 2 }
      const filled = map[level] || 3
      return '★'.repeat(filled) + '☆'.repeat(5 - filled)
    },
    skillIcon(name) {
      const n = (name || '').toLowerCase()
      if (n.includes('azure')) return '☁️'
      if (n.includes('aws') || n.includes('amazon')) return '☁️'
      if (n.includes('gcp') || n.includes('google cloud') || n.includes('cloud')) return '☁️'
      if (n.includes('docker')) return '🐳'
      if (n.includes('kubernetes') || n.includes('k8s')) return '☸️'
      if (n.includes('spark')) return '⚡'
      if (n.includes('kafka')) return '📨'
      if (n.includes('power bi') || n.includes('tableau') || n.includes('dashboard') || n.includes('visualization')) return '📊'
      if (n.includes('etl') || n.includes('pipeline')) return '🔄'
      if (n.includes('linux')) return '🐧'
      if (n.includes('git')) return '🌿'
      if (n.includes('sql')) return '🗄️'
      if (n.includes('python')) return '🐍'
      if (n.includes('ci/cd') || n.includes('devops')) return '🔁'
      return '🧩'
    },
    // --- END CAREER PROFILE ---

    // --- AI LANGUAGE TUTOR ---
    selectLangTutorLanguage(lang) {
      if (lang === this.langTutorLanguage) return
      this.langTutorLanguage = lang
      this.langTutorHistory = []
      this.langTutorInput = ''
      this.langTutorError = null
      this.fetchLangTutorProgress()
    },
    async fetchLangTutorProgress() {
      try {
        const res = await fetch(`/api/ai/language-tutor/progress/${encodeURIComponent(this.langTutorLanguage)}`)
        if (res.ok) this.langTutorProgress = await res.json()
      } catch {
        // Backend nicht erreichbar beim Start — kein Fehler anzeigen
      }
    },
    scrollLangTutorToBottom() {
      const el = this.$refs.langTutorMessages
      if (el) el.scrollTop = el.scrollHeight
    },
    async sendLangTutorMessage() {
      const text = this.langTutorInput.trim()
      if (!text || this.langTutorLoading) return

      this.langTutorInput = ''
      this.langTutorError = null
      // Assistant turns carry the conversational reply + the question that was asked,
      // so Gemini sees what it already said and doesn't repeat itself.
      const historyForRequest = this.langTutorHistory.map(h => ({
        role: h.role,
        text: h.role === 'assistant' ? [h.reply, h.next_question].filter(Boolean).join(' ') : h.text
      }))
      this.langTutorHistory.push({ role: 'user', text })
      this.langTutorLoading = true
      await this.$nextTick()
      this.scrollLangTutorToBottom()

      try {
        const res = await fetch('/api/ai/language-tutor', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language: this.langTutorLanguage, message: text, history: historyForRequest })
        })
        if (res.ok) {
          const data = await res.json()
          this.langTutorHistory.push({ role: 'assistant', ...data })
          if (data.progress) this.langTutorProgress = data.progress
        } else {
          const data = await res.json().catch(() => ({}))
          this.langTutorError = data.detail || 'Der Sprachtutor konnte die Anfrage nicht verarbeiten.'
        }
      } catch {
        this.langTutorError = 'Backend nicht erreichbar.'
      } finally {
        this.langTutorLoading = false
        await this.$nextTick()
        this.scrollLangTutorToBottom()
      }
    },
    toggleLangTutorVoiceInput() {
      if (!this.speechSupported) {
        this.langTutorSpeechError = 'Voice input is not supported in this browser.'
        return
      }
      if (this.langTutorListening) {
        this._langTutorManualStop = true
        this._langTutorRecognition?.stop()
      } else {
        this._langTutorManualStop = false
        this.startLangTutorVoiceInput()
      }
    },
    async startLangTutorVoiceInput() {
      const micCheck = await this.ensureMicrophoneAccess()
      if (!micCheck.ok) {
        this.langTutorListening = false
        this.langTutorSpeechError = 'Microphone access was denied or unavailable.'
        return
      }

      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      const recognition = new SpeechRecognition()
      recognition.lang = this.langTutorLocale
      recognition.continuous = false
      recognition.interimResults = true
      recognition.maxAlternatives = 1

      recognition.onstart = () => {
        this.langTutorListening = true
        this.langTutorSpeechError = ''
      }
      recognition.onresult = (event) => {
        let transcript = ''
        for (let i = 0; i < event.results.length; i++) transcript += event.results[i][0].transcript
        this.langTutorInput = transcript
      }
      recognition.onerror = (event) => {
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          this.langTutorSpeechError = 'Microphone access was denied. Please allow microphone permission and try again.'
        } else if (event.error === 'no-speech') {
          this.langTutorSpeechError = 'No speech detected. Please try again.'
        } else if (event.error !== 'aborted') {
          this.langTutorSpeechError = `Voice recognition error: ${event.error}`
        }
      }
      recognition.onend = () => {
        this.langTutorListening = false
        this._langTutorRecognition = null
        // Voice conversation mode: once speech ends, send automatically instead
        // of waiting for the student to press the send button.
        if (!this._langTutorManualStop && this.langTutorInput.trim()) {
          this.sendLangTutorMessage()
        }
        this._langTutorManualStop = false
      }

      this._langTutorRecognition = recognition
      try {
        recognition.start()
      } catch {
        this.langTutorSpeechError = 'Could not start voice recognition.'
        this.langTutorListening = false
      }
    },
    // --- END AI LANGUAGE TUTOR ---

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
    },
    async fetchTutorDocuments() {
      try {
        const res = await fetch('/api/documents')
        if (res.ok) this.tutorDocuments = await res.json()
      } catch { /* silent */ }
    },
    async generateTutorQuiz() {
      if (this.tutorSelectedDocs.length === 0 || this.tutorGenerating) return
      this.tutorGenerating = true
      this.tutorStatus = { type: 'info', message: 'Quiz wird generiert, das dauert ca. 15 Sekunden...' }
      try {
        const res = await fetch('/api/tutor/quiz/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_documents: this.tutorSelectedDocs,
            num_questions: this.tutorNumQuestions,
            course_name: this.tutorCourseName.trim() || null,
          })
        })
        if (res.ok) {
          this.tutorQuiz = await res.json()
          this.tutorAnswers = {}
          this.tutorCurrentQuestion = 0
          this.tutorStatus = null
          this.tutorView = 'quiz'
        } else {
          const data = await res.json().catch(() => ({}))
          this.tutorStatus = { type: 'error', message: data.detail || 'Fehler bei der Quiz-Generierung.' }
        }
      } catch {
        this.tutorStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.tutorGenerating = false
      }
    },
    selectAnswer(questionId, answer) {
      this.tutorAnswers = { ...this.tutorAnswers, [questionId]: answer }
    },
    async submitTutorQuiz() {
      if (!this.tutorQuiz || !this.tutorAllAnswered || this.tutorSubmitting) return
      this.tutorSubmitting = true
      const answers = Object.entries(this.tutorAnswers).map(([question_id, given_answer]) => ({
        question_id: parseInt(question_id),
        given_answer,
      }))
      try {
        const res = await fetch(`/api/tutor/quiz/${this.tutorQuiz.id}/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers })
        })
        if (res.ok) {
          this.tutorResults = await res.json()
          this.tutorView = 'results'
        } else {
          const data = await res.json().catch(() => ({}))
          this.tutorStatus = { type: 'error', message: data.detail || 'Fehler beim Auswerten.' }
        }
      } catch {
        this.tutorStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.tutorSubmitting = false
      }
    },
    async fetchTutorStats() {
      this.tutorStatsLoading = true
      this.tutorView = 'stats'
      this.tutorStats = null
      try {
        const res = await fetch('/api/tutor/stats')
        if (res.ok) this.tutorStats = await res.json()
      } catch { /* silent */ } finally {
        this.tutorStatsLoading = false
      }
    },
    questionTextById(questionId) {
      if (!this.tutorQuiz) return ''
      const q = this.tutorQuiz.questions.find(q => q.id === questionId)
      return q ? q.question_text : ''
    },
    resetTutorQuiz() {
      this.tutorView = 'setup'
      this.tutorQuiz = null
      this.tutorResults = null
      this.tutorAnswers = {}
      this.tutorCurrentQuestion = 0
      this.tutorStatus = null
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
  font-size: 17px;
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
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 15px;
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

/* Date / time badge */
.welcome-datetime {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 18px;
  gap: 2px;
}
.welcome-date {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}
.welcome-time {
  font-size: 28px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.2;
}

/* Quick suggestion buttons */
.welcome-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin: 20px auto 0;
  max-width: 560px;
}
.suggestion-btn {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 7px 15px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
  white-space: nowrap;
}
.suggestion-btn:hover {
  background: var(--primary-dim);
  border-color: var(--primary);
  color: var(--primary);
}

/* Info cards (4-card row) */
.welcome-cards {
  display: flex;
  gap: 10px;
  margin: 24px auto 0;
  justify-content: center;
  flex-wrap: wrap;
  max-width: 840px;
  width: 100%;
}
.welcome-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  text-align: left;
  flex: 1 1 160px;
  max-width: 200px;
}
.welcome-card--clickable {
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, box-shadow 0.18s, transform 0.15s;
}
.welcome-card--clickable:hover {
  background: var(--surface-hover);
  border-color: var(--primary);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.10);
  transform: translateY(-2px);
}
.dark .welcome-card--clickable:hover {
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
}
.welcome-card-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
.welcome-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.welcome-card-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.45;
  margin-bottom: 2px;
}
.welcome-card-desc:last-child { margin-bottom: 0; }

/* Next Class card — body constrained; icon stays top-aligned like other cards */
.welcome-card--next-class { align-items: flex-start; }

/* min-width:0 is the key flex rule that allows shrinking below content size */
.next-class-body {
  min-width: 0;
  overflow: hidden;
  flex: 1;
}

/* Next Class card inner text */
.next-class-course {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.35;
  margin-bottom: 6px;
  max-width: 100%;
  word-break: break-word;
  overflow-wrap: break-word;
}
.next-class-meta {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.55;
  margin-bottom: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.next-class-meta:last-child { margin-bottom: 0; }

/* 2 columns on medium screens */
@media (max-width: 660px) {
  .welcome-card { flex: 1 1 calc(50% - 5px); max-width: calc(50% - 5px); }
}
/* 1 column on small screens */
@media (max-width: 420px) {
  .welcome-suggestions { flex-direction: column; align-items: stretch; }
  .suggestion-btn { white-space: normal; text-align: left; }
  .welcome-card { flex: 1 1 100%; max-width: 100%; }
}


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

.lang-select {
  flex-shrink: 0;
  height: 28px;
  max-width: 90px;
  font-size: 11px;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 0 4px;
  margin-bottom: 3px;
  cursor: pointer;
}

.lang-select:disabled { opacity: 0.5; cursor: default; }

.mic-btn {
  position: relative;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: transparent;
  color: var(--text-muted);
  border: none;
  font-size: 16px;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, background 0.15s;
  padding: 0;
}

.mic-btn:hover { color: var(--primary); background: var(--surface-hover); }

.mic-btn--listening {
  color: #fff;
  background: #ef4444;
}

.mic-btn--listening:hover { color: #fff; background: #ef4444; }

.mic-pulse {
  position: absolute;
  inset: -4px;
  border-radius: 12px;
  background: #ef4444;
  opacity: 0.5;
  animation: mic-pulse 1.4s ease-out infinite;
  z-index: -1;
}

@keyframes mic-pulse {
  0% { transform: scale(0.9); opacity: 0.5; }
  70% { transform: scale(1.6); opacity: 0; }
  100% { transform: scale(1.6); opacity: 0; }
}

.upload-status {
  max-width: 720px;
  margin: 6px auto 0;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}

.upload-status--error { color: #ef4444; }

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

/* CAREER */
.career-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.career-toolbar { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.career-toolbar-title { font-size: 13px; font-weight: 600; color: var(--text); }

.career-scroll {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  overscroll-behavior: contain;
  max-height: min(65vh, 560px);
  padding-right: 6px;
  margin-right: -6px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.career-scroll::-webkit-scrollbar { width: 8px; }
.career-scroll::-webkit-scrollbar-track { background: transparent; }
.career-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
.career-scroll::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

.career-spotlight-card {
  border: 1px solid var(--primary);
  border-radius: 12px;
  padding: 12px;
  background: linear-gradient(135deg, var(--primary-dim), transparent);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.career-spotlight-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px; }
.career-spotlight-title { font-size: 15px; font-weight: 700; color: var(--text); }
.career-spotlight-match {
  font-size: 13px;
  font-weight: 700;
  color: var(--primary);
  background: var(--surface);
  padding: 2px 10px;
  border-radius: 999px;
}

.career-spotlight-reason { margin: 0; font-size: 12px; color: var(--text-muted); line-height: 1.5; }

.career-spotlight-row { display: flex; align-items: center; justify-content: space-between; font-size: 12px; }
.career-spotlight-row-label { color: var(--text-muted); }
.career-spotlight-row-value { font-weight: 600; color: var(--text); }

.career-spotlight-block { margin-top: 2px; }
.career-spotlight-block-label { font-size: 11px; font-weight: 600; color: var(--text); display: block; margin-bottom: 3px; }

.career-empty { font-size: 13px; color: var(--text-muted); text-align: center; padding: 16px 4px; line-height: 1.5; }

.career-source-badge {
  align-self: flex-start;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--primary-dim);
  color: var(--primary);
}

.career-summary-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
}

.career-metrics { display: flex; gap: 8px; }

.career-metric-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 8px;
  background: var(--surface-hover);
  border-radius: 10px;
}

.career-metric-label { font-size: 11px; font-weight: 600; color: var(--text-muted); }
.career-metric-value { font-size: 18px; font-weight: 700; color: var(--primary); }

.career-skills { display: flex; flex-direction: column; gap: 12px; }

.career-skill-block { display: flex; flex-direction: column; gap: 3px; }

.career-skill-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.career-skill-name { color: var(--text); font-weight: 500; }
.career-skill-percent { color: var(--primary); font-weight: 700; font-size: 12px; }

.career-skill-bar {
  height: 7px;
  border-radius: 4px;
  background: var(--border);
  overflow: hidden;
}

.career-skill-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--primary), #22c55e);
  width: 0%;
  transition: width 0.8s cubic-bezier(0.22, 1, 0.36, 1);
}

.career-skill-reason { margin: 0; font-size: 11px; color: var(--text-muted); line-height: 1.4; }

.career-skill-courses { font-size: 11px; color: var(--text-muted); }
.career-skill-courses-label { font-weight: 600; }
.career-skill-courses ul { margin: 2px 0 0; padding-left: 4px; list-style: none; line-height: 1.6; }
.career-skill-courses li { color: var(--text); }

.career-roles-title { margin: 4px 0 6px; font-size: 12px; font-weight: 600; color: var(--text-muted); }

.career-disclaimer {
  margin: 0 0 8px;
  font-size: 11px;
  font-style: italic;
  color: var(--text-muted);
  line-height: 1.4;
}

.career-role-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  margin-bottom: 6px;
}

.career-role-header { display: flex; align-items: center; justify-content: space-between; }
.career-role-title { font-size: 13px; font-weight: 600; color: var(--text); }
.career-role-match { font-size: 12px; font-weight: 700; color: var(--primary); }
.career-role-reason { margin: 4px 0 0; font-size: 12px; color: var(--text-muted); line-height: 1.4; }

.career-role-block { margin-top: 8px; }
.career-role-block-label { font-size: 11px; font-weight: 600; color: var(--text); display: block; margin-bottom: 3px; }

.career-role-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.career-role-tag-list li {
  font-size: 11px;
  font-weight: 500;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 999px;
  padding: 2px 8px;
}

.career-role-list { margin: 0; padding-left: 16px; font-size: 11px; color: var(--text-muted); line-height: 1.6; }

.career-role-demand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.career-role-demand-label { font-size: 11px; color: var(--text-muted); }

.career-demand-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}

.career-demand-very-high { background: #dcfce7; color: #15803d; }
.career-demand-high { background: #fef9c3; color: #854d0e; }
.career-demand-medium { background: #ffedd5; color: #9a3412; }
.career-demand-low { background: #fee2e2; color: #b91c1c; }

.career-summary {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  background: var(--surface-hover);
  border-radius: 10px;
  padding: 8px 10px;
}

.career-summary-line { margin: 0; }
.career-summary-line + .career-summary-line { margin-top: 4px; }

.career-learning-path { font-size: 12px; color: var(--text-muted); }
.career-learning-path ul { margin: 4px 0 0; padding-left: 16px; line-height: 1.6; }

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

/* PRUEFUNGEN */
.pruefungen-section {
  margin-top: 4px;
}

.pruefungen-empty {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 8px 0;
  line-height: 1.6;
}

.pruefungen-hint {
  font-size: 11px;
  opacity: 0.75;
}

.pruefungen-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pruefungen-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 7px;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  font-size: 12px;
}

.pruefungen-date {
  font-weight: 600;
  color: var(--primary);
  white-space: nowrap;
  flex-shrink: 0;
}

.pruefungen-title {
  flex: 1;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pruefungen-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  white-space: nowrap;
  flex-shrink: 0;
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

/* FOCUS TIME */
.focus-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.focus-config-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.focus-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-hover);
}

.focus-field span {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.focus-field input {
  width: 100%;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 18px;
  font-weight: 700;
  outline: none;
}

.focus-theme-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.focus-theme-btn {
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.focus-theme-btn:hover { background: var(--surface-hover); color: var(--text); }
.focus-theme-btn--active { background: var(--primary-dim); border-color: var(--primary); color: var(--primary); }

.focus-stage {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 18%, rgba(34, 197, 94, 0.16), transparent 24%),
    linear-gradient(135deg, rgba(99, 102, 241, 0.14), rgba(20, 184, 166, 0.12));
}

.focus-stage--break {
  background:
    radial-gradient(circle at 20% 25%, rgba(125, 211, 252, 0.18), transparent 22%),
    linear-gradient(135deg, rgba(14, 165, 233, 0.11), rgba(34, 197, 94, 0.1));
}

.focus-stage-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.18);
}

.focus-mode-badge {
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255,255,255,0.72);
  color: #111827;
  font-size: 11px;
  font-weight: 800;
}

.dark .focus-mode-badge { background: rgba(15,17,23,0.72); color: var(--text); }

.focus-route {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  text-align: right;
}

.focus-scene {
  --focus-progress: 0%;
  --focus-ratio: 0;
  position: relative;
  height: 170px;
  overflow: hidden;
}

.focus-break-calm {
  position: absolute;
  left: 50%;
  bottom: 22px;
  transform: translateX(-50%);
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,0.7);
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
}

.focus-arrival {
  position: absolute;
  right: 24px;
  top: 64px;
  padding: 5px 10px;
  border-radius: 999px;
  background: #dcfce7;
  color: #166534;
  font-size: 12px;
  font-weight: 800;
  animation: focusPop 1.2s ease both;
}

.focus-timer-card {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-hover);
}

.focus-time-display {
  font-variant-numeric: tabular-nums;
  text-align: center;
  font-size: 42px;
  line-height: 1;
  font-weight: 800;
  color: var(--text);
  margin-bottom: 10px;
}

.focus-progress-wrap {
  height: 8px;
  border-radius: 999px;
  background: var(--border);
  overflow: hidden;
}

.focus-progress-bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22c55e, #3b82f6);
  transition: width 0.8s linear;
}

.focus-progress-meta,
.focus-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.focus-progress-meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.focus-action-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.focus-primary-btn,
.focus-secondary-btn {
  min-height: 34px;
  border-radius: 12px;
  border: 1px solid var(--border);
  font-size: 12px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.focus-primary-btn {
  background: linear-gradient(135deg, var(--primary), #0ea5e9);
  border-color: var(--primary);
  color: #fff;
  box-shadow: 0 12px 30px rgba(79,70,229,0.22);
}

.focus-primary-btn:hover:not(:disabled) { background: var(--primary-hover); }
.focus-secondary-btn { background: transparent; color: var(--text-muted); }
.focus-secondary-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--text); }
.focus-primary-btn:disabled,
.focus-secondary-btn:disabled { opacity: 0.45; cursor: default; }

.focus-stat-card {
  flex: 1;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-hover);
  text-align: center;
}

.focus-stat-value {
  display: block;
  color: var(--primary);
  font-size: 20px;
  font-weight: 800;
}

.focus-stat-label {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  margin-top: 2px;
}

.focus-summary,
.focus-motivation,
.focus-status {
  margin: 0;
  font-size: 12px;
  text-align: center;
}

.focus-summary { color: var(--text); font-weight: 600; }
.focus-motivation { color: var(--text-muted); }
.focus-status.success { color: #16a34a; }
.focus-status.error { color: #dc2626; }
.focus-status.info { color: var(--text-muted); }

@keyframes focusPop {
  0% { opacity: 0; transform: scale(0.75); }
  22% { opacity: 1; transform: scale(1.08); }
  100% { opacity: 0; transform: scale(1); }
}

.dropdown--focus-full {
  position: fixed;
  inset: 64px 18px 18px;
  width: auto;
  min-width: 0;
  max-width: none;
  padding: 0;
  border-radius: 18px;
  overflow: hidden;
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(22px);
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.22);
}

.dropdown--focus-full .dropdown-title,
.dropdown--focus-full > ul {
  display: none;
}

.dropdown--focus-full .focus-section {
  height: 100%;
  margin: 0;
  padding: 16px;
  border-top: none;
  gap: 12px;
  overflow-y: auto;
}

.dropdown--focus-full .focus-config-grid {
  order: 4;
  grid-template-columns: repeat(3, minmax(92px, 1fr));
}

.dropdown--focus-full .focus-theme-row {
  order: 0;
  max-width: 620px;
  margin: 0 auto;
}

.dropdown--focus-full .focus-stage {
  order: 1;
  position: relative;
  min-height: min(58vh, 620px);
  flex: 1;
  border-radius: 16px;
}

.dropdown--focus-full .focus-timer-card { order: 2; }
.dropdown--focus-full .focus-action-grid { order: 3; }
.dropdown--focus-full .focus-stats { order: 5; }
.dropdown--focus-full .focus-summary { order: 6; }
.dropdown--focus-full .focus-motivation { order: 7; }
.dropdown--focus-full .focus-status { order: 8; }

.dropdown--focus-full .focus-scene {
  height: min(58vh, 620px);
  min-height: 420px;
}

.dropdown--focus-full .focus-stage-top {
  position: absolute;
  left: 18px;
  right: 18px;
  top: 14px;
  z-index: 8;
  border-bottom: none;
  padding: 0;
  pointer-events: none;
}

.dropdown--focus-full .focus-mode-badge,
.dropdown--focus-full .focus-route {
  box-shadow: 0 14px 35px rgba(15, 23, 42, 0.16);
}

.dropdown--focus-full .focus-route {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255,255,255,0.64);
  backdrop-filter: blur(14px);
  color: #0f172a;
}

.dark .dropdown--focus-full .focus-route {
  background: rgba(15,23,42,0.58);
  color: #e2e8f0;
}

.dropdown--focus-full .focus-dashboard-row {
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(300px, 1.2fr);
  gap: 12px;
  align-items: stretch;
}

.dropdown--focus-full .focus-action-grid {
  max-width: 760px;
  width: 100%;
  margin: 0 auto;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: color-mix(in srgb, var(--surface-hover) 72%, transparent);
  backdrop-filter: blur(18px);
}

.dropdown--focus-full .focus-timer-card,
.dropdown--focus-full .focus-field,
.dropdown--focus-full .focus-stat-card {
  background: color-mix(in srgb, var(--surface-hover) 78%, transparent);
  backdrop-filter: blur(14px);
}

.focus-stage--flight {
  position: relative;
  isolation: isolate;
  background:
    radial-gradient(circle at 18% 18%, rgba(255,255,255,0.9), transparent 8%),
    linear-gradient(180deg, #60a5fa 0%, #93c5fd 42%, #dbeafe 72%, #f8fafc 100%);
}

.dark .focus-stage--flight {
  background:
    radial-gradient(circle at 80% 18%, rgba(226,232,240,0.76), transparent 7%),
    radial-gradient(circle at 20% 22%, rgba(96,165,250,0.22), transparent 20%),
    linear-gradient(180deg, #0f172a 0%, #1e1b4b 48%, #334155 100%);
}

.focus-stage--flight.focus-stage--break {
  background:
    radial-gradient(circle at 24% 18%, rgba(255,255,255,0.78), transparent 8%),
    linear-gradient(180deg, #7dd3fc 0%, #bfdbfe 55%, #f0f9ff 100%);
}

.focus-stage--final {
  box-shadow:
    inset 0 0 0 2px rgba(251,191,36,0.36),
    0 24px 80px rgba(245,158,11,0.22);
}

.focus-stage--final .flight-sun {
  animation: flightFinalSun 1s ease-in-out infinite;
}

.focus-stage--final .flight-aircraft {
  animation: flightFinalTilt 0.7s ease-in-out infinite;
}

.focus-stage--final .flight-hud {
  border-color: rgba(251,191,36,0.72);
  box-shadow:
    0 24px 80px rgba(15,23,42,0.34),
    0 0 0 8px rgba(251,191,36,0.16);
  animation: flightHudPulse 1s ease-in-out infinite;
}

.focus-stage--break-starting .flight-hud {
  opacity: 0.38;
  transform: translate(-50%, -50%) scale(0.96);
  transition: opacity 0.35s ease, transform 0.35s ease;
}

.flight-sky-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.flight-sky-layer--far {
  opacity: 0.22;
  background-image:
    radial-gradient(circle at 12% 38%, rgba(255,255,255,0.9) 0 2px, transparent 3px),
    radial-gradient(circle at 44% 24%, rgba(255,255,255,0.7) 0 1px, transparent 2px),
    radial-gradient(circle at 78% 42%, rgba(255,255,255,0.8) 0 2px, transparent 3px);
}

.dark .flight-sky-layer--far { opacity: 0.46; }

.flight-sky-layer--near {
  bottom: -1px;
  top: auto;
  height: 34%;
  background:
    linear-gradient(180deg, transparent, rgba(15,23,42,0.08)),
    radial-gradient(ellipse at 42% 100%, rgba(15,23,42,0.12), transparent 45%);
}

.flight-sun {
  position: absolute;
  width: 88px;
  height: 88px;
  right: 10%;
  top: 12%;
  border-radius: 999px;
  background: radial-gradient(circle, #fff7ed 0%, #fde68a 46%, rgba(251,191,36,0.2) 70%, transparent 72%);
  filter: blur(0.2px);
  opacity: 0.88;
}

.dark .flight-sun {
  width: 72px;
  height: 72px;
  background: radial-gradient(circle, #f8fafc 0%, #cbd5e1 50%, rgba(148,163,184,0.12) 74%, transparent 76%);
}

.flight-cloud {
  position: absolute;
  width: 210px;
  height: 70px;
  border-radius: 999px;
  background: rgba(255,255,255,0.72);
  filter: blur(0.2px);
  box-shadow:
    48px -18px 0 8px rgba(255,255,255,0.66),
    94px 4px 0 2px rgba(255,255,255,0.62),
    132px -10px 0 4px rgba(255,255,255,0.58);
  opacity: 0.54;
  animation: flightCloudDrift 42s linear infinite;
}

.flight-cloud--one { left: -260px; top: 16%; animation-duration: 54s; }
.flight-cloud--two { left: 22%; top: 34%; transform: scale(0.72); animation-duration: 68s; animation-delay: -24s; }
.flight-cloud--three { left: 62%; top: 19%; transform: scale(0.54); animation-duration: 74s; animation-delay: -46s; opacity: 0.38; }

.dark .flight-cloud {
  background: rgba(148,163,184,0.24);
  box-shadow:
    48px -18px 0 8px rgba(148,163,184,0.18),
    94px 4px 0 2px rgba(148,163,184,0.16),
    132px -10px 0 4px rgba(148,163,184,0.14);
}

.flight-map {
  position: absolute;
  inset: 7% 4% 5%;
  z-index: 2;
  overflow: visible;
}

.flight-route-shadow,
.flight-route-base,
.flight-route-progress {
  fill: none;
  stroke-linecap: round;
}

.flight-route-shadow {
  stroke: rgba(15,23,42,0.16);
  stroke-width: 18;
  filter: blur(10px);
}

.flight-route-base {
  stroke: rgba(255,255,255,0.52);
  stroke-width: 7;
  stroke-dasharray: 2 18;
}

.flight-route-progress {
  stroke: url(#flightRouteGradient);
  stroke-width: 7;
  stroke-dasharray: var(--flight-route-progress) 100;
  transition: stroke-dasharray 0.8s linear;
  filter: drop-shadow(0 0 10px rgba(56,189,248,0.48));
}

.flight-city {
  position: absolute;
  z-index: 5;
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 2px 8px;
  padding: 9px 12px;
  border: 1px solid rgba(255,255,255,0.5);
  border-radius: 14px;
  background: rgba(255,255,255,0.62);
  backdrop-filter: blur(16px);
  color: #0f172a;
  box-shadow: 0 18px 42px rgba(15,23,42,0.12);
}

.dark .flight-city {
  background: rgba(15,23,42,0.56);
  border-color: rgba(148,163,184,0.32);
  color: #f8fafc;
}

.flight-city--depart { left: 5.5%; bottom: 14%; }
.flight-city--arrive { right: 5.5%; bottom: 18%; }

.flight-city-dot {
  grid-row: span 2;
  width: 11px;
  height: 11px;
  border-radius: 999px;
  background: #22c55e;
  box-shadow: 0 0 0 7px rgba(34,197,94,0.18);
}

.flight-city--depart .flight-city-dot { background: #38bdf8; box-shadow: 0 0 0 7px rgba(56,189,248,0.18); }
.flight-city-code { font-size: 11px; font-weight: 900; color: var(--primary); letter-spacing: 0.08em; }
.flight-city strong { font-size: 14px; line-height: 1; }

.flight-aircraft,
.flight-plane-shadow,
.flight-jet-trail {
  position: absolute;
  left: var(--flight-left);
  top: calc(54% + var(--flight-y));
  z-index: 6;
  transition: left 0.8s linear, top 0.8s linear, transform 0.8s linear;
}

.flight-aircraft {
  width: clamp(116px, 16vw, 210px);
  aspect-ratio: 260 / 156;
  transform: translate(-50%, -50%) rotate(var(--flight-tilt)) perspective(700px) rotateX(8deg) rotateY(-10deg);
  transform-origin: 52% 50%;
  animation: flightMicroTilt 3.6s ease-in-out infinite;
  filter: saturate(1.05) contrast(1.02);
}

.flight-aircraft svg {
  width: 100%;
  height: 100%;
  display: block;
}

.flight-plane-shadow {
  width: clamp(92px, 12vw, 160px);
  height: 24px;
  border-radius: 999px;
  background: rgba(15,23,42,0.22);
  filter: blur(12px);
  transform: translate(-50%, 92px) scale(var(--flight-shadow-scale));
  z-index: 3;
  opacity: 0.38;
}

.flight-jet-trail {
  width: clamp(150px, 22vw, 320px);
  height: 54px;
  transform: translate(calc(-100% + 34px), -50%) rotate(var(--flight-tilt));
  transform-origin: right center;
  z-index: 4;
  opacity: var(--flight-trail-opacity);
  pointer-events: none;
}

.flight-jet-trail span {
  position: absolute;
  right: 0;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.34), rgba(255,255,255,0.78));
  filter: blur(2px);
  animation: flightTrailPulse 1.8s ease-in-out infinite;
}

.flight-jet-trail span:nth-child(1) { top: 14px; left: 0; }
.flight-jet-trail span:nth-child(2) { top: 25px; left: 34px; opacity: 0.78; animation-delay: -0.5s; }
.flight-jet-trail span:nth-child(3) { top: 36px; left: 74px; opacity: 0.55; animation-delay: -1s; }

.flight-hud {
  position: absolute;
  left: 50%;
  top: 48%;
  z-index: 7;
  min-width: min(440px, 72vw);
  padding: 16px 28px;
  border: 1px solid rgba(255,255,255,0.42);
  border-radius: 999px;
  background: rgba(9,13,23,0.72);
  color: #fff;
  text-align: center;
  transform: translate(-50%, -50%);
  backdrop-filter: blur(24px);
  box-shadow: 0 24px 80px rgba(15,23,42,0.34);
}

.flight-hud span,
.flight-hud small {
  display: block;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.72);
}

.flight-hud strong {
  display: block;
  margin: 2px 0 4px;
  font-size: clamp(42px, 6vw, 88px);
  line-height: 0.95;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.flight-final-countdown {
  position: absolute;
  right: clamp(18px, 5vw, 76px);
  top: clamp(86px, 18vh, 150px);
  z-index: 9;
  width: clamp(112px, 16vw, 172px);
  aspect-ratio: 1;
  border-radius: 999px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 2px;
  color: #fff;
  background:
    radial-gradient(circle, rgba(15,23,42,0.82), rgba(15,23,42,0.58)),
    conic-gradient(from 0deg, #f59e0b, #ef4444, #f59e0b);
  border: 1px solid rgba(255,255,255,0.34);
  backdrop-filter: blur(20px);
  box-shadow: 0 20px 70px rgba(15,23,42,0.34);
  animation: flightFinalBubble 1s ease-in-out infinite;
}

.flight-final-countdown span {
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.74);
}

.flight-final-countdown strong {
  font-size: clamp(46px, 7vw, 78px);
  line-height: 0.9;
  font-variant-numeric: tabular-nums;
}

.flight-break-transition {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 10;
  transform: translate(-50%, -50%);
  padding: 20px 32px;
  border-radius: 999px;
  color: #052e2b;
  background: rgba(204,251,241,0.88);
  border: 1px solid rgba(255,255,255,0.62);
  backdrop-filter: blur(24px);
  box-shadow:
    0 26px 90px rgba(15,23,42,0.28),
    0 0 0 14px rgba(20,184,166,0.16);
  animation: flightBreakStart 2.4s ease both;
}

.flight-break-transition span {
  display: block;
  font-size: clamp(20px, 3vw, 42px);
  font-weight: 900;
  letter-spacing: 0;
  white-space: nowrap;
}

.focus-stage--break .flight-aircraft,
.focus-stage--break .flight-jet-trail {
  opacity: 0.45;
}

.focus-stage--success .flight-aircraft {
  animation: flightLandingPulse 1.2s ease both;
}

@keyframes flightCloudDrift {
  from { translate: -20vw 0; }
  to { translate: 120vw 0; }
}

@keyframes flightMicroTilt {
  0%, 100% { margin-top: -3px; }
  50% { margin-top: 5px; }
}

@keyframes flightTrailPulse {
  0%, 100% { transform: scaleX(0.96); opacity: 0.62; }
  50% { transform: scaleX(1.04); opacity: 1; }
}

@keyframes flightLandingPulse {
  0% { scale: 1; }
  45% { scale: 1.035; }
  100% { scale: 1; }
}

@keyframes flightHudPulse {
  0%, 100% { scale: 1; }
  50% { scale: 1.025; }
}

@keyframes flightFinalSun {
  0%, 100% { opacity: 0.88; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.08); }
}

@keyframes flightFinalTilt {
  0%, 100% { margin-top: -5px; }
  50% { margin-top: 7px; }
}

@keyframes flightFinalBubble {
  0%, 100% { transform: scale(1); filter: saturate(1); }
  50% { transform: scale(1.06); filter: saturate(1.22); }
}

@keyframes flightBreakStart {
  0% { opacity: 0; transform: translate(-50%, -38%) scale(0.86); }
  18% { opacity: 1; transform: translate(-50%, -50%) scale(1.04); }
  72% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
  100% { opacity: 0; transform: translate(-50%, -62%) scale(0.96); }
}

@media (max-width: 760px) {
  .dropdown--focus-full {
    inset: 58px 8px 8px;
    border-radius: 14px;
  }

  .dropdown--focus-full .focus-section {
    padding: 10px;
  }

  .dropdown--focus-full .focus-theme-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    max-width: none;
  }

  .dropdown--focus-full .focus-scene {
    min-height: 380px;
    height: 52vh;
  }

  .flight-hud {
    min-width: min(330px, 86vw);
    padding: 13px 18px;
  }

  .flight-city {
    padding: 7px 9px;
  }

  .flight-city strong { font-size: 12px; }

  .dropdown--focus-full .focus-action-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* AI LANGUAGE TUTOR */
.langtutor-section { display: flex; flex-direction: column; gap: 10px; }

.langtutor-lang-row { display: flex; flex-wrap: wrap; gap: 6px; }

.langtutor-lang-chip {
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.langtutor-lang-chip:hover { border-color: var(--primary); color: var(--primary); }
.langtutor-lang-chip--active { background: var(--primary); border-color: var(--primary); color: #fff; }

.langtutor-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--surface-hover);
  border-radius: 10px;
}

.langtutor-progress-badge {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary);
  flex-shrink: 0;
}

.langtutor-xp-wrap { flex: 1; display: flex; align-items: center; gap: 8px; }

.langtutor-xp-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
}

.langtutor-xp-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), #f59e0b);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.langtutor-progress-xp { font-size: 11px; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }

.langtutor-messages {
  max-height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 2px;
}

.langtutor-empty { font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px 0; }

.langtutor-turn { display: flex; }
.langtutor-turn.user { justify-content: flex-end; }
.langtutor-turn.assistant { justify-content: flex-start; }

.langtutor-bubble {
  max-width: 90%;
  border-radius: 12px;
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.45;
}

.langtutor-bubble--user { background: var(--primary); color: #fff; border-bottom-right-radius: 3px; }
.langtutor-bubble--ai { background: var(--surface-hover); color: var(--text); border-bottom-left-radius: 3px; width: 100%; }
.langtutor-bubble--loading { color: var(--text-muted); font-style: italic; }

.langtutor-reply { margin: 0; }

.langtutor-block { margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.langtutor-block-label { font-size: 11px; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 2px; }
.langtutor-block p { margin: 0; }
.langtutor-block--correction p { color: #dc2626; }
.langtutor-explanation { color: var(--text-muted); font-size: 12px; margin-top: 2px; }
.langtutor-block--vocab ul { margin: 0; padding-left: 16px; }
.langtutor-block--vocab li { font-size: 12px; }
.langtutor-block--better p { color: #16a34a; }
.langtutor-block--question { border-top-color: var(--primary); }
.langtutor-block--question p { color: var(--primary); font-weight: 500; }

.langtutor-status { font-size: 12px; margin: 0; text-align: center; }
.langtutor-status.error { color: #dc2626; }

.langtutor-input-row { display: flex; align-items: center; gap: 6px; }

.langtutor-input {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  background: var(--input-bg);
  color: var(--text);
  outline: none;
}

.langtutor-input:focus { border-color: var(--primary); }

.langtutor-send-btn {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--primary);
  color: #fff;
  border: none;
  font-size: 15px;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.langtutor-send-btn:hover:not(:disabled) { background: var(--primary-hover); }
.langtutor-send-btn:disabled { background: var(--border); cursor: default; }

/* TUTOR */
.tutor-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.tutor-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 6px;
}

.tutor-doc-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 140px;
  overflow-y: auto;
  margin-bottom: 10px;
}

.tutor-doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
  transition: background 0.15s;
}

.tutor-doc-item:hover { background: var(--surface-hover); }
.tutor-doc-item input[type="checkbox"] { accent-color: var(--primary); flex-shrink: 0; }
.tutor-doc-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.tutor-config { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }

.tutor-slider-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tutor-slider-val {
  font-size: 13px;
  font-weight: 700;
  color: var(--primary);
}

.tutor-slider {
  width: 100%;
  accent-color: var(--primary);
}

.tutor-input {
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

.tutor-input:focus { border-color: var(--primary); }
.tutor-input::placeholder { color: var(--text-muted); }

.tutor-action-row { display: flex; gap: 6px; }

.tutor-generate-btn {
  flex: 1;
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

.tutor-generate-btn:hover:not(:disabled) { background: var(--primary-hover); }
.tutor-generate-btn:disabled { background: var(--border); cursor: default; }

.tutor-stats-btn {
  padding: 8px 10px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}

.tutor-stats-btn:hover { background: var(--surface-hover); color: var(--text); }

.tutor-status { margin: 8px 0 0; font-size: 12px; text-align: center; }
.tutor-status.success { color: #16a34a; }
.tutor-status.error   { color: #dc2626; }
.tutor-status.info    { color: var(--text-muted); }

.tutor-empty {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 8px 0;
}

/* Stats view */
.tutor-view-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.tutor-back-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.tutor-back-btn:hover { background: var(--surface-hover); color: var(--text); }

.tutor-view-title { font-size: 13px; font-weight: 600; color: var(--text); }

.tutor-stats-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tutor-stat-chip {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.tutor-stat-val { font-size: 18px; font-weight: 700; color: var(--primary); }
.tutor-stat-lbl { font-size: 10px; color: var(--text-muted); margin-top: 2px; }

.tutor-stats-block { margin-bottom: 10px; }

.tutor-stats-heading {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  margin: 0 0 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tutor-stats-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  margin-bottom: 4px;
  font-size: 12px;
}

.tutor-stats-weak  { background: #fef2f2; color: #991b1b; }
.tutor-stats-strong { background: #f0fdf4; color: #166534; }
.dark .tutor-stats-weak   { background: #2d1515; color: #fca5a5; }
.dark .tutor-stats-strong { background: #14231a; color: #86efac; }

.tutor-stats-rate { font-weight: 700; white-space: nowrap; flex-shrink: 0; }
.tutor-stats-text { flex: 1; line-height: 1.4; }

/* Quiz view */
.tutor-quiz-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.tutor-quiz-title { font-size: 13px; font-weight: 600; color: var(--text); }
.tutor-quiz-progress { font-size: 12px; color: var(--text-muted); white-space: nowrap; }

.tutor-progress-bar {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin-bottom: 12px;
  overflow: hidden;
}

.tutor-progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.tutor-question-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  background: var(--surface-hover);
  margin-bottom: 12px;
}

.tutor-question-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  margin: 0 0 12px;
  line-height: 1.5;
}

.tutor-options { display: flex; flex-direction: column; gap: 6px; }

.tutor-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
  font-size: 12px;
  color: var(--text);
  font-family: inherit;
}

.tutor-option:hover { border-color: var(--primary); background: var(--primary-dim); }
.tutor-option--selected { border-color: var(--primary); background: var(--primary-dim); }

.tutor-opt-key {
  font-weight: 700;
  color: var(--primary);
  flex-shrink: 0;
  width: 14px;
}

.tutor-opt-text { flex: 1; line-height: 1.4; }

.tutor-tf-options { display: flex; gap: 8px; }

.tutor-tf-btn {
  flex: 1;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  font-family: inherit;
}

.tutor-tf-btn:hover { border-color: var(--primary); background: var(--primary-dim); }
.tutor-tf-btn--selected { border-color: var(--primary); background: var(--primary-dim); color: var(--primary); }

.tutor-nav-row { display: flex; gap: 6px; }

.tutor-nav-btn {
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  font-family: inherit;
}

.tutor-nav-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--text); }
.tutor-nav-btn:disabled { opacity: 0.4; cursor: default; }
.tutor-nav-btn--next { margin-left: auto; }
.tutor-nav-btn--submit { margin-left: auto; background: var(--primary); color: #fff; border-color: var(--primary); }
.tutor-nav-btn--submit:hover:not(:disabled) { background: var(--primary-hover); }

.tutor-unanswered { font-size: 11px; color: var(--text-muted); text-align: center; margin: 6px 0 0; }

/* Results view */
.tutor-score-badge {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 10px;
  padding: 16px;
  border-radius: 10px;
  margin-bottom: 14px;
  text-align: center;
}

.score-great { background: #f0fdf4; }
.score-ok    { background: #fefce8; }
.score-poor  { background: #fef2f2; }
.dark .score-great { background: #14231a; }
.dark .score-ok    { background: #1f1a09; }
.dark .score-poor  { background: #2d1515; }

.tutor-score-fraction { font-size: 24px; font-weight: 700; color: var(--text); }
.tutor-score-pct { font-size: 16px; font-weight: 600; color: var(--text-muted); }

.tutor-result-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
  margin-bottom: 12px;
}

.tutor-result-item {
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
}

.result-correct { background: #f0fdf4; border: 1px solid #bbf7d0; }
.result-wrong   { background: #fef2f2; border: 1px solid #fecaca; }
.dark .result-correct { background: #14231a; border-color: #166534; }
.dark .result-wrong   { background: #2d1515; border-color: #991b1b; }

.tutor-result-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 4px; }
.tutor-result-icon { font-weight: 700; flex-shrink: 0; }
.result-correct .tutor-result-icon { color: #16a34a; }
.result-wrong   .tutor-result-icon { color: #dc2626; }
.tutor-result-q { flex: 1; color: var(--text); line-height: 1.4; font-weight: 500; }

.tutor-result-answer {
  font-size: 11px;
  color: var(--text-muted);
  margin: 2px 0;
  padding-left: 18px;
}

.tutor-result-explanation {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  padding-left: 18px;
  line-height: 1.4;
}

.tutor-restart-btn {
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

.tutor-restart-btn:hover { background: var(--primary-hover); }
</style>
