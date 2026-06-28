# Moodle API Integration

Die Anwendung nutzt Moodle Web Services, um Kursmaterialien, Deadlines und weitere studienrelevante Informationen direkt aus Moodle abzurufen und im Study Agent bereitzustellen.

## Aktuell verwendete APIs

| API-Funktion                        | Beschreibung                                                                                                                                                                                                                        |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core_webservice_get_site_info`     | Ruft grundlegende Informationen über den authentifizierten Benutzer ab, einschließlich der Moodle-User-ID. Diese ID wird für weitere benutzerspezifische API-Aufrufe benötigt.                                                      |
| `core_enrol_get_users_courses`      | Lädt alle Moodle-Kurse, in denen der Benutzer eingeschrieben ist. Die Daten werden genutzt, um die Kursübersicht im Frontend darzustellen und Kurse nach Semester zu sortieren.                                                     |
| `core_course_get_contents`          | Ruft die Struktur eines Kurses ab, einschließlich Abschnitten, PDFs, Dateien, Aufgaben, URLs und weiteren Lernressourcen. Diese Daten bilden die Grundlage für die Moodle Course Overview sowie die KI-gestützte Dokumentenanalyse. |
| `core_calendar_get_calendar_events` | Lädt Kalenderereignisse wie Abgabefristen, Quiz-Termine und wichtige Kursereignisse. Diese Informationen werden für den Planner und zukünftige KI-Empfehlungen verwendet.                                                           |
