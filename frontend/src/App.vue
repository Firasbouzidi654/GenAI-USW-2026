<template>
  <div :class="['app', { dark: isDark }]" @click="closePanel">

    <!-- SIDEBAR -->
    <aside class="sidebar" @click.stop>
      <div class="sidebar-header">
        <span class="nav-logo">✦ AI Agent</span>
        <button class="theme-btn" @click.stop="toggleDark" :title="isDark ? 'Heller Modus' : 'Dunkler Modus'">
          <UiIcon :name="isDark ? 'brightness' : 'moon'" :fallback="isDark ? '☀️' : '🌙'" cls="theme-icon-img" />
        </button>
      </div>

      <button
        @click.stop="newChat"
        class="sidebar-btn sidebar-newchat"
        :disabled="!canStartNewChat"
        :title="canStartNewChat
          ? 'Neuen Chat starten (eigene Dokumente, getrennt vom bisherigen Verlauf)'
          : 'Stelle zuerst eine Frage im aktuellen Chat, bevor du einen neuen startest'"
      >
        ＋ Neuer Chat
      </button>
      <button
        @click.stop="syncLsf"
        :disabled="lsfSyncing"
        class="sidebar-btn sidebar-sync"
        title="Noten, Termine, Prüfungen und Kalender aus dem LSF neu laden"
      >
        <UiIcon name="back-up" fallback="🔄" cls="lsf-sync-icon" />
        {{ lsfSyncing ? 'Synchronisiere…' : 'LSF synchronisieren' }}
      </button>
      <span v-if="lsfSyncStatus" :class="['lsf-sync-status', lsfSyncStatus.type]">{{ lsfSyncStatus.message }}</span>

      <p class="sidebar-section-label">Bereiche</p>
      <div class="nav-items">
        <div v-for="item in navItems" :key="item.id" class="nav-item">
          <button
            @click="togglePanel(item.id)"
            :class="['nav-btn', { active: activePanel === item.id }]"
          >
            <UiIcon :name="item.iconName" :fallback="item.icon" cls="nav-icon-img" />
            {{ item.label }}
          </button>
          <div v-if="activePanel === item.id" :class="['dropdown', { 'dropdown--calendar': item.id === 'kalender', 'dropdown--extra-wide': item.id === 'noten' || item.id === 'planner' || item.id === 'quiz' || item.id === 'career' || item.id === 'profil' }]">
            <h4 class="dropdown-title">{{ item.label }}</h4>
            <ul>
              <li v-for="entry in item.entries" :key="entry">{{ entry }}</li>
            </ul>
            <div v-if="item.id === 'career'" class="career-section">
              <div class="career-toolbar">
                <span class="career-toolbar-title">Karriere-Profil</span>
                <button
                  @click.stop="fetchCareerAnalysis"
                  :disabled="careerLoading"
                  class="kalender-clear-btn"
                  title="Neu berechnen"
                ><UiIcon name="refresh" fallback="🔄" /></button>
              </div>

              <!-- CV / Lebenslauf-Upload -->
              <div class="cv-bar">
                <label class="cv-upload-label">
                  <UiIcon name="clip" fallback="📎" />
                  {{ cvUploading ? 'Lädt…' : (cvStatus && cvStatus.has_cv ? 'CV ersetzen' : 'Lebenslauf hochladen') }}
                  <input type="file" accept=".pdf" @change="uploadCv" :disabled="cvUploading" hidden />
                </label>
                <span v-if="cvStatus && cvStatus.has_cv" class="cv-filename" :title="cvStatus.filename">
                  ✓ {{ cvStatus.filename }}
                </span>
                <button
                  v-if="cvStatus && cvStatus.has_cv"
                  @click.stop="deleteCv"
                  class="cv-delete-btn"
                  title="CV entfernen"
                >✕</button>
              </div>
              <p v-if="cvStatus && cvStatus.has_cv" class="cv-hint">
                Dein Lebenslauf fließt in die Analyse ein. „Neu berechnen" für ein aktualisiertes Ergebnis.
              </p>

              <div class="career-scroll">
              <div v-if="careerLoading" class="career-empty"><UiIcon name="robot" fallback="🤖" /> Die KI analysiert dein akademisches Profil…</div>
              <div v-else-if="careerError" class="career-empty">{{ careerError }}</div>
              <div v-else-if="!careerAnalysis || !careerAnalysis.has_data" class="career-empty">
                Synchronisiere zuerst deine Noten (oder lade einen Lebenslauf hoch), um eine persönliche Karriereanalyse zu erhalten.
              </div>
              <template v-else>
                <span class="career-source-badge"><UiIcon name="sparkle" fallback="✨" /> KI-Analyse</span>

                <!-- DATENBASIS: was fließt in die Analyse ein -->
                <div v-if="careerAnalysis.data_sources" class="career-datasources">
                  <p class="career-ds-title">Datenbasis dieser Analyse</p>
                  <div class="career-ds-chips">
                    <span class="career-ds-chip on">
                      <UiIcon name="graduation-cap" fallback="🎓" /> {{ careerAnalysis.data_sources.grades_count }} Module (Noten)
                    </span>
                    <span :class="['career-ds-chip', careerAnalysis.data_sources.has_cv ? 'on' : 'off']">
                      <UiIcon name="clip" fallback="📎" /> Lebenslauf: {{ careerAnalysis.data_sources.has_cv ? 'ja' : 'nein' }}
                    </span>
                    <span :class="['career-ds-chip', careerAnalysis.data_sources.quiz_topics_count ? 'on' : 'off']">
                      <UiIcon name="web-test" fallback="🧠" />
                      {{ careerAnalysis.data_sources.quiz_topics_count }} Quiz-Themen
                      <template v-if="careerAnalysis.data_sources.quiz_topics_count"> · Ø {{ careerAnalysis.data_sources.quiz_avg_score }}%</template>
                    </span>
                  </div>
                  <div v-if="careerAnalysis.data_sources.quiz_topics.length" class="career-ds-quiz">
                    <span class="career-ds-quiz-label">Quiz-bestätigte Stärken (≥ 90 %):</span>
                    <span
                      v-for="t in careerAnalysis.data_sources.quiz_topics"
                      :key="t.topic"
                      :class="['career-ds-quiz-tag', 'plevel-' + t.level]"
                      :title="t.level"
                    >{{ t.topic }} · {{ t.score }}%</span>
                  </div>
                  <p v-else class="career-ds-hint">
                    Noch keine Quiz-bestätigte Stärke — erst ab <strong>90 %</strong> zählt ein Thema als belegte Stärke und fließt in die Jobsuche ein.
                  </p>
                  <div v-if="careerAnalysis.data_sources.job_keywords && careerAnalysis.data_sources.job_keywords.length" class="career-ds-quiz">
                    <span class="career-ds-quiz-label">Jobsuche basiert auf:</span>
                    <span
                      v-for="kw in careerAnalysis.data_sources.job_keywords"
                      :key="kw"
                      class="career-ds-quiz-tag career-ds-kw"
                    >{{ kw }}</span>
                  </div>
                </div>

                <p v-if="careerAnalysis.summary" class="career-summary-text">{{ careerAnalysis.summary }}</p>

                <div v-if="bestCareerMatch" class="career-spotlight">
                  <p class="career-roles-title"><UiIcon name="trophy" fallback="🏆" /> Bester Job-Match</p>
                  <div class="career-spotlight-card">
                    <div class="career-spotlight-header">
                      <span class="career-spotlight-title"><UiIcon name="medal" fallback="🥇" /> {{ bestCareerMatch.title }}</span>
                      <span class="career-spotlight-match">{{ bestCareerMatch.match_percent }}% Übereinstimmung</span>
                    </div>
                    <p class="career-spotlight-reason">{{ bestCareerMatch.reason }}</p>

                    <div class="career-spotlight-row">
                      <span class="career-spotlight-row-label"><UiIcon name="salary" fallback="💼" /> Werkstudenten-Vergütung</span>
                      <span class="career-spotlight-row-value">{{ bestCareerMatch.salary_range_eur || 'Nicht verfügbar' }}</span>
                    </div>
                    <div class="career-spotlight-row">
                      <span class="career-spotlight-row-label"><UiIcon name="trend-up" fallback="📈" /> Marktnachfrage</span>
                      <span class="career-spotlight-row-value">{{ marketDemandStars(bestCareerMatch.market_demand) }} {{ demandLabel(bestCareerMatch.market_demand) }}</span>
                    </div>

                    <div v-if="bestCareerMatch.missing_skills.length" class="career-spotlight-block">
                      <span class="career-spotlight-block-label">Fehlende Skills</span>
                      <ul class="career-role-tag-list">
                        <li v-for="(skill, mi) in bestCareerMatch.missing_skills" :key="mi">{{ skill }}</li>
                      </ul>
                    </div>

                    <div v-if="bestCareerMatch.recommended_certifications.length" class="career-spotlight-block">
                      <span class="career-spotlight-block-label"><UiIcon name="certificate" fallback="🎓" /> Empfohlene Zertifikate</span>
                      <ul class="career-role-list">
                        <li v-for="(cert, ci) in bestCareerMatch.recommended_certifications" :key="ci">{{ cert }}</li>
                      </ul>
                    </div>

                    <div v-if="bestCareerMatch.recommended_projects.length" class="career-spotlight-block">
                      <span class="career-spotlight-block-label"><UiIcon name="rocket" fallback="🚀" /> Empfohlene Portfolio-Projekte</span>
                      <ul class="career-role-list">
                        <li v-for="(proj, pi) in bestCareerMatch.recommended_projects" :key="pi">{{ proj }}</li>
                      </ul>
                    </div>

                    <p class="career-disclaimer"><UiIcon name="robot" fallback="🤖" /> KI-generierte Schätzung auf Basis deines Notenspiegels — keine garantierte Tatsache.</p>
                  </div>
                </div>

                <!-- VORGEFILTERTE PORTAL-SUCHEN (Werkstudent) -->
                <div v-if="bestCareerMatch && bestCareerMatch.search_links && bestCareerMatch.search_links.length" class="career-portals">
                  <p class="career-portals-label">Vorgefilterte Werkstudent-Suche für „{{ bestCareerMatch.title }}":</p>
                  <div class="career-portals-btns">
                    <a
                      v-for="link in bestCareerMatch.search_links"
                      :key="link.portal"
                      :href="link.url"
                      target="_blank"
                      rel="noopener"
                      class="career-portal-btn"
                    >{{ link.portal }} ↗</a>
                  </div>
                </div>

                <!-- ECHTE WERKSTUDENTENSTELLEN -->
                <div v-if="careerAnalysis.jobs && careerAnalysis.jobs.length" class="career-jobs">
                  <p class="career-jobs-title"><UiIcon name="briefcase" fallback="💼" /> Aktuelle Werkstudentenstellen <span class="career-jobs-source">via {{ careerAnalysis.job_source }}</span></p>
                  <a
                    v-for="(job, ji) in careerAnalysis.jobs"
                    :key="ji"
                    :href="job.url"
                    target="_blank"
                    rel="noopener"
                    class="career-job-card"
                  >
                    <div class="career-job-top">
                      <span class="career-job-title">{{ job.title }}</span>
                      <span v-if="job.salary" class="career-job-salary">{{ job.salary }}</span>
                    </div>
                    <div class="career-job-meta">
                      <span v-if="job.company">{{ job.company }}</span>
                      <span v-if="job.location">· {{ job.location }}</span>
                      <span v-if="job.remote" class="career-job-remote">· Remote</span>
                    </div>
                  </a>
                </div>
                <p v-else-if="bestCareerMatch" class="career-jobs-empty">
                  Über die freie Quelle ({{ careerAnalysis.job_source }}) wurden gerade keine
                  passenden Werkstudentenstellen gefunden — nutze die Buttons oben für aktuelle
                  Werkstudentenstellen auf LinkedIn, StepStone &amp; Indeed.
                </p>

                <div class="career-metrics">
                  <div class="career-metric-card">
                    <span class="career-metric-label"><UiIcon name="target" fallback="🎯" /> Job-Eignung</span>
                    <span class="career-metric-value">{{ careerAnalysis.job_fit_percent }}%</span>
                  </div>
                  <div class="career-metric-card">
                    <span class="career-metric-label"><UiIcon name="robot" fallback="🤖" /> KI-Konfidenz</span>
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
                      <span class="career-skill-courses-label">Basierend auf:</span>
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
                    <strong><UiIcon name="strength" fallback="💪" /> Stärken:</strong> {{ careerAnalysis.strengths.join(', ') }}
                  </p>
                  <p v-if="careerAnalysis.weak_areas.length" class="career-summary-line">
                    <strong><UiIcon name="trend-down" fallback="📉" /> Schwächen:</strong> {{ careerAnalysis.weak_areas.join(', ') }}
                  </p>
                </div>

                <div class="career-roles">
                  <p class="career-roles-title">Empfohlene Rollen</p>
                  <p class="career-disclaimer">
                    <UiIcon name="robot" fallback="🤖" /> KI-generierte Empfehlungen auf Basis deines Notenspiegels — keine garantierten Tatsachen. Prüfe Zertifikate und Anforderungen, bevor du dich darauf verlässt.
                  </p>
                  <div v-for="role in careerAnalysis.roles" :key="role.title" class="career-role-card">
                    <div class="career-role-header">
                      <span class="career-role-title">{{ role.title }}</span>
                      <span class="career-role-match">{{ role.match_percent }}% Übereinstimmung</span>
                    </div>
                    <div class="career-role-demand">
                      <span class="career-role-demand-label">Marktnachfrage</span>
                      <span :class="['career-demand-badge', 'career-demand-' + role.market_demand.toLowerCase().replace(' ', '-')]">
                        {{ demandLabel(role.market_demand) }}
                      </span>
                    </div>
                    <p class="career-role-reason">{{ role.reason }}</p>

                    <div v-if="role.missing_skills.length" class="career-role-block">
                      <span class="career-role-block-label">Fehlende Skills</span>
                      <ul class="career-role-tag-list">
                        <li v-for="(skill, mi) in role.missing_skills" :key="mi">{{ skill }}</li>
                      </ul>
                    </div>

                    <div v-if="role.recommended_certifications.length" class="career-role-block">
                      <span class="career-role-block-label"><UiIcon name="certificate" fallback="🎓" /> Empfohlene Zertifikate</span>
                      <ul class="career-role-list">
                        <li v-for="(cert, ci) in role.recommended_certifications" :key="ci">{{ cert }}</li>
                      </ul>
                    </div>

                    <div v-if="role.recommended_projects.length" class="career-role-block">
                      <span class="career-role-block-label"><UiIcon name="rocket" fallback="🛠️" /> Empfohlene Projekte</span>
                      <ul class="career-role-list">
                        <li v-for="(proj, pi) in role.recommended_projects" :key="pi">{{ proj }}</li>
                      </ul>
                    </div>

                    <div v-if="role.search_links && role.search_links.length" class="career-portals-btns career-portals-btns--sm">
                      <a
                        v-for="link in role.search_links"
                        :key="link.portal"
                        :href="link.url"
                        target="_blank"
                        rel="noopener"
                        class="career-portal-btn career-portal-btn--sm"
                      >{{ link.portal }} ↗</a>
                    </div>
                  </div>
                </div>

                <div v-if="careerAnalysis.recommended_learning_path.length" class="career-learning-path">
                  <p class="career-roles-title"><UiIcon name="book" fallback="📚" /> Empfohlener Lernpfad</p>
                  <ul>
                    <li v-for="(step, si) in careerAnalysis.recommended_learning_path" :key="si">{{ step }}</li>
                  </ul>
                </div>
              </template>
              </div>
            </div>

            <div v-if="item.id === 'kalender'" class="kalender-section">
              <div class="cal-toolbar">
                <div class="cal-views">
                  <button :class="['cal-view-btn', { active: calView === 'day' }]" @click.stop="calView = 'day'">Tag</button>
                  <button :class="['cal-view-btn', { active: calView === 'week' }]" @click.stop="calView = 'week'">Woche</button>
                  <button :class="['cal-view-btn', { active: calView === 'month' }]" @click.stop="calView = 'month'">Monat</button>
                </div>
                <div class="cal-nav">
                  <button class="cal-nav-btn" @click.stop="calPrev" title="Zurück">‹</button>
                  <button class="cal-today-btn" @click.stop="calToday">Heute</button>
                  <button class="cal-nav-btn" @click.stop="calNext" title="Weiter">›</button>
                </div>
              </div>
              <div class="cal-period-row">
                <span class="cal-period">{{ calPeriodLabel }}</span>
                <button v-if="!calShowAddForm" class="cal-add-btn" @click.stop="calShowAddForm = true">＋ Eigener Termin</button>
              </div>

              <!-- Eigenen Termin hinzufügen -->
              <form v-if="calShowAddForm" class="cal-add-form" @submit.prevent="addUserEvent" @click.stop>
                <input v-model="userEventForm.title" placeholder="Titel *" required class="cal-add-input" />
                <div class="cal-add-grid">
                  <input type="date" v-model="userEventForm.date" required class="cal-add-input" />
                  <input type="time" v-model="userEventForm.start" required class="cal-add-input" />
                  <input type="time" v-model="userEventForm.end" required class="cal-add-input" />
                </div>
                <input v-model="userEventForm.location" placeholder="Ort (optional)" class="cal-add-input" />
                <div class="cal-add-actions">
                  <button type="submit" :disabled="userEventSaving" class="cal-add-save">{{ userEventSaving ? 'Speichert…' : 'Hinzufügen' }}</button>
                  <button type="button" class="cal-add-cancel" @click.stop="calShowAddForm = false">Abbrechen</button>
                </div>
                <p v-if="userEventStatus" :class="['tutor-status', userEventStatus.type]">{{ userEventStatus.message }}</p>
              </form>

              <div class="cal-legend">
                <span class="cal-legend-item"><span class="cal-dot cal-dot--class"></span>Vorlesung</span>
                <span class="cal-legend-item"><span class="cal-dot cal-dot--user"></span>Eigener Termin</span>
                <span class="cal-legend-item"><span class="cal-dot cal-dot--deadline"></span>Deadline</span>
              </div>

              <!-- MONAT -->
              <div v-if="calView === 'month'" class="cal-month">
                <div v-for="d in calWeekdayLabels" :key="'h'+d" class="cal-weekday">{{ d }}</div>
                <template v-for="(week, wi) in calMonthGrid" :key="wi">
                  <div
                    v-for="day in week"
                    :key="day.key"
                    :class="['cal-cell', { 'cal-cell--out': !day.inMonth, 'cal-cell--today': day.isToday }]"
                    @click.stop="calSelectDay(day.date)"
                  >
                    <span class="cal-cell-num">{{ day.date.getDate() }}</span>
                    <div class="cal-cell-events">
                      <span
                        v-for="e in day.events.slice(0, 3)"
                        :key="e.id"
                        :class="['cal-chip', 'cal-chip--' + e.kind]"
                        :title="e.title"
                      >{{ e.title }}</span>
                      <span v-if="day.events.length > 3" class="cal-more">+{{ day.events.length - 3 }}</span>
                    </div>
                  </div>
                </template>
              </div>

              <!-- WOCHE -->
              <div v-else-if="calView === 'week'" class="cal-week">
                <div
                  v-for="day in calWeekDays"
                  :key="day.key"
                  :class="['cal-week-col', { 'cal-week-col--today': day.isToday }]"
                >
                  <div class="cal-week-head" @click.stop="calSelectDay(day.date)">
                    <span class="cal-week-dow">{{ calWeekdayLabels[(day.date.getDay() + 6) % 7] }}</span>
                    <span class="cal-week-date">{{ day.date.getDate() }}.{{ day.date.getMonth() + 1 }}.</span>
                  </div>
                  <div class="cal-week-events">
                    <div v-if="day.events.length === 0" class="cal-week-empty">–</div>
                    <div v-for="e in day.events" :key="e.id" :class="['cal-event', 'cal-event--' + e.kind]" :title="e.location || e.title">
                      <span class="cal-event-time">{{ e.allDay ? '●' : formatTime(e.start_time) }}</span>
                      <span class="cal-event-name">{{ e.title }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- TAG -->
              <div v-else class="cal-day">
                <div v-if="calDayEvents.length === 0" class="kalender-empty">Keine Termine an diesem Tag.</div>
                <div v-for="e in calDayEvents" :key="e.id" :class="['cal-day-event', 'cal-day-event--' + e.kind]">
                  <div class="cal-day-time">
                    <template v-if="!e.allDay">
                      <span>{{ formatTime(e.start_time) }}</span>
                      <span class="cal-day-time-end">{{ formatTime(e.end_time) }}</span>
                    </template>
                    <span v-else class="cal-day-allday">ganztägig</span>
                  </div>
                  <div class="cal-day-body">
                    <div class="cal-day-top">
                      <span class="cal-day-name">{{ e.title }}</span>
                      <span v-if="e.kind === 'deadline'" class="kalender-card-badge">{{ plannerTypeLabel(e.deadlineType) }}</span>
                      <span v-else-if="e.kind === 'user'" class="kalender-card-badge cal-badge-user">Eigener Termin</span>
                    </div>
                    <div v-if="e.location" class="kalender-card-meta"><UiIcon name="location" fallback="📍" /> {{ e.location }}</div>
                    <button v-if="e.kind === 'user'" class="cal-day-del" @click.stop="deleteUserEvent(e.rawId)">Termin löschen</button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="item.id === 'profil'" class="profil-section">
              <!-- MODULHANDBUCH (Vorgänger-Graph für Wissenslücken) -->
              <div class="curriculum-box">
                <div class="curriculum-head">
                  <span class="curriculum-title">Modulhandbuch</span>
                  <span v-if="curriculumStatus && curriculumStatus.modules > 0" class="curriculum-count">
                    {{ curriculumStatus.modules }} Module · {{ curriculumStatus.with_prerequisites }} mit Vorgängern
                  </span>
                </div>
                <div class="curriculum-row">
                  <label class="cv-upload-label" @click.stop>
                    <UiIcon name="clip" fallback="📎" />
                    {{ (curriculumUploading || (curriculumStatus && curriculumStatus.processing)) ? 'Wird analysiert…' : ((curriculumStatus && curriculumStatus.modules > 0) ? 'Modulhandbuch ersetzen' : 'Modulhandbuch hochladen') }}
                    <input type="file" accept=".pdf" @change="uploadCurriculum" hidden />
                  </label>
                  <button v-if="curriculumStatus && curriculumStatus.modules > 0" @click.stop="deleteCurriculum" class="cv-delete-btn" title="Modulhandbuch entfernen">✕</button>
                </div>
                <p class="curriculum-hint">
                  <template v-if="curriculumStatus && curriculumStatus.processing">Die KI extrahiert die Module + Vorgänger-Beziehungen — das dauert einen Moment.</template>
                  <template v-else-if="curriculumStatus && curriculumStatus.modules > 0">Die Wissenslücken-Analyse empfiehlt jetzt bei schwachen Modulen gezielt die Vorgängermodule zum Wiederholen.</template>
                  <template v-else>Lade das Modulhandbuch deines Studiengangs hoch — dann erkennt die Wissenslücken-Analyse, welche Vorgängermodule du wiederholen solltest.</template>
                </p>
              </div>

              <div v-if="profileLoading" class="tutor-empty">Lade Profil…</div>
              <template v-else-if="profileData && profileData.topics.length > 0">
                <div class="profil-overall">
                  <div class="profil-overall-ring" :style="{ '--p': profileData.overall_score }">
                    <span class="profil-overall-val">{{ profileData.overall_score }}</span>
                  </div>
                  <div class="profil-overall-meta">
                    <span class="profil-overall-label">Gesamt-Beherrschung</span>
                    <span class="profil-overall-sub">{{ profileData.total_answered }} beantwortete Fragen</span>
                  </div>
                </div>

                <p class="profil-heading">Themen</p>
                <div v-for="t in profileData.topics" :key="t.topic" class="profil-topic">
                  <div class="profil-topic-head">
                    <span class="profil-topic-name">{{ t.topic }}</span>
                    <span :class="['profil-topic-score', 'plevel-' + t.level]">{{ t.score }}/100</span>
                  </div>
                  <div class="profil-bar">
                    <div :class="['profil-bar-fill', 'plevel-' + t.level]" :style="{ width: t.score + '%' }"></div>
                  </div>
                  <span class="profil-topic-sub">{{ t.correct }}/{{ t.total }} richtig · {{ t.attempts }} Quiz(ze)</span>
                </div>

                <button
                  v-if="profileData.weak_topics.length > 0"
                  @click.stop="generateWeaknessQuiz"
                  :disabled="tutorGenerating"
                  class="profil-weakness-btn"
                >
                  <UiIcon name="target" fallback="🎯" />
                  {{ tutorGenerating ? 'Wird erstellt…' : 'Schwächen-Quiz starten' }}
                </button>
              </template>
              <div v-else class="tutor-empty">
                Noch kein Lernprofil. Mach ein paar Quizze im Quiz-Tab — danach siehst du
                hier pro Thema deinen Beherrschungs-Score (0–100).
              </div>

              <div class="profil-reset">
                <button @click.stop="resetProfile" :disabled="profileResetting" class="profil-reset-btn">
                  {{ profileResetting ? 'Wird zurückgesetzt…' : 'Profil vollständig zurücksetzen' }}
                </button>
                <p class="profil-reset-hint">
                  Löscht alle gespeicherten Daten: Quizze &amp; Ergebnisse, hochgeladene Dokumente,
                  Lebenslauf, Modulhandbuch, eigene Termine und Chats. Noten &amp; Stundenplan
                  (LSF) bleiben und lassen sich neu synchronisieren.
                </p>
              </div>
            </div>

            <div v-if="item.id === 'noten'" class="noten-section">
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
              <div v-else class="noten-empty">
                Keine Noten. Klicke oben auf „LSF synchronisieren".
              </div>
            </div>

            <div v-if="item.id === 'pruefungen'" class="pruefungen-section">
              <div v-if="upcomingExams.length === 0" class="pruefungen-empty">
                Keine Prüfungen.<br>
                <span class="pruefungen-hint">Klicke oben auf „LSF synchronisieren".</span>
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
              <!-- LERNPLAN-GENERATOR -->
              <button @click.stop="generateStudyPlan" :disabled="studyPlanLoading" class="planner-plan-btn">
                <UiIcon name="calendar-2" fallback="🗓" cls="planner-plan-icon" />
                {{ studyPlanLoading ? 'Erstelle Lernplan…' : 'Lernplan für 7 Tage erstellen' }}
              </button>
              <div v-if="studyPlan" class="planner-plan-result">
                <div class="planner-plan-head">
                  <span class="planner-plan-title">Dein Lernplan</span>
                  <span v-if="studyPlanDate" class="planner-plan-date">{{ formatPlanDate(studyPlanDate) }}</span>
                  <button @click.stop="clearStudyPlan" class="planner-plan-close" title="Lernplan verwerfen">✕</button>
                </div>
                <div class="planner-plan-text markdown" v-html="renderMarkdown(studyPlan)"></div>
              </div>

              <p class="planner-deadlines-label">Anstehende Deadlines</p>
              <div v-if="plannerEvents.length === 0" class="planner-empty">
                Keine Deadlines. Klicke oben auf „LSF synchronisieren".
              </div>
              <div v-else class="planner-list">
                <div v-for="event in plannerEvents" :key="event.id" class="planner-card">
                  <div class="planner-card-header">
                    <span class="planner-card-title">{{ event.title }}</span>
                  </div>
                  <div class="planner-card-meta">
                    <span class="planner-course">{{ event.course_name }}</span>
                    <span :class="['planner-type-badge', 'ptype-' + event.type.toLowerCase()]">{{ plannerTypeLabel(event.type) }}</span>
                  </div>
                  <div class="planner-card-footer">
                    <span class="planner-date"><UiIcon name="calendar-2" fallback="📅" /> {{ formatPlannerDate(event.date) }}</span>
                    <span class="planner-days">{{ event.days_remaining }} Tage verbleibend</span>
                    <span :class="['planner-priority', 'pprio-' + event.priority.toLowerCase()]">{{ priorityLabel(event.priority) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- TUTOR / QUIZ -->
            <div v-if="item.id === 'quiz'" class="tutor-section" @click.stop>

              <!-- SETUP VIEW -->
              <div v-if="tutorView === 'setup'">
                <div class="tutor-doc-list">
                  <div class="tutor-doc-head">
                    <p class="tutor-label">Dokumente auswählen</p>
                    <label class="tutor-upload-label" @click.stop>
                      <UiIcon name="clip" fallback="📎" />
                      {{ quizUploading ? 'Lädt…' : 'PDF hochladen' }}
                      <input type="file" accept=".pdf" @change="uploadQuizFile" :disabled="quizUploading" hidden />
                    </label>
                  </div>
                  <div v-if="tutorDocuments.length === 0" class="tutor-empty">
                    Noch keine Dokumente. Lade hier ein PDF hoch, um daraus ein Quiz zu erstellen.
                  </div>
                  <label v-for="doc in tutorDocuments" :key="doc" class="tutor-doc-item" @click.stop>
                    <input type="checkbox" :value="doc" v-model="tutorSelectedDocs" @click.stop @change="onDocSelectionChange" />
                    <span class="tutor-doc-name">{{ truncateName(doc, 32) }}</span>
                  </label>
                  <p v-if="quizUploadStatus" :class="['tutor-status', quizUploadStatus.type]">{{ quizUploadStatus.message }}</p>
                </div>
                <div class="tutor-config">
                  <div class="tutor-slider-row">
                    <span class="tutor-label">Anzahl Fragen</span>
                    <span class="tutor-slider-val">{{ tutorNumQuestions }}</span>
                  </div>
                  <input type="range" min="5" max="20" v-model.number="tutorNumQuestions" class="tutor-slider" @click.stop />
                  <input v-model="tutorCourseName" placeholder="Modul / Kursname (optional)" class="tutor-input" @click.stop @input="moduleSuggested = false" />
                  <p v-if="moduleSuggested" class="tutor-module-hint">Modul automatisch aus dem Modulhandbuch erkannt — anpassbar.</p>
                </div>
                <div class="tutor-action-row">
                  <button @click.stop="generateTutorQuiz" :disabled="tutorGenerating || tutorSelectedDocs.length === 0" class="tutor-generate-btn">
                    {{ tutorGenerating ? '⏳ Wird generiert...' : '✦ Quiz generieren' }}
                  </button>
                  <button @click.stop="fetchTutorStats" class="tutor-stats-btn"><UiIcon name="stats" fallback="📊" /> Statistiken</button>
                </div>
                <button @click.stop="generateWeaknessQuiz" :disabled="tutorGenerating" class="tutor-weakness-btn">
                  <UiIcon name="target" fallback="🎯" /> {{ tutorGenerating ? 'Wird generiert...' : 'Schwächen-Quiz (aus meinem Profil)' }}
                </button>
                <p v-if="tutorStatus" :class="['tutor-status', tutorStatus.type]">{{ tutorStatus.message }}</p>
              </div>

              <!-- STATS VIEW -->
              <div v-if="tutorView === 'stats'">
                <div class="tutor-view-header">
                  <button @click.stop="tutorView = 'setup'" class="tutor-back-btn">← Zurück</button>
                  <span class="tutor-view-title">Meine Statistiken</span>
                  <button
                    v-if="tutorStats && tutorStats.total_attempts > 0"
                    @click.stop="resetStats"
                    :disabled="tutorStatsResetting"
                    class="tutor-reset-btn"
                    title="Alle Quiz-Statistiken löschen"
                  >{{ tutorStatsResetting ? '…' : 'Zurücksetzen' }}</button>
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

                  <!-- EVALUATOR AGENT: KI-Wissenslücken-Analyse -->
                  <div class="evaluator-block">
                    <button
                      v-if="!evaluatorAnalysis && !evaluatorLoading"
                      @click.stop="fetchKnowledgeGaps"
                      :disabled="tutorStats.total_attempts === 0"
                      class="evaluator-btn"
                    >
                      <UiIcon name="brain" fallback="🧠" /> KI-Wissenslücken-Analyse
                    </button>
                    <div v-if="evaluatorLoading" class="tutor-empty">
                      Der Evaluator-Agent analysiert deinen Lernfortschritt…
                    </div>
                    <div v-if="evaluatorAnalysis" class="evaluator-result">
                      <div class="evaluator-result-header">
                        <span class="evaluator-result-title"><UiIcon name="brain" fallback="🧠" /> Wissenslücken-Analyse</span>
                        <button @click.stop="evaluatorAnalysis = ''" class="evaluator-refresh">↻ Neu</button>
                      </div>
                      <div class="evaluator-text">{{ evaluatorAnalysis }}</div>
                    </div>
                  </div>
                  <div v-if="tutorStats.weak_questions.length > 0" class="tutor-stats-block">
                    <p class="tutor-stats-heading"><UiIcon name="trend-down" fallback="📉" /> Verbesserungspotenzial</p>
                    <div v-for="q in tutorStats.weak_questions" :key="q.question_id" class="tutor-stats-item tutor-stats-weak">
                      <span class="tutor-stats-rate">{{ q.success_rate }}%</span>
                      <span class="tutor-stats-text">{{ q.question_text }}</span>
                    </div>
                  </div>
                  <div v-if="tutorStats.strong_questions.length > 0" class="tutor-stats-block">
                    <p class="tutor-stats-heading"><UiIcon name="trend-up" fallback="📈" /> Du kannst das gut</p>
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
                      v-for="(opt, oi) in currentQuestion.options" :key="oi"
                      :class="['tutor-option', { 'tutor-option--selected': tutorAnswers[currentQuestion.id] === optionLetter(oi) }]"
                      @click.stop="selectAnswer(currentQuestion.id, optionLetter(oi))"
                    >
                      <span class="tutor-opt-key">{{ optionLetter(oi) }}</span>
                      <span class="tutor-opt-text">{{ optionLabel(opt) }}</span>
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
                    <template v-if="tutorSubmitting">⏳</template>
                    <template v-else><UiIcon name="check" fallback="✓" /> Auswerten</template>
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
                      <span :class="['tutor-result-icon', ans.is_correct ? 'result-ok' : 'result-bad']">
                        <UiIcon :name="ans.is_correct ? 'check' : 'cross'" :fallback="ans.is_correct ? '✓' : '✗'" cls="tutor-result-icon-img" />
                      </span>
                      <span class="tutor-result-q">{{ questionTextById(ans.question_id) }}</span>
                    </div>
                    <div v-if="!ans.is_correct" class="tutor-result-answer">
                      Deine Antwort: <strong>{{ ans.given_answer }}</strong> · Richtig: <strong>{{ ans.correct_answer }}</strong>
                    </div>
                    <div v-if="ans.explanation" class="tutor-result-explanation"><UiIcon name="lightbulb" fallback="💡" /> {{ ans.explanation }}</div>
                  </div>
                </div>

                <!-- NACHBESPRECHUNG bei < 90 % -->
                <div v-if="tutorResults.percentage < 90" class="quiz-review">
                  <div v-if="tutorQuiz && tutorQuiz.source_documents && tutorQuiz.source_documents.length" class="quiz-review-material">
                    <p class="quiz-review-material-label"><UiIcon name="book" fallback="📚" /> Empfohlenes Material zum Wiederholen</p>
                    <div v-for="d in tutorQuiz.source_documents" :key="d" class="quiz-review-doc" :title="'Öffnen: ' + d" @click.stop="openDocument(d)">
                      <UiIcon name="clip" fallback="📎" /> <span>{{ truncateName(d, 30) }}</span>
                      <span class="quiz-review-doc-open">ansehen</span>
                    </div>
                    <p v-if="tutorQuiz.course_name" class="quiz-review-module">Modul: {{ tutorQuiz.course_name }}</p>
                  </div>

                  <button
                    v-if="!quizReview"
                    @click.stop="reviewQuiz"
                    :disabled="quizReviewLoading"
                    class="quiz-review-btn"
                  >
                    {{ quizReviewLoading ? 'Tutor bereitet die Nachbesprechung vor …' : 'Ergebnisse mit dem Tutor durchgehen' }}
                  </button>

                  <div v-if="quizReview" class="quiz-review-text markdown" v-html="renderMarkdown(quizReview)"></div>
                </div>

                <button @click.stop="resetTutorQuiz" class="tutor-restart-btn">Neues Quiz starten</button>
              </div>

            </div>

          </div>
        </div>
      </div>
      <p class="sidebar-section-label">Chats</p>
      <div class="chat-list">
        <div
          v-for="c in chats"
          :key="c.id"
          @click.stop="switchChat(c.id)"
          :class="['chat-list-item', { active: c.id === chatId }]"
          :title="c.title"
        >
          <span class="chat-list-title">{{ c.title }}</span>
          <span class="chat-list-del" @click.stop="deleteChat(c.id)" title="Chat löschen">✕</span>
        </div>
      </div>

      <div v-if="tutorDocuments.length > 0" class="chat-docs">
        <p class="chat-docs-label">Hochgeladene Dokumente</p>
        <div v-for="d in tutorDocuments" :key="d" class="chat-doc-item chat-doc-item--clickable" :title="'Öffnen: ' + d" @click.stop="openDocument(d)">
          <UiIcon name="clip" fallback="📎" /> <span>{{ truncateName(d, 22) }}</span>
        </div>
      </div>
    </aside>

    <!-- HAUPTSPALTE: Chat + Eingabe -->
    <div class="main-col">
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
              <span class="welcome-card-icon"><UiIcon name="journal-alt" fallback="📋" cls="welcome-icon-img" /></span>
              <div>
                <div class="welcome-card-title">Planner-bewusst</div>
                <div class="welcome-card-desc">Nutzt Prüfungen, Abgaben und Präsentationen.</div>
              </div>
            </div>
            <div class="welcome-card">
              <span class="welcome-card-icon"><UiIcon name="calendar-2" fallback="📆" cls="welcome-icon-img" /></span>
              <div>
                <div class="welcome-card-title">Kalender-bewusst</div>
                <div class="welcome-card-desc">Nutzt bevorstehende Kurse und Termine.</div>
              </div>
            </div>
            <div class="welcome-card">
              <span class="welcome-card-icon"><UiIcon name="web-test" fallback="🧠" cls="welcome-icon-img" /></span>
              <div>
                <div class="welcome-card-title">KI-Lernberater</div>
                <div class="welcome-card-desc">Gibt personalisierte Lernempfehlungen.</div>
              </div>
            </div>
            <div
              :class="['welcome-card', 'welcome-card--next-class', { 'welcome-card--clickable': nextClass }]"
              @click="nextClass && togglePanel('kalender')"
            >
              <span class="welcome-card-icon"><UiIcon name="university" fallback="🏫" cls="welcome-icon-img" /></span>
              <div class="next-class-body">
                <div class="welcome-card-title">Nächster Kurs</div>
                <template v-if="nextClass">
                  <div class="next-class-course" :title="nextClass.title">{{ extractCourseName(nextClass.title) }}</div>
                  <div class="next-class-meta"><UiIcon name="calendar-2" fallback="📅" /> {{ nextClassRelativeDate(nextClass.start_time) }}</div>
                  <div class="next-class-meta"><UiIcon name="clock" fallback="🕐" /> {{ formatTime(nextClass.start_time) }} – {{ formatTime(nextClass.end_time) }}</div>
                  <div v-if="nextClass.location" class="next-class-meta"><UiIcon name="location" fallback="📍" /> {{ extractRoom(nextClass.location) }}</div>
                </template>
                <div v-else class="next-class-meta">Keine bevorstehenden Kurse gefunden.</div>
              </div>
            </div>
          </div>
        </div>

        <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
          <div class="bubble">
            <template v-if="msg.role === 'assistant'">
              <div v-if="msg.kind === 'success'" class="bubble-success">
                <UiIcon name="check" fallback="✅" cls="bubble-success-icon" />
                <div class="bubble-text markdown" v-html="renderMarkdown(msg.content)"></div>
              </div>
              <div v-else-if="!loading || i < messages.length - 1"
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
          <span v-if="uploading">⏳</span><UiIcon v-else name="clip" fallback="📎" cls="attach-icon-img" />
          <input type="file" accept=".pdf" @change="uploadFile" :disabled="uploading" hidden />
        </label>
        <textarea
          v-model="prompt"
          :placeholder="isListening ? 'Höre zu…' : 'Frage eingeben…'"
          @keydown.enter.exact.prevent="sendPrompt"
          @input="resizeTextarea"
          ref="textarea"
          rows="1"
        ></textarea>
        <select
          v-if="speechSupported"
          v-model="speechLang"
          class="lang-select"
          title="Sprache der Spracherkennung"
          :disabled="isListening"
          @change="saveSpeechLang"
        >
          <option v-for="opt in speechLangOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <button
          v-if="speechSupported"
          @click="toggleVoiceInput"
          :class="['mic-btn', { 'mic-btn--listening': isListening }]"
          :title="isListening ? 'Aufnahme stoppen' : 'Frage sprechen'"
          type="button"
        >
          <span v-if="isListening" class="mic-pulse"></span>
          <UiIcon name="microphone" fallback="🎤" />
        </button>
        <button @click="sendPrompt" :disabled="loading || !prompt.trim()" class="send-btn">
          ↑
        </button>
      </div>
      <p v-if="speechError" class="upload-status upload-status--error">{{ speechError }}</p>
      <p v-else-if="uploadStatus" class="upload-status">{{ uploadStatus }}</p>
    </div>
    </div><!-- /main-col -->

    <!-- PDF-POPUP -->
    <div v-if="pdfViewer" class="pdf-modal-overlay" @click.self="closePdfViewer">
      <div class="pdf-modal">
        <div class="pdf-modal-header">
          <span class="pdf-modal-title" :title="pdfViewer.name"><UiIcon name="clip" fallback="📄" /> {{ pdfViewer.name }}</span>
          <div class="pdf-modal-actions">
            <a :href="pdfViewer.url" target="_blank" rel="noopener" class="pdf-modal-link" title="In neuem Tab öffnen">↗</a>
            <button class="pdf-modal-close" @click.stop="closePdfViewer" title="Schließen">✕</button>
          </div>
        </div>
        <iframe :src="pdfViewer.url" class="pdf-modal-frame" title="PDF-Vorschau"></iframe>
      </div>
    </div>

  </div>
</template>

<script>
import { marked } from 'marked'
import { h } from 'vue'

// Alle PNG-Icons aus assets automatisch laden (eager). Fehlt eine Datei, fällt
// <UiIcon> auf das Emoji zurück — der Build bricht also nie, und sobald eine
// passend benannte Datei in src/assets/ liegt, erscheint sie automatisch.
const _iconModules = import.meta.glob('./assets/*.png', { eager: true, import: 'default' })
const ICONS = {}
for (const p in _iconModules) {
  ICONS[p.split('/').pop().replace(/\.png$/, '')] = _iconModules[p]
}

// Wiederverwendbares Icon mit Emoji-Fallback.
const UiIcon = {
  name: 'UiIcon',
  props: {
    name: { type: String, required: true },
    fallback: { type: String, default: '' },
    cls: { type: String, default: 'ui-icon' },
  },
  render() {
    const src = ICONS[this.name]
    const cls = this.cls === 'ui-icon' ? 'ui-icon' : 'ui-icon ' + this.cls
    return src
      ? h('img', { src, class: cls, alt: '' })
      : h('span', { class: 'ui-icon-emoji' }, this.fallback)
  },
}

marked.use({ breaks: true })

export default {
  components: { UiIcon },
  data() {
    return {
      chatId: '',
      chats: [],
      prompt: '',
      messages: [],
      loading: false,
      currentTime: new Date(),
      quickSuggestions: [
        'Worauf sollte ich mich diese Woche konzentrieren?',
        'Erstelle einen Lernplan basierend auf meinem Kalender.',
        'Welche Kurse habe ich diese Woche?',
        'Ich habe heute nur 3 Stunden Zeit.',
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
      lsfSyncing: false,
      lsfSyncStatus: null,
      careerAnalysis: null,
      careerLoading: false,
      careerError: null,
      careerBarsAnimated: false,
      isDark: false,
      calendarEvents: [],
      calendarSearch: '',
      calendarShowAll: false,
      calView: 'month',
      calRefDate: new Date(),
      calShowAddForm: false,
      userEventForm: { title: '', date: '', start: '', end: '', location: '' },
      userEventSaving: false,
      userEventStatus: null,
      studyPlan: '',
      studyPlanDate: '',
      studyPlanLoading: false,
      calWeekdayLabels: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
      calMonthNames: ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'],
      gradesData: null,
      plannerEvents: [],
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
      quizReview: '',
      quizReviewLoading: false,
      pdfViewer: null,   // { name, url } — angezeigtes Dokument im Popup
      tutorStats: null,
      tutorStatsLoading: false,
      evaluatorAnalysis: '',
      evaluatorLoading: false,
      tutorStatsResetting: false,
      quizUploading: false,
      quizUploadStatus: null,
      moduleSuggested: false,
      profileData: null,
      profileLoading: false,
      curriculumStatus: null,
      curriculumUploading: false,
      profileResetting: false,
      cvStatus: null,
      cvUploading: false,
      navItems: [
        {
          id: 'pruefungen',
          label: 'Prüfungen',
          icon: '📅',
          iconName: 'reminder-appointment',
          entries: []
        },
        {
          id: 'quiz',
          label: 'Quiz',
          icon: '🧠',
          iconName: 'web-test',
          entries: []
        },
        {
          id: 'profil',
          label: 'Profil',
          icon: '👤',
          iconName: 'person',
          entries: []
        },
        {
          id: 'career',
          label: 'Career',
          icon: '💼',
          iconName: 'briefcase',
          entries: []
        },
        {
          id: 'kalender',
          label: 'Kalender',
          icon: '📆',
          iconName: 'calendar-2',
          entries: []
        },
        {
          id: 'noten',
          label: 'Noten',
          icon: '🎓',
          iconName: 'graduation-cap',
          entries: []
        },
        {
          id: 'planner',
          label: 'Planner',
          icon: '📋',
          iconName: 'journal-alt',
          entries: []
        }
      ]
    }
  },
  computed: {
    canStartNewChat() {
      // Erst nachdem im aktuellen Chat etwas gefragt wurde, darf ein neuer starten.
      return this.messages.some(m => m.role === 'user')
    },
    currentDateTimeStr() {
      const d = this.currentTime
      const days = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
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
    bestCareerMatch() {
      return this.careerAnalysis?.roles?.length ? this.careerAnalysis.roles[0] : null
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
    },
    // ── Kalender (Tag/Woche/Monat) ──────────────────────────────
    _calEventsByDay() {
      // Vereinheitlicht Stundenplan (lsf), eigene Termine (user) und Planner-Deadlines.
      const byDay = {}
      const push = (key, item) => { (byDay[key] = byDay[key] || []).push(item) }

      for (const e of this.calendarEvents) {
        const d = new Date(e.start_time)
        push(this._dayKey(d), {
          id: 'c' + e.id,
          rawId: e.id,
          kind: e.source === 'user' ? 'user' : 'class',
          title: e.source === 'user' ? e.title : this.parseCourseName(e.title),
          start_time: e.start_time,
          end_time: e.end_time,
          location: e.location,
          description: e.description,
          allDay: false,
        })
      }
      // Planner-Deadlines (Prüfungen/Abgaben/Präsentationen) als ganztägige Marker
      for (const ev of this.plannerEvents) {
        const d = new Date(ev.date + 'T00:00:00')
        push(this._dayKey(d), {
          id: 'p' + ev.id,
          kind: 'deadline',
          title: ev.title,
          deadlineType: ev.type,
          start_time: null,
          end_time: null,
          location: null,
          allDay: true,
        })
      }
      for (const k in byDay) {
        byDay[k].sort((a, b) =>
          (a.allDay ? 0 : 1) - (b.allDay ? 0 : 1) ||
          (new Date(a.start_time || 0) - new Date(b.start_time || 0))
        )
      }
      return byDay
    },
    calMonthGrid() {
      const ref = this.calRefDate
      const year = ref.getFullYear(), month = ref.getMonth()
      const first = new Date(year, month, 1)
      const startDow = (first.getDay() + 6) % 7        // Montag = 0
      const gridStart = new Date(year, month, 1 - startDow)
      const byDay = this._calEventsByDay
      const todayKey = this._dayKey(new Date())
      const weeks = []
      for (let w = 0; w < 6; w++) {
        const week = []
        for (let d = 0; d < 7; d++) {
          const date = new Date(gridStart)
          date.setDate(gridStart.getDate() + w * 7 + d)
          const key = this._dayKey(date)
          week.push({ key, date, inMonth: date.getMonth() === month, isToday: key === todayKey, events: byDay[key] || [] })
        }
        weeks.push(week)
      }
      // letzte voll-außerhalb-liegende Woche weglassen
      while (weeks.length > 4 && weeks[weeks.length - 1].every(d => !d.inMonth)) weeks.pop()
      return weeks
    },
    calWeekDays() {
      const ref = this.calRefDate
      const dow = (ref.getDay() + 6) % 7
      const monday = new Date(ref)
      monday.setDate(ref.getDate() - dow)
      const byDay = this._calEventsByDay
      const todayKey = this._dayKey(new Date())
      const days = []
      for (let i = 0; i < 7; i++) {
        const date = new Date(monday)
        date.setDate(monday.getDate() + i)
        const key = this._dayKey(date)
        days.push({ key, date, isToday: key === todayKey, events: byDay[key] || [] })
      }
      return days
    },
    calDayEvents() {
      return this._calEventsByDay[this._dayKey(this.calRefDate)] || []
    },
    calPeriodLabel() {
      const ref = this.calRefDate
      if (this.calView === 'month') return `${this.calMonthNames[ref.getMonth()]} ${ref.getFullYear()}`
      if (this.calView === 'week') {
        const days = this.calWeekDays
        const a = days[0].date, b = days[6].date
        const f = d => `${d.getDate()}.${d.getMonth() + 1}.`
        return `${f(a)} – ${f(b)}${b.getFullYear()}`
      }
      const wd = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
      return `${wd[ref.getDay()]}, ${ref.getDate()}. ${this.calMonthNames[ref.getMonth()]} ${ref.getFullYear()}`
    }
  },
  mounted() {
    this.isDark = localStorage.getItem('darkMode') === 'true'
    this.studyPlan = localStorage.getItem('studyPlan') || ''
    this.studyPlanDate = localStorage.getItem('studyPlanDate') || ''
    this.initChatId()
    this.fetchCalendarEvents()
    this.fetchPlannerEvents()
    this.fetchTutorDocuments()
    this.fetchGrades()
    this.fetchCareerAnalysis()
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
    if (this._recognition) this._recognition.abort()
  },
  methods: {
    toggleDark() {
      this.isDark = !this.isDark
      localStorage.setItem('darkMode', this.isDark)
    },
    togglePanel(id) {
      this.activePanel = this.activePanel === id ? null : id
      if (this.activePanel === 'profil') { this.fetchProfile(); this.fetchCurriculumStatus() }
      if (this.activePanel === 'career' && this.cvStatus === null) this.fetchCvStatus()
    },
    closePanel() {
      this.activePanel = null
    },
    _genChatId() {
      return (crypto.randomUUID && crypto.randomUUID()) || ('chat-' + Date.now() + '-' + Math.random().toString(16).slice(2))
    },
    persistChats() {
      localStorage.setItem('chats', JSON.stringify(this.chats))
    },
    loadMessages() {
      try {
        this.messages = JSON.parse(localStorage.getItem('chat:' + this.chatId + ':messages') || '[]')
      } catch { this.messages = [] }
    },
    saveMessages() {
      try {
        localStorage.setItem('chat:' + this.chatId + ':messages', JSON.stringify(this.messages))
      } catch { /* localStorage voll — ignorieren */ }
    },
    async maybeNameChat(text) {
      // Benennt den Chat nur beim ERSTEN Beitrag. Setzt sofort einen provisorischen
      // Titel (gekürzte Frage) und ersetzt ihn dann durch einen KI-Themen-Titel.
      const c = this.chats.find(c => c.id === this.chatId)
      if (!c || (c.title && c.title !== 'Neuer Chat')) return
      c.title = (text || '').trim().slice(0, 40) || 'Neuer Chat'
      this.persistChats()
      try {
        const res = await fetch('/api/chat/title', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: text })
        })
        if (res.ok) {
          const data = await res.json()
          const t = (data.title || '').trim()
          if (t) { c.title = t.slice(0, 60); this.persistChats() }
        }
      } catch { /* provisorischer Titel bleibt bestehen */ }
    },
    truncateName(name, max = 24) {
      if (!name) return ''
      if (name.length <= max) return name
      const dot = name.lastIndexOf('.')
      const ext = dot > 0 ? name.slice(dot) : ''
      const base = dot > 0 ? name.slice(0, dot) : name
      const keep = Math.max(4, max - ext.length - 1)
      return base.slice(0, keep) + '…' + ext
    },
    initChatId() {
      // Persistente Chat-Liste laden; aktiven Chat bestimmen/erstellen.
      try { this.chats = JSON.parse(localStorage.getItem('chats') || '[]') } catch { this.chats = [] }
      let id = localStorage.getItem('chatId')
      if (!id || !this.chats.find(c => c.id === id)) {
        if (this.chats.length > 0) {
          id = this.chats[0].id
        } else {
          id = this._genChatId()
          this.chats.unshift({ id, title: 'Neuer Chat', createdAt: Date.now() })
        }
      }
      this.chatId = id
      localStorage.setItem('chatId', id)
      this.persistChats()
      this.loadMessages()
    },
    newChat() {
      // Erst einen neuen Chat zulassen, wenn im aktuellen schon etwas gefragt wurde.
      if (!this.canStartNewChat) return
      this._createChat()
    },
    _createChat() {
      // Startet einen frischen Chat: neue chat_id, eigener Verlauf + Dokumente.
      const id = this._genChatId()
      this.chats.unshift({ id, title: 'Neuer Chat', createdAt: Date.now() })
      this.persistChats()
      this.chatId = id
      localStorage.setItem('chatId', id)
      this.messages = []
      this.saveMessages()
      this.tutorDocuments = []
      this.tutorSelectedDocs = []
      this.uploadStatus = ''
      this.activePanel = null
      this.fetchTutorDocuments()
    },
    switchChat(id) {
      this.activePanel = null
      if (id === this.chatId) return
      this.saveMessages()              // aktuellen Chat sichern
      this.chatId = id
      localStorage.setItem('chatId', id)
      this.loadMessages()
      this.tutorSelectedDocs = []
      this.uploadStatus = ''
      this.fetchTutorDocuments()
    },
    deleteChat(id) {
      this.chats = this.chats.filter(c => c.id !== id)
      localStorage.removeItem('chat:' + id + ':messages')
      this.persistChats()
      if (id === this.chatId) {
        if (this.chats.length === 0) {
          this._createChat()
        } else {
          this.chatId = this.chats[0].id
          localStorage.setItem('chatId', this.chatId)
          this.loadMessages()
          this.fetchTutorDocuments()
        }
      }
    },
    async syncLsf() {
      // Lädt Noten, Termine, Prüfungen und Kalender frisch aus dem LSF-Mock in die DB
      // und aktualisiert anschließend alle Ansichten.
      this.lsfSyncing = true
      this.lsfSyncStatus = null
      try {
        const res = await fetch('/api/lsf/sync', { method: 'POST' })
        if (!res.ok) throw new Error('sync failed')
        const data = await res.json()
        await Promise.all([
          this.fetchCalendarEvents(),
          this.fetchPlannerEvents(),
          this.fetchGrades(),
          this.fetchCareerAnalysis(),
        ])
        this.lsfSyncStatus = {
          type: 'success',
          message: `✓ ${data.grades} Noten, ${data.calendar_events} Termine, ${data.exams} Prüfungen`,
        }
      } catch {
        this.lsfSyncStatus = { type: 'error', message: 'LSF-Sync fehlgeschlagen.' }
      } finally {
        this.lsfSyncing = false
      }
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
      this.maybeNameChat(userPrompt)

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
              'Der Lernberater konnte deine Anfrage nicht verarbeiten. Bitte versuche es erneut.'
          }
        } catch {
          this.messages[this.messages.length - 1].content = 'Fehler: Backend nicht erreichbar.'
        } finally {
          this.loading = false
          this.saveMessages()
        }
        return
      }
      // --- END STUDY ADVISOR routing ---

      // Existing streaming chat for all non-planner questions
      try {
        const res = await fetch('/api/prompt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: userPrompt, chat_id: this.chatId })
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
        this.saveMessages()
      }
    },
    _dayKey(d) {
      return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
    },
    calToday() {
      this.calRefDate = new Date()
    },
    calSelectDay(date) {
      this.calRefDate = new Date(date)
      this.calView = 'day'
    },
    calPrev() { this._calShift(-1) },
    calNext() { this._calShift(1) },
    _calShift(dir) {
      const d = new Date(this.calRefDate)
      if (this.calView === 'month') d.setMonth(d.getMonth() + dir)
      else if (this.calView === 'week') d.setDate(d.getDate() + 7 * dir)
      else d.setDate(d.getDate() + dir)
      this.calRefDate = d
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
    async addUserEvent() {
      const f = this.userEventForm
      if (!f.title || !f.date || !f.start || !f.end) return
      this.userEventSaving = true
      this.userEventStatus = null
      // Datum + Uhrzeit zu ISO (lokale Zeit) zusammensetzen
      const toIso = (d, t) => new Date(`${d}T${t}:00`).toISOString()
      try {
        const res = await fetch('/api/calendar/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: f.title,
            start_time: toIso(f.date, f.start),
            end_time: toIso(f.date, f.end),
            location: f.location || null,
          })
        })
        if (res.ok) {
          await this.fetchCalendarEvents()
          this.calShowAddForm = false
          this.userEventForm = { title: '', date: '', start: '', end: '', location: '' }
        } else {
          const data = await res.json().catch(() => ({}))
          this.userEventStatus = { type: 'error', message: data.detail || 'Termin konnte nicht gespeichert werden.' }
        }
      } catch {
        this.userEventStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.userEventSaving = false
      }
    },
    async deleteUserEvent(id) {
      if (!confirm('Diesen Termin löschen?')) return
      try {
        const res = await fetch('/api/calendar/events/' + id, { method: 'DELETE' })
        if (res.ok) await this.fetchCalendarEvents()
      } catch { /* silent */ }
    },
    async generateStudyPlan() {
      this.studyPlanLoading = true
      this.studyPlan = ''
      try {
        const res = await fetch('/api/planner/study-plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ horizon_days: 7 })
        })
        if (res.ok) {
          const data = await res.json()
          this.studyPlan = data.plan || ''
          if (this.studyPlan) {
            this.studyPlanDate = new Date().toISOString()
            try {
              localStorage.setItem('studyPlan', this.studyPlan)
              localStorage.setItem('studyPlanDate', this.studyPlanDate)
            } catch { /* localStorage voll */ }
          }
        } else {
          this.studyPlan = 'Der Lernplan konnte gerade nicht erstellt werden. Bitte später erneut versuchen.'
        }
      } catch {
        this.studyPlan = 'Backend nicht erreichbar.'
      } finally {
        this.studyPlanLoading = false
      }
    },
    clearStudyPlan() {
      this.studyPlan = ''
      this.studyPlanDate = ''
      localStorage.removeItem('studyPlan')
      localStorage.removeItem('studyPlanDate')
    },
    formatPlanDate(iso) {
      try {
        return 'erstellt ' + new Date(iso).toLocaleString('de-DE', {
          day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
        }) + ' Uhr'
      } catch { return '' }
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
      if (diff === 0) return 'Heute'
      if (diff === 1) return 'Morgen'
      const days = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
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
      formData.append('chat_id', this.chatId)

      try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData })
        if (res.ok) {
          this.uploadStatus = ''
          this.fetchTutorDocuments()
          this.messages.push({
            role: 'assistant',
            kind: 'success',
            content:
              `**${this.truncateName(file.name, 40)}** wurde erfolgreich hochgeladen.\n\n` +
              `Das Dokument wird im Hintergrund verarbeitet. Du kannst in wenigen Sekunden Fragen dazu stellen.`
          })
          this.saveMessages()
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
    marketDemandStars(level) {
      const map = { 'Very High': 5, 'High': 4, 'Medium': 3, 'Low': 2 }
      const filled = map[level] || 3
      return '★'.repeat(filled) + '☆'.repeat(5 - filled)
    },
    demandLabel(level) {
      return { 'Very High': 'Sehr hoch', 'High': 'Hoch', 'Medium': 'Mittel', 'Low': 'Niedrig' }[level] || level
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
    async fetchPlannerEvents() {
      try {
        const res = await fetch('/api/planner/events')
        if (res.ok) this.plannerEvents = await res.json()
      } catch {
        // Backend nicht erreichbar beim Start — kein Fehler anzeigen
      }
    },
    plannerTypeLabel(type) {
      const map = { EXAM: 'Prüfung', ASSIGNMENT: 'Abgabe', PRESENTATION: 'Präsentation' }
      return map[type] || type
    },
    priorityLabel(prio) {
      const map = { URGENT: 'Dringend', HIGH: 'Hoch', NORMAL: 'Normal' }
      return map[(prio || '').toUpperCase()] || prio
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
    async uploadQuizFile(event) {
      // Lädt ein PDF direkt aus dem Quiz-Tab hoch (in den aktuellen Chat) — kein
      // Chatwechsel nötig. Nach dem Hochladen ist das Dokument auswählbar.
      const file = event.target.files[0]
      if (!file || this.quizUploading) return
      event.target.value = ''
      if (file.type !== 'application/pdf') {
        this.quizUploadStatus = { type: 'error', message: 'Nur PDF-Dateien erlaubt.' }
        return
      }
      this.quizUploading = true
      this.quizUploadStatus = { type: 'info', message: `„${this.truncateName(file.name, 28)}" wird hochgeladen…` }
      const formData = new FormData()
      formData.append('file', file)
      formData.append('chat_id', this.chatId)
      try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData })
        if (res.ok) {
          await this.fetchTutorDocuments()
          if (this.tutorDocuments.includes(file.name) && !this.tutorSelectedDocs.includes(file.name)) {
            this.tutorSelectedDocs.push(file.name)
          }
          this.quizUploadStatus = { type: 'success', message: 'Hochgeladen — wird im Hintergrund verarbeitet (ein paar Sekunden), dann kannst du das Quiz erstellen.' }
        } else {
          const data = await res.json().catch(() => ({}))
          this.quizUploadStatus = { type: 'error', message: data.detail || 'Fehler beim Hochladen.' }
        }
      } catch {
        this.quizUploadStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.quizUploading = false
      }
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
            chat_id: this.chatId,
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
    // Antwort-Buchstabe aus dem Options-Index (0→A, 1→B, …). Unabhängig davon,
    // ob das LLM die Option mit „A) " präfixt hat — verhindert das Mehrfach-Auswählen.
    optionLetter(i) {
      return String.fromCharCode(65 + i)
    },
    // Entfernt ein evtl. vorhandenes „A) " / „A. " / „A: " Präfix, damit der
    // Buchstabe nicht doppelt erscheint und der Text nicht abgeschnitten wird.
    optionLabel(opt) {
      return String(opt).replace(/^\s*[A-Da-d][).:．、]\s*/, '').trim()
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
          this.quizReview = ''
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
    async reviewQuiz() {
      if (!this.tutorQuiz || !this.tutorResults || this.quizReviewLoading) return
      this.quizReviewLoading = true
      try {
        const res = await fetch(`/api/tutor/quiz/${this.tutorQuiz.id}/review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ attempt_id: this.tutorResults.attempt_id })
        })
        if (res.ok) {
          const data = await res.json()
          this.quizReview = data.review || ''
        } else {
          const data = await res.json().catch(() => ({}))
          this.tutorStatus = { type: 'error', message: data.detail || 'Nachbesprechung fehlgeschlagen.' }
        }
      } catch {
        this.tutorStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.quizReviewLoading = false
      }
    },
    async fetchTutorStats() {
      this.tutorStatsLoading = true
      this.tutorView = 'stats'
      this.tutorStats = null
      this.evaluatorAnalysis = ''
      try {
        const res = await fetch('/api/tutor/stats')
        if (res.ok) this.tutorStats = await res.json()
      } catch { /* silent */ } finally {
        this.tutorStatsLoading = false
      }
    },
    async resetStats() {
      if (!confirm('Wirklich alle Quiz-Statistiken zurücksetzen? Das kann nicht rückgängig gemacht werden.')) return
      this.tutorStatsResetting = true
      try {
        const res = await fetch('/api/tutor/stats', { method: 'DELETE' })
        if (res.ok) {
          this.tutorStats = { total_attempts: 0, average_score: 0, weak_questions: [], strong_questions: [] }
          this.evaluatorAnalysis = ''
          this.profileData = null
        }
      } catch { /* silent */ } finally {
        this.tutorStatsResetting = false
      }
    },
    onDocSelectionChange() {
      if (this.tutorSelectedDocs.length === 0) return
      clearTimeout(this._moduleSuggestTimer)
      this._moduleSuggestTimer = setTimeout(() => this.suggestQuizModule(), 500)
    },
    async suggestQuizModule() {
      // Nur vorbefüllen, wenn der Nutzer noch keinen Kursnamen eingegeben hat.
      if (this.tutorSelectedDocs.length === 0 || (this.tutorCourseName || '').trim()) return
      try {
        const res = await fetch('/api/curriculum/suggest-module', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ documents: this.tutorSelectedDocs })
        })
        if (res.ok) {
          const data = await res.json()
          if (data.module && !(this.tutorCourseName || '').trim()) {
            this.tutorCourseName = data.module
            this.moduleSuggested = true
          }
        }
      } catch { /* silent */ }
    },
    async generateWeaknessQuiz() {
      if (this.tutorGenerating) return
      this.tutorGenerating = true
      this.tutorStatus = { type: 'info', message: 'Schwächen-Quiz wird aus deinem Profil erstellt…' }
      try {
        const res = await fetch('/api/tutor/quiz/weakness', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ num_questions: this.tutorNumQuestions })
        })
        if (res.ok) {
          this.tutorQuiz = await res.json()
          this.tutorAnswers = {}
          this.tutorCurrentQuestion = 0
          this.tutorStatus = null
          this.tutorView = 'quiz'
        } else {
          const data = await res.json().catch(() => ({}))
          this.tutorStatus = { type: 'error', message: data.detail || 'Schwächen-Quiz fehlgeschlagen.' }
        }
      } catch {
        this.tutorStatus = { type: 'error', message: 'Backend nicht erreichbar.' }
      } finally {
        this.tutorGenerating = false
      }
    },
    async fetchProfile() {
      this.profileLoading = true
      try {
        const res = await fetch('/api/tutor/profile')
        if (res.ok) this.profileData = await res.json()
      } catch { /* silent */ } finally {
        this.profileLoading = false
      }
    },
    async fetchCurriculumStatus() {
      try {
        const res = await fetch('/api/curriculum/status')
        if (res.ok) {
          this.curriculumStatus = await res.json()
          // Solange die Extraktion läuft, weiter pollen
          if (this.curriculumStatus.processing) {
            clearTimeout(this._curriculumPoll)
            this._curriculumPoll = setTimeout(() => this.fetchCurriculumStatus(), 3000)
          }
        }
      } catch { /* silent */ }
    },
    async uploadCurriculum(event) {
      const file = event.target.files[0]
      if (!file || this.curriculumUploading) return
      event.target.value = ''
      if (file.type !== 'application/pdf') return
      this.curriculumUploading = true
      const formData = new FormData()
      formData.append('file', file)
      try {
        const res = await fetch('/api/curriculum/upload', { method: 'POST', body: formData })
        if (res.ok) {
          // Hintergrund-Extraktion läuft → Status pollen
          this.curriculumStatus = { processing: true, modules: 0, with_prerequisites: 0 }
          clearTimeout(this._curriculumPoll)
          this._curriculumPoll = setTimeout(() => this.fetchCurriculumStatus(), 3000)
        }
      } catch { /* silent */ } finally {
        this.curriculumUploading = false
      }
    },
    async deleteCurriculum() {
      if (!confirm('Modulhandbuch entfernen?')) return
      try {
        const res = await fetch('/api/curriculum', { method: 'DELETE' })
        if (res.ok) this.curriculumStatus = { processing: false, modules: 0, with_prerequisites: 0 }
      } catch { /* silent */ }
    },
    async resetProfile() {
      if (!confirm('Wirklich ALLE gespeicherten Daten löschen? Quizze, Ergebnisse, Dokumente, ' +
                   'Lebenslauf, Modulhandbuch, eigene Termine und Chats werden unwiderruflich entfernt.')) return
      this.profileResetting = true
      try {
        const res = await fetch('/api/profile/reset', { method: 'POST' })
        if (!res.ok) {
          alert('Zurücksetzen fehlgeschlagen. Bitte später erneut versuchen.')
          this.profileResetting = false
          return
        }
        // localStorage leeren (Chats, Nachrichten, Lernplan, Chat-ID)
        try {
          const keys = []
          for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i)
            if (k && (k === 'chats' || k === 'chatId' || k === 'studyPlan' || k === 'studyPlanDate' || k.startsWith('chat:'))) keys.push(k)
          }
          keys.forEach(k => localStorage.removeItem(k))
        } catch { /* ignore */ }
        // Saubere Neuinitialisierung
        location.reload()
      } catch {
        alert('Backend nicht erreichbar.')
        this.profileResetting = false
      }
    },
    async fetchCvStatus() {
      try {
        const res = await fetch('/api/career/cv')
        if (res.ok) this.cvStatus = await res.json()
      } catch { /* silent */ }
    },
    async uploadCv(event) {
      const file = event.target.files[0]
      if (!file || this.cvUploading) return
      event.target.value = ''
      if (file.type !== 'application/pdf') { this.careerError = 'Nur PDF-Dateien erlaubt.'; return }
      this.cvUploading = true
      const formData = new FormData()
      formData.append('file', file)
      try {
        const res = await fetch('/api/career/cv', { method: 'POST', body: formData })
        if (res.ok) {
          this.cvStatus = await res.json()
          // Analyse mit CV neu berechnen
          this.fetchCareerAnalysis()
        } else {
          const data = await res.json().catch(() => ({}))
          this.careerError = data.detail || 'CV-Upload fehlgeschlagen.'
        }
      } catch {
        this.careerError = 'Backend nicht erreichbar.'
      } finally {
        this.cvUploading = false
      }
    },
    async deleteCv() {
      if (!confirm('Lebenslauf entfernen?')) return
      try {
        const res = await fetch('/api/career/cv', { method: 'DELETE' })
        if (res.ok) {
          this.cvStatus = { has_cv: false, filename: null }
          this.fetchCareerAnalysis()
        }
      } catch { /* silent */ }
    },
    async fetchKnowledgeGaps() {
      // Ruft den EvaluatorAgent auf, der autonom alle Quiz-Daten sammelt und
      // eine KI-Analyse der Wissenslücken erstellt.
      this.evaluatorLoading = true
      this.evaluatorAnalysis = ''
      try {
        const res = await fetch('/api/ai/knowledge-gaps')
        if (res.ok) {
          const data = await res.json()
          this.evaluatorAnalysis = data.analysis || 'Keine Analyse verfügbar.'
        } else {
          this.evaluatorAnalysis = 'Die Analyse ist momentan nicht verfügbar. Bitte später erneut versuchen.'
        }
      } catch {
        this.evaluatorAnalysis = 'Backend nicht erreichbar.'
      } finally {
        this.evaluatorLoading = false
      }
    },
    questionTextById(questionId) {
      if (!this.tutorQuiz) return ''
      const q = this.tutorQuiz.questions.find(q => q.id === questionId)
      return q ? q.question_text : ''
    },
    openDocument(name, url = null) {
      // Zeigt eine PDF im App-Popup. url optional (z.B. später für Moodle-Dokumente);
      // sonst wird die lokal hochgeladene Datei ausgeliefert.
      if (!name) return
      this.pdfViewer = {
        name,
        url: url || ('/api/documents/file?name=' + encodeURIComponent(name)),
      }
    },
    closePdfViewer() {
      this.pdfViewer = null
    },
    resetTutorQuiz() {
      this.tutorView = 'setup'
      this.tutorQuiz = null
      this.tutorResults = null
      this.quizReview = ''
      this.quizReviewLoading = false
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
  flex-direction: row;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  transition: background 0.2s, color 0.2s;
}

/* SIDEBAR */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 7px;
  width: 240px;
  flex-shrink: 0;
  padding: 14px 12px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: 100;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}

.nav-logo {
  font-weight: 700;
  font-size: 17px;
  color: var(--primary);
  white-space: nowrap;
}

.sidebar-section-label {
  margin: 10px 4px 0;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.sidebar-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s, background 0.15s;
}
.sidebar-newchat { background: var(--primary); color: #fff; border: none; }
.sidebar-newchat:hover:not(:disabled) { background: var(--primary-hover); }
.sidebar-newchat:disabled { opacity: 0.45; cursor: not-allowed; }
.sidebar-sync { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; border: none; }
.sidebar-sync:hover:not(:disabled) { opacity: 0.9; }
.sidebar-sync:disabled { opacity: 0.55; cursor: not-allowed; }

/* back-up.png (schwarz) auf dem violetten Button → weiß einfärben */
.lsf-sync-icon {
  width: 15px;
  height: 15px;
  object-fit: contain;
  display: block;
  filter: brightness(0) invert(1);
}

.lsf-sync-status {
  font-size: 11px;
  white-space: normal;
  line-height: 1.3;
}
.lsf-sync-status.success { color: #16a34a; }
.lsf-sync-status.error { color: #dc2626; }

.nav-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item { position: static; }

.nav-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  padding: 8px 12px;
  border-radius: 7px;
  font-size: 14px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

/* CHAT-LISTE in der Sidebar */
.chat-list { display: flex; flex-direction: column; gap: 2px; }
.chat-list-item {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
  padding: 7px 10px; border-radius: 7px; cursor: pointer;
  font-size: 13px; color: var(--text-muted);
}
.chat-list-item:hover { background: var(--surface-hover); color: var(--text); }
.chat-list-item.active { background: var(--primary-dim); color: var(--primary); font-weight: 600; }
.chat-list-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.chat-list-del { opacity: 0; font-size: 12px; flex-shrink: 0; }
.chat-list-item:hover .chat-list-del { opacity: 0.6; }
.chat-list-del:hover { opacity: 1; color: #dc2626; }

.chat-docs { margin-top: 6px; padding: 8px 10px; background: var(--surface-hover); border-radius: 8px; }
.chat-docs-label { margin: 0 0 6px; font-size: 11px; font-weight: 600; color: var(--text-muted); }
.chat-doc-item {
  display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text); padding: 2px 0;
}
.chat-doc-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* HAUPTSPALTE */
.main-col { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }

/* Erfolg-Bubble (Upload) */
.bubble-success { display: flex; align-items: flex-start; gap: 8px; }
img.bubble-success-icon { width: 18px; height: 18px; flex-shrink: 0; margin-top: 2px; }

.nav-btn:hover { background: var(--surface-hover); color: var(--text); }
.nav-btn.active { background: var(--primary-dim); color: var(--primary); }

/* Eigene PNG-Icons (assets) — schwarz, daher im Dark Mode invertiert */
.nav-icon-img {
  width: 16px;
  height: 16px;
  object-fit: contain;
  display: block;
  opacity: 0.75;
  transition: opacity 0.15s, filter 0.15s;
}
.nav-btn:hover .nav-icon-img,
.nav-btn.active .nav-icon-img { opacity: 1; }
.dark .nav-icon-img { filter: invert(1) brightness(1.6); }
/* Aktives Item violett einfärben (passend zur Textfarbe) */
.nav-btn.active .nav-icon-img {
  filter: invert(36%) sepia(83%) saturate(2884%) hue-rotate(238deg) brightness(94%) contrast(92%);
}
.nav-icon-emoji { font-size: 15px; line-height: 1; }

/* Generische UiIcon-Bilder — skalieren mit der Textgröße (1em) und werden im
   Dark Mode invertiert (alle Asset-PNGs sind schwarz). Emoji-Fallback bleibt Text. */
.ui-icon {
  width: 1em;
  height: 1em;
  object-fit: contain;
  display: inline-block;
  vertical-align: -0.15em;
}
.dark .ui-icon { filter: invert(1) brightness(1.7); }
.ui-icon-emoji { display: inline-block; line-height: 1; }

/* Kontext-spezifische Größen (img.X schlägt .ui-icon per Spezifität) */
img.welcome-icon-img { width: 1em; height: 1em; }
img.theme-icon-img { width: 18px; height: 18px; vertical-align: -3px; }
img.attach-icon-img { width: 18px; height: 18px; vertical-align: -4px; }
/* Sync-Icon bleibt auf dem violetten Button immer weiß */
img.lsf-sync-icon { filter: brightness(0) invert(1); }
.dark img.lsf-sync-icon { filter: brightness(0) invert(1); }

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
  position: fixed;
  left: 252px;                       /* Sidebar-Breite (240) + 12 Abstand */
  top: 14px;
  max-height: calc(100vh - 28px);
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  min-width: 320px;
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
  max-height: 180px;
  overflow-y: auto;
  margin-bottom: 10px;
}

.tutor-doc-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tutor-upload-label {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: 7px;
  background: var(--surface); border: 1px solid var(--border);
  font-size: 12px; font-weight: 500; color: var(--text); cursor: pointer; white-space: nowrap;
}
.tutor-upload-label:hover { background: var(--surface-hover); border-color: var(--primary); color: var(--primary); }

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

/* EvaluatorAgent — KI-Wissenslücken-Analyse */
.evaluator-block { margin: 12px 0; }

.evaluator-btn {
  width: 100%;
  padding: 10px 12px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}
.evaluator-btn:hover:not(:disabled) { opacity: 0.92; }
.evaluator-btn:active:not(:disabled) { transform: scale(0.99); }
.evaluator-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.evaluator-result {
  margin-top: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  background: var(--surface-hover);
}
.evaluator-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.evaluator-result-title { font-size: 13px; font-weight: 600; color: var(--text); }
.evaluator-refresh {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 11px;
  padding: 3px 8px;
  color: var(--text-muted);
  cursor: pointer;
}
.evaluator-refresh:hover { background: var(--surface); color: var(--text); }
.evaluator-text {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

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

/* Nachbesprechung (< 90 %) */
.quiz-review {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.quiz-review-material {
  background: var(--primary-dim);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.quiz-review-material-label { font-size: 13px; font-weight: 700; color: var(--text); margin: 0 0 8px; }
.quiz-review-doc {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--text); padding: 3px 0;
}
.quiz-review-module { font-size: 12px; color: var(--text-muted); margin: 6px 0 0; }
.quiz-review-btn {
  width: 100%;
  padding: 11px 14px;
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  border-radius: 9px;
  cursor: pointer;
}
.quiz-review-btn:hover:not(:disabled) { background: var(--primary-hover); }
.quiz-review-btn:disabled { opacity: 0.6; cursor: progress; }
.quiz-review-text {
  margin-top: 12px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--text);
}
.quiz-review-doc { cursor: pointer; }
.quiz-review-doc:hover { text-decoration: underline; }
.quiz-review-doc-open {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--primary);
}
.chat-doc-item--clickable { cursor: pointer; }
.chat-doc-item--clickable:hover { color: var(--primary); text-decoration: underline; }

/* PDF-Popup */
.pdf-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}
.pdf-modal {
  width: min(900px, 92vw);
  height: min(90vh, 1000px);
  background: var(--surface);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pdf-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}
.pdf-modal-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pdf-modal-actions { display: flex; align-items: center; gap: 6px; }
.pdf-modal-link, .pdf-modal-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 15px;
  cursor: pointer;
  text-decoration: none;
}
.pdf-modal-link:hover, .pdf-modal-close:hover { background: var(--surface-hover); }
.pdf-modal-frame {
  flex: 1;
  width: 100%;
  border: none;
  background: #f3f4f6;
}

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
.tutor-result-icon { font-weight: 700; flex-shrink: 0; display: inline-flex; }
.result-correct .tutor-result-icon { color: #16a34a; }
.result-wrong   .tutor-result-icon { color: #dc2626; }
img.tutor-result-icon-img { width: 15px; height: 15px; }
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

/* ── Schwächen-Quiz + Stats-Reset ───────────────────────────────── */
.tutor-weakness-btn {
  width: 100%;
  margin-top: 8px;
  padding: 9px 12px;
  background: var(--surface);
  border: 1px solid var(--primary);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background 0.15s;
}
.tutor-weakness-btn:hover:not(:disabled) { background: var(--primary-dim); }
.tutor-weakness-btn:disabled { opacity: 0.55; cursor: default; }

.tutor-reset-btn {
  margin-left: auto;
  padding: 3px 9px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 11px;
  color: #dc2626;
  cursor: pointer;
}
.tutor-reset-btn:hover:not(:disabled) { background: #fee2e2; }
.tutor-reset-btn:disabled { opacity: 0.5; cursor: default; }

/* ── Profil-Tab ─────────────────────────────────────────────────── */
.profil-section { display: flex; flex-direction: column; gap: 10px; max-height: 60vh; overflow-y: auto; }

.profil-overall { display: flex; align-items: center; gap: 14px; padding: 4px 2px; }
.profil-overall-ring {
  --p: 0;
  position: relative;
  width: 60px; height: 60px; border-radius: 50%;
  flex-shrink: 0;
  background: conic-gradient(var(--primary) calc(var(--p) * 1%), var(--border) 0);
  display: grid; place-items: center;
}
.profil-overall-ring::before {
  content: ''; position: absolute; width: 46px; height: 46px;
  border-radius: 50%; background: var(--surface);
}
.profil-overall-val { position: relative; font-size: 17px; font-weight: 700; color: var(--text); }
.profil-overall-meta { display: flex; flex-direction: column; gap: 2px; }
.profil-overall-label { font-size: 13px; font-weight: 600; color: var(--text); }
.profil-overall-sub { font-size: 11px; color: var(--text-muted); }

.profil-heading { font-size: 12px; font-weight: 600; color: var(--text-muted); margin: 4px 0 0; }
.profil-topic { display: flex; flex-direction: column; gap: 4px; }
.profil-topic-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.profil-topic-name { font-size: 13px; color: var(--text); font-weight: 500; }
.profil-topic-score { font-size: 12px; font-weight: 700; white-space: nowrap; }
.profil-topic-sub { font-size: 11px; color: var(--text-muted); }
.profil-bar { height: 7px; border-radius: 4px; background: var(--border); overflow: hidden; }
.profil-bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s; }

.plevel-stark { color: #16a34a; }
.profil-bar-fill.plevel-stark { background: #16a34a; }
.plevel-ok { color: #d97706; }
.profil-bar-fill.plevel-ok { background: #f59e0b; }
.plevel-schwach { color: #dc2626; }
.profil-bar-fill.plevel-schwach { background: #dc2626; }

.profil-weakness-btn {
  margin-top: 6px; width: 100%;
  padding: 9px 12px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none; border-radius: 8px;
  font-size: 13px; font-weight: 600; color: #fff;
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
}
.profil-weakness-btn:hover:not(:disabled) { opacity: 0.92; }
.profil-weakness-btn:disabled { opacity: 0.55; cursor: default; }

/* ── CV-Upload (Career) ─────────────────────────────────────────── */
.cv-bar { display: flex; align-items: center; gap: 8px; margin: 8px 0 0; flex-wrap: wrap; }
.cv-upload-label {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 10px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; font-size: 12.5px; font-weight: 500;
  color: var(--text); cursor: pointer; white-space: nowrap;
}
.cv-upload-label:hover { background: var(--surface-hover); }
.cv-filename {
  font-size: 12px; color: #16a34a; max-width: 160px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cv-delete-btn {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  font-size: 11px; color: var(--text-muted); cursor: pointer; padding: 2px 7px;
}
.cv-delete-btn:hover { color: #dc2626; }
.cv-hint { font-size: 11px; color: var(--text-muted); margin: 6px 0 0; line-height: 1.4; }

/* ── Kalender (Tag/Woche/Monat) ──────────────────────────────────── */
.dropdown--calendar { width: 640px; max-width: calc(100vw - 280px); }

.cal-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.cal-views { display: inline-flex; background: var(--surface-hover); border-radius: 8px; padding: 2px; }
.cal-view-btn { border: none; background: none; padding: 5px 12px; border-radius: 6px; font-size: 12.5px; color: var(--text-muted); cursor: pointer; }
.cal-view-btn.active { background: var(--surface); color: var(--text); font-weight: 600; box-shadow: var(--shadow); }
.cal-nav { display: inline-flex; align-items: center; gap: 4px; }
.cal-nav-btn { width: 28px; height: 28px; border: 1px solid var(--border); background: var(--surface); border-radius: 6px; cursor: pointer; font-size: 16px; color: var(--text); line-height: 1; }
.cal-nav-btn:hover { background: var(--surface-hover); }
.cal-today-btn { padding: 5px 10px; border: 1px solid var(--border); background: var(--surface); border-radius: 6px; font-size: 12px; cursor: pointer; color: var(--text); }
.cal-today-btn:hover { background: var(--surface-hover); }
.cal-period { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 8px; text-align: center; }

/* Monat */
.cal-month { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.cal-weekday { font-size: 11px; font-weight: 600; color: var(--text-muted); text-align: center; padding: 2px 0; }
.cal-cell {
  min-height: 74px; border: 1px solid var(--border); border-radius: 7px; padding: 4px;
  cursor: pointer; display: flex; flex-direction: column; gap: 2px; overflow: hidden;
  background: var(--surface); transition: background 0.12s;
}
.cal-cell:hover { background: var(--surface-hover); }
.cal-cell--out { opacity: 0.4; }
.cal-cell--today { border-color: var(--primary); }
.cal-cell-num { font-size: 12px; font-weight: 600; color: var(--text); align-self: flex-end; }
.cal-cell--today .cal-cell-num { background: var(--primary); color: #fff; border-radius: 50%; width: 18px; height: 18px; display: grid; place-items: center; }
.cal-cell-events { display: flex; flex-direction: column; gap: 2px; }
.cal-chip { font-size: 10px; padding: 1px 4px; border-radius: 4px; background: var(--primary-dim); color: var(--primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cal-more { font-size: 10px; color: var(--text-muted); }

/* Woche */
.cal-week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.cal-week-col { border: 1px solid var(--border); border-radius: 7px; overflow: hidden; min-height: 120px; background: var(--surface); }
.cal-week-col--today { border-color: var(--primary); }
.cal-week-head { padding: 5px; text-align: center; cursor: pointer; background: var(--surface-hover); }
.cal-week-dow { display: block; font-size: 11px; color: var(--text-muted); }
.cal-week-date { font-size: 13px; font-weight: 600; color: var(--text); }
.cal-week-events { padding: 4px; display: flex; flex-direction: column; gap: 3px; }
.cal-week-empty { font-size: 11px; color: var(--text-muted); text-align: center; }
.cal-event { font-size: 10.5px; padding: 3px 5px; border-radius: 5px; background: var(--primary-dim); display: flex; flex-direction: column; }
.cal-event-time { font-weight: 600; color: var(--primary); }
.cal-event-name { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Tag */
.cal-day { display: flex; flex-direction: column; gap: 6px; }
.cal-day-event { display: flex; gap: 10px; border: 1px solid var(--border); border-left: 3px solid var(--primary); border-radius: 8px; padding: 8px 10px; }
.cal-day-time { display: flex; flex-direction: column; font-size: 12px; font-weight: 600; color: var(--primary); min-width: 46px; }
.cal-day-time-end { color: var(--text-muted); font-weight: 400; }
.cal-day-body { display: flex; flex-direction: column; gap: 3px; }
.cal-day-top { display: flex; align-items: center; gap: 6px; }
.cal-day-name { font-size: 13px; font-weight: 600; color: var(--text); }

/* ── Career: Datenbasis ──────────────────────────────────────────── */
.career-datasources { margin: 10px 0; padding: 10px 12px; background: var(--surface-hover); border: 1px solid var(--border); border-radius: 10px; }
.career-ds-title { margin: 0 0 8px; font-size: 12px; font-weight: 700; color: var(--text); }
.career-ds-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.career-ds-chip { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; padding: 4px 9px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); color: var(--text); }
.career-ds-chip.on { border-color: var(--primary); color: var(--primary); }
.career-ds-chip.off { opacity: 0.6; }
.career-ds-quiz { margin-top: 8px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.career-ds-quiz-label { font-size: 11px; color: var(--text-muted); }
.career-ds-quiz-tag { font-size: 11px; padding: 2px 8px; border-radius: 6px; font-weight: 600; }
.career-ds-kw { background: var(--primary-dim); color: var(--primary); }
.career-ds-quiz-tag.plevel-stark { background: #dcfce7; color: #166534; }
.career-ds-quiz-tag.plevel-ok { background: #fef9c3; color: #854d0e; }
.career-ds-quiz-tag.plevel-schwach { background: #fee2e2; color: #991b1b; }
.dark .career-ds-quiz-tag.plevel-stark { background: #14231a; color: #4ade80; }
.dark .career-ds-quiz-tag.plevel-ok { background: #2a2410; color: #fbbf24; }
.dark .career-ds-quiz-tag.plevel-schwach { background: #2d1515; color: #f87171; }
.career-ds-hint { margin: 8px 0 0; font-size: 11px; color: var(--text-muted); line-height: 1.4; }

/* ── Career: Portal-Deep-Links ───────────────────────────────────── */
.career-portals { margin: 8px 0; }
.career-portals-label { margin: 0 0 6px; font-size: 12px; color: var(--text-muted); }
.career-portals-btns { display: flex; flex-wrap: wrap; gap: 6px; }
.career-portals-btns--sm { margin-top: 8px; }
.career-portal-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 12px; border-radius: 8px;
  background: var(--primary); color: #fff; text-decoration: none;
  font-size: 12px; font-weight: 600; transition: opacity 0.15s;
}
.career-portal-btn:hover { opacity: 0.9; }
.career-portal-btn--sm { padding: 4px 9px; font-size: 11px; background: var(--surface); color: var(--primary); border: 1px solid var(--primary); }

/* ── Career: echte Stellen ───────────────────────────────────────── */
.career-jobs { margin: 12px 0; }
.career-jobs-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: var(--text); }
.career-jobs-source { font-size: 11px; font-weight: 400; color: var(--text-muted); }
.career-job-card { display: block; padding: 9px 12px; margin-bottom: 6px; border: 1px solid var(--border); border-radius: 9px; text-decoration: none; transition: border-color 0.15s, background 0.15s; }
.career-job-card:hover { border-color: var(--primary); background: var(--surface-hover); }
.career-job-top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.career-job-title { font-size: 13px; font-weight: 600; color: var(--text); }
.career-job-salary { font-size: 11.5px; font-weight: 600; color: #16a34a; white-space: nowrap; }
.career-job-meta { font-size: 11.5px; color: var(--text-muted); margin-top: 2px; display: flex; gap: 4px; flex-wrap: wrap; }
.career-job-remote { color: var(--primary); }
.career-jobs-empty { font-size: 12px; color: var(--text-muted); line-height: 1.5; margin: 8px 0; padding: 10px 12px; background: var(--surface-hover); border-radius: 9px; }

/* ── Kalender: eigene Termine + Legende + Event-Arten ────────────── */
.cal-period-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.cal-add-btn { padding: 5px 11px; border: 1px solid var(--primary); background: var(--surface); color: var(--primary); border-radius: 7px; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.cal-add-btn:hover { background: var(--primary-dim); }
.cal-add-form { display: flex; flex-direction: column; gap: 6px; padding: 10px; margin-bottom: 8px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-hover); }
.cal-add-grid { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 6px; }
.cal-add-input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 12.5px; background: var(--surface); color: var(--text); }
.cal-add-actions { display: flex; gap: 6px; }
.cal-add-save { flex: 1; padding: 7px; border: none; border-radius: 7px; background: var(--primary); color: #fff; font-weight: 600; font-size: 12.5px; cursor: pointer; }
.cal-add-save:disabled { opacity: 0.6; }
.cal-add-cancel { padding: 7px 12px; border: 1px solid var(--border); border-radius: 7px; background: var(--surface); color: var(--text-muted); font-size: 12.5px; cursor: pointer; }

.cal-legend { display: flex; gap: 12px; margin-bottom: 8px; }
.cal-legend-item { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-muted); }
.cal-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.cal-dot--class { background: #8b5cf6; }
.cal-dot--user { background: #0ea5e9; }
.cal-dot--deadline { background: #ef4444; }

/* Event-Farben je Art */
.cal-chip--class { background: var(--primary-dim); color: var(--primary); }
.cal-chip--user { background: #e0f2fe; color: #0369a1; }
.cal-chip--deadline { background: #fee2e2; color: #b91c1c; font-weight: 600; }
.dark .cal-chip--user { background: #0c2a3a; color: #7dd3fc; }
.dark .cal-chip--deadline { background: #2d1515; color: #fca5a5; }

.cal-event--class .cal-event-time { color: var(--primary); }
.cal-event--user { background: #e0f2fe; }
.cal-event--user .cal-event-time { color: #0369a1; }
.cal-event--deadline { background: #fee2e2; }
.cal-event--deadline .cal-event-time { color: #b91c1c; }
.dark .cal-event--user { background: #0c2a3a; }
.dark .cal-event--deadline { background: #2d1515; }

.cal-day-event--user { border-left-color: #0ea5e9; }
.cal-day-event--deadline { border-left-color: #ef4444; }
.cal-day-allday { font-size: 11px; color: var(--text-muted); }
.cal-badge-user { background: #e0f2fe; color: #0369a1; }
.cal-day-del { margin-top: 4px; align-self: flex-start; background: none; border: 1px solid var(--border); border-radius: 6px; font-size: 11px; padding: 3px 8px; color: #dc2626; cursor: pointer; }
.cal-day-del:hover { background: #fee2e2; }

/* ── Planner: Lernplan-Generator ─────────────────────────────────── */
.planner-plan-btn { display: inline-flex; align-items: center; justify-content: center; gap: 7px; width: 100%; padding: 10px 12px; margin-bottom: 10px; border: none; border-radius: 9px; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
.planner-plan-btn:hover:not(:disabled) { opacity: 0.92; }
.planner-plan-btn:disabled { opacity: 0.6; cursor: default; }
img.planner-plan-icon { filter: brightness(0) invert(1); width: 16px; height: 16px; }
.planner-plan-result { border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 12px; background: var(--surface-hover); }
.planner-plan-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.planner-plan-title { font-size: 13px; font-weight: 700; color: var(--text); }
.planner-plan-date { font-size: 10.5px; color: var(--text-muted); margin-left: auto; margin-right: 8px; white-space: nowrap; }
.planner-plan-close { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 13px; }
.planner-plan-text { font-size: 12.5px; line-height: 1.55; color: var(--text); }
.planner-deadlines-label { margin: 4px 0 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); }

/* ── Profil: Modulhandbuch ───────────────────────────────────────── */
.curriculum-box { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; background: var(--surface-hover); }
.curriculum-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.curriculum-title { font-size: 12px; font-weight: 700; color: var(--text); }
.curriculum-count { font-size: 11px; color: #16a34a; font-weight: 600; }
.curriculum-row { display: flex; align-items: center; gap: 8px; }
.curriculum-hint { font-size: 11px; color: var(--text-muted); line-height: 1.4; margin: 8px 0 0; }
.tutor-module-hint { font-size: 11px; color: #16a34a; margin: 4px 0 0; }

/* Profil-Reset */
.profil-reset { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); }
.profil-reset-btn { width: 100%; padding: 9px 12px; border: 1px solid #dc2626; background: var(--surface); color: #dc2626; border-radius: 8px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.profil-reset-btn:hover:not(:disabled) { background: #fee2e2; }
.profil-reset-btn:disabled { opacity: 0.55; cursor: default; }
.profil-reset-hint { font-size: 11px; color: var(--text-muted); line-height: 1.4; margin: 6px 0 0; }
</style>
