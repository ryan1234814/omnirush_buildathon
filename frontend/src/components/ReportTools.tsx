import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  createSchedule,
  deleteSchedule,
  downloadReportFormat,
  getReportDiff,
  getReportFormatUrl,
  listNotifications,
  listSchedules,
  markNotificationRead,
  sendFollowUpChat,
  type FollowUpChatResponse,
  type Notification,
  type ReportDiff,
  type ReportFormat,
  type Schedule,
  type ScheduleFrequency,
} from '../api/client'
import type { HistoryEntry } from './RecentRuns'

type ReportToolsProps = {
  runId: string
  topic: string
  history: HistoryEntry[]
}

const REPORT_FORMATS: Array<{ value: ReportFormat; label: string }> = [
  { value: 'pdf', label: 'PDF' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
  { value: 'text', label: 'Plain text' },
  { value: 'json', label: 'JSON' },
  { value: 'executive-summary', label: 'Executive summary' },
  { value: 'blog', label: 'Blog post' },
  { value: 'linkedin', label: 'LinkedIn digest' },
  { value: 'marp', label: 'Marp slides' },
]

const SCHEDULE_FREQUENCIES: Array<{ value: ScheduleFrequency; label: string }> = [
  { value: 'once', label: 'One time' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
]

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function formatFilename(runId: string, format: ReportFormat): string {
  const extensions: Record<ReportFormat, string> = {
    markdown: 'md',
    pdf: 'pdf',
    html: 'html',
    text: 'txt',
    json: 'json',
    'executive-summary': 'executive.md',
    blog: 'blog.md',
    linkedin: 'linkedin.md',
    marp: 'marp.md',
  }
  return `research-report-${runId}.${extensions[format]}`
}

function ReportTools({ runId, topic, history }: ReportToolsProps) {
  const [followUp, setFollowUp] = useState('')
  const [followUpLoading, setFollowUpLoading] = useState(false)
  const [followUpError, setFollowUpError] = useState('')
  const [followUpResponse, setFollowUpResponse] = useState<FollowUpChatResponse | null>(null)
  const [selectedFormat, setSelectedFormat] = useState<ReportFormat>('pdf')
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [compareRunId, setCompareRunId] = useState('')
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState('')
  const [diff, setDiff] = useState<ReportDiff | null>(null)
  const [scheduleTopic, setScheduleTopic] = useState(topic)
  const [scheduleFrequency, setScheduleFrequency] = useState<ScheduleFrequency>('weekly')
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [scheduleError, setScheduleError] = useState('')
  const [schedules, setSchedules] = useState<Schedule[] | null>(null)
  const [schedulesLoading, setSchedulesLoading] = useState(false)
  const [notifications, setNotifications] = useState<Notification[] | null>(null)
  const [notificationsLoading, setNotificationsLoading] = useState(false)
  const [notificationsError, setNotificationsError] = useState('')

  const comparableRuns = history.filter((entry) => entry.id !== runId && entry.status === 'completed')

  async function handleFollowUpSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const message = followUp.trim()
    if (!message) {
      setFollowUpError('Ask a question about this report first.')
      return
    }
    setFollowUpLoading(true)
    setFollowUpError('')
    try {
      const response = await sendFollowUpChat(runId, { message, conversation_id: followUpResponse?.conversation_id })
      setFollowUpResponse(response)
      setFollowUp('')
    } catch (error: unknown) {
      setFollowUpError(errorMessage(error, 'The follow-up could not be sent.'))
    } finally {
      setFollowUpLoading(false)
    }
  }

  async function handleDownload(): Promise<void> {
    setDownloadLoading(true)
    setDownloadError('')
    try {
      const blob = await downloadReportFormat(runId, selectedFormat)
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = formatFilename(runId, selectedFormat)
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(objectUrl)
    } catch (error: unknown) {
      setDownloadError(errorMessage(error, `The ${selectedFormat} export could not be downloaded.`))
    } finally {
      setDownloadLoading(false)
    }
  }

  async function handleCompare(): Promise<void> {
    if (!compareRunId) {
      setDiffError('Choose another completed run to compare.')
      return
    }
    setDiffLoading(true)
    setDiffError('')
    try {
      setDiff(await getReportDiff(runId, compareRunId))
    } catch (error: unknown) {
      setDiffError(errorMessage(error, 'The report comparison could not be loaded.'))
      setDiff(null)
    } finally {
      setDiffLoading(false)
    }
  }

  async function handleScheduleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (!scheduleTopic.trim()) {
      setScheduleError('Enter a topic for the scheduled run.')
      return
    }
    setScheduleLoading(true)
    setScheduleError('')
    try {
      const schedule = await createSchedule({
        topic: scheduleTopic.trim(),
        frequency: scheduleFrequency,
        run_id: runId,
      })
      setSchedules((current) => [schedule, ...(current ?? [])])
    } catch (error: unknown) {
      setScheduleError(errorMessage(error, 'The schedule could not be created.'))
    } finally {
      setScheduleLoading(false)
    }
  }

  async function loadSchedules(): Promise<void> {
    setSchedulesLoading(true)
    setScheduleError('')
    try {
      setSchedules(await listSchedules())
    } catch (error: unknown) {
      setScheduleError(errorMessage(error, 'Schedules could not be loaded.'))
    } finally {
      setSchedulesLoading(false)
    }
  }

  async function removeSchedule(scheduleId: string): Promise<void> {
    setScheduleError('')
    try {
      await deleteSchedule(scheduleId)
      setSchedules((current) => current?.filter((schedule) => schedule.id !== scheduleId) ?? current)
    } catch (error: unknown) {
      setScheduleError(errorMessage(error, 'The schedule could not be removed.'))
    }
  }

  async function loadNotifications(): Promise<void> {
    setNotificationsLoading(true)
    setNotificationsError('')
    try {
      setNotifications(await listNotifications())
    } catch (error: unknown) {
      setNotificationsError(errorMessage(error, 'Notifications could not be loaded.'))
    } finally {
      setNotificationsLoading(false)
    }
  }

  async function readNotification(notification: Notification): Promise<void> {
    if (notification.read) return
    try {
      const updated = await markNotificationRead(notification.id)
      setNotifications((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? current)
    } catch (error: unknown) {
      setNotificationsError(errorMessage(error, 'The notification could not be marked read.'))
    }
  }

  return (
    <section className="report-tools" aria-labelledby="report-tools-title">
      <div className="report-tools-heading">
        <div>
          <p className="eyebrow">REPORT ACTIONS</p>
          <h3 id="report-tools-title">Keep working with this run</h3>
        </div>
        <span className="report-tools-run">RUN {runId.slice(0, 8)}</span>
      </div>

      <div className="report-tools-grid">
        <section className="report-tool-card" aria-labelledby="follow-up-title">
          <p className="eyebrow">FOLLOW-UP CHAT</p>
          <h4 id="follow-up-title">Ask about the evidence</h4>
          <form className="tool-form" onSubmit={(event) => void handleFollowUpSubmit(event)}>
            <textarea
              value={followUp}
              onChange={(event) => setFollowUp(event.target.value)}
              placeholder="What changed since last year?"
              rows={3}
              aria-label="Follow-up question"
              disabled={followUpLoading}
            />
            <button type="submit" className="tool-button" disabled={followUpLoading}>
              {followUpLoading ? 'Asking…' : 'Ask follow-up'}
            </button>
          </form>
          {followUpError && <p className="tool-error" role="alert">{followUpError}</p>}
          {followUpResponse && (
            <div className="tool-result" role="status">
              <strong>Response</strong>
              <p>{followUpResponse.answer}</p>
              {followUpResponse.citations && followUpResponse.citations.length > 0 && (
                <small>Sources: {followUpResponse.citations.map((citation) => `[${citation}]`).join(' ')}</small>
              )}
            </div>
          )}
        </section>

        <section className="report-tool-card" aria-labelledby="format-title">
          <p className="eyebrow">ALTERNATE FORMATS</p>
          <h4 id="format-title">Export this report</h4>
          <div className="tool-inline-form">
            <label htmlFor="report-format">Format</label>
            <select id="report-format" value={selectedFormat} onChange={(event) => setSelectedFormat(event.target.value as ReportFormat)}>
              {REPORT_FORMATS.map((format) => <option value={format.value} key={format.value}>{format.label}</option>)}
            </select>
            <button type="button" className="tool-button" onClick={() => void handleDownload()} disabled={downloadLoading}>
              {downloadLoading ? 'Preparing…' : 'Download'}
            </button>
          </div>
          <div className="format-links" aria-label="Report format links">
            {REPORT_FORMATS.map((format) => (
              <a href={getReportFormatUrl(runId, format.value)} download={formatFilename(runId, format.value)} key={format.value}>
                {format.label}
              </a>
            ))}
          </div>
          {downloadError && <p className="tool-error" role="alert">{downloadError}</p>}
        </section>

        <section className="report-tool-card" aria-labelledby="compare-title">
          <p className="eyebrow">COMPARE RUNS</p>
          <h4 id="compare-title">See what changed</h4>
          <div className="tool-inline-form">
            <label htmlFor="compare-run">Against</label>
            <select id="compare-run" value={compareRunId} onChange={(event) => setCompareRunId(event.target.value)} disabled={comparableRuns.length === 0}>
              <option value="">{comparableRuns.length > 0 ? 'Choose a completed run' : 'No other completed runs'}</option>
              {comparableRuns.map((entry) => <option value={entry.id} key={entry.id}>{entry.topic}</option>)}
            </select>
            <button type="button" className="tool-button" onClick={() => void handleCompare()} disabled={diffLoading || comparableRuns.length === 0}>
              {diffLoading ? 'Comparing…' : 'Compare'}
            </button>
          </div>
          {diffError && <p className="tool-error" role="alert">{diffError}</p>}
          {diff && (
            <div className="tool-result diff-result" role="status">
              <strong>{diff.summary || `${diff.changes.length} changes found`}</strong>
              {diff.changes.length > 0 && (
                <ul>
                  {diff.changes.map((change, index) => <li key={`${change.section}-${index}`}><b>{change.section}</b> · {change.status || 'changed'}</li>)}
                </ul>
              )}
            </div>
          )}
        </section>

        <section className="report-tool-card" aria-labelledby="schedule-title">
          <div className="tool-card-heading">
            <div>
              <p className="eyebrow">SCHEDULE</p>
              <h4 id="schedule-title">Run it again</h4>
            </div>
            <button type="button" className="tool-link-button" onClick={() => void loadSchedules()} disabled={schedulesLoading}>
              {schedulesLoading ? 'Loading…' : 'View schedules'}
            </button>
          </div>
          <form className="tool-form" onSubmit={(event) => void handleScheduleSubmit(event)}>
            <input value={scheduleTopic} onChange={(event) => setScheduleTopic(event.target.value)} aria-label="Scheduled topic" placeholder="Topic to revisit" />
            <div className="tool-inline-form">
              <select value={scheduleFrequency} onChange={(event) => setScheduleFrequency(event.target.value as ScheduleFrequency)} aria-label="Schedule frequency">
                {SCHEDULE_FREQUENCIES.map((frequency) => <option value={frequency.value} key={frequency.value}>{frequency.label}</option>)}
              </select>
              <button type="submit" className="tool-button" disabled={scheduleLoading}>{scheduleLoading ? 'Saving…' : 'Schedule'}</button>
            </div>
          </form>
          {scheduleError && <p className="tool-error" role="alert">{scheduleError}</p>}
          {schedules && (
            <ul className="tool-list">
              {schedules.length === 0 ? <li>No schedules yet.</li> : schedules.slice(0, 3).map((schedule) => (
                <li key={schedule.id}>
                  <span><b>{schedule.topic}</b><small>{schedule.frequency} · {schedule.enabled ? 'active' : 'paused'}</small></span>
                  <button type="button" className="tool-link-button" onClick={() => void removeSchedule(schedule.id)}>Remove</button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="report-tool-card" aria-labelledby="notifications-title">
          <div className="tool-card-heading">
            <div>
              <p className="eyebrow">NOTIFICATIONS</p>
              <h4 id="notifications-title">Delivery updates</h4>
            </div>
            <button type="button" className="tool-link-button" onClick={() => void loadNotifications()} disabled={notificationsLoading}>
              {notificationsLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {notificationsError && <p className="tool-error" role="alert">{notificationsError}</p>}
          {notifications && (
            <ul className="tool-list">
              {notifications.length === 0 ? <li>No notifications.</li> : notifications.slice(0, 3).map((notification) => (
                <li className={notification.read ? '' : 'unread'} key={notification.id}>
                  <button type="button" className="notification-item" onClick={() => void readNotification(notification)}>
                    <b>{notification.title}</b><small>{notification.message}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!notifications && <p className="tool-empty">Refresh to check run delivery updates.</p>}
        </section>
      </div>
    </section>
  )
}

export default ReportTools
