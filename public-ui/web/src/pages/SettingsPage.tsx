import { useState } from 'react'

import {
  useAlerts,
  useDeleteAlert,
  useMeta,
  usePushSubscriptions,
  useSaveAlert,
  useSavePush,
  useTestAlert,
  useUpdateProfile,
} from '../api/hooks'
import type { Alert } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { BellIcon, PlusIcon } from '../components/Icons'
import { useToast } from '../components/Toast'
import { absoluteTime } from '../lib/format'
import { pushSupported, subscribeToPush } from '../lib/push'
import { AlertBuilder } from './panes/AlertBuilder'

function describe(alert: Alert): string {
  const bits: string[] = []
  const { criteria } = alert
  bits.push(criteria.categories?.length ? criteria.categories.join(', ') : 'Any category')
  if (criteria.cities?.length) bits.push(`in ${criteria.cities.join(', ')}`)
  if (criteria.specs?.length) bits.push(`${criteria.specs.length} number rule(s)`)
  if (criteria.unknowns_required?.length) {
    bits.push(`missing ${criteria.unknowns_required.join(', ')}`)
  }
  return bits.join(' · ')
}

function AlertsSection() {
  const meta = useMeta()
  const alerts = useAlerts()
  const save = useSaveAlert()
  const remove = useDeleteAlert()
  const test = useTestAlert()
  const { toast } = useToast()

  const [editing, setEditing] = useState<Alert | 'new' | null>(null)
  const [confirming, setConfirming] = useState<Alert | null>(null)
  const [error, setError] = useState('')

  if (!meta.data) return <p className="muted">Loading…</p>

  return (
    <section className="settings-card">
      <div className="pane-head">
        <div>
          <h2 className="title-block">Alerts</h2>
          <p className="muted">
            Save the shape of a deal you want, and we'll tell you when one lands.
          </p>
        </div>
        {!editing && (
          <button className="btn btn-brass" onClick={() => setEditing('new')}>
            <PlusIcon /> New alert
          </button>
        )}
      </div>

      {editing ? (
        <AlertBuilder
          meta={meta.data}
          initial={editing === 'new' ? undefined : editing}
          saving={save.isPending}
          error={error}
          onCancel={() => {
            setEditing(null)
            setError('')
          }}
          onSave={(payload) => {
            setError('')
            save.mutate(payload, {
              onSuccess: () => {
                setEditing(null)
                toast(payload.id ? 'Alert saved' : 'Alert created')
              },
              onError: (err) => setError(err instanceof Error ? err.message : 'Could not save'),
            })
          }}
        />
      ) : alerts.data?.items.length === 0 ? (
        <div className="empty-state empty-inline">
          <BellIcon />
          <p className="muted">
            No alerts yet. Describe one deal you'd drop everything for, and we'll watch for it.
          </p>
        </div>
      ) : (
        <ul className="alert-list">
          {alerts.data?.items.map((alert) => (
            <li key={alert.id} className={`alert-item${alert.enabled ? '' : ' alert-off'}`}>
              <div className="alert-main">
                <p className="alert-name">{alert.name}</p>
                <p className="faint">{describe(alert)}</p>
                <p className="faint">
                  {alert.digest === 'instant' ? 'As they land' : `${alert.digest} roundup`} ·{' '}
                  {alert.channels.join(', ')} · up to {alert.max_per_day}/day
                  {alert.last_fired_at && ` · last sent ${absoluteTime(alert.last_fired_at)}`}
                </p>
              </div>
              <div className="alert-actions">
                <button
                  className="btn btn-sm"
                  onClick={() =>
                    save.mutate(
                      { id: alert.id, enabled: !alert.enabled },
                      { onSuccess: () => toast(alert.enabled ? 'Alert paused' : 'Alert resumed') },
                    )
                  }
                >
                  {alert.enabled ? 'Pause' : 'Resume'}
                </button>
                <button
                  className="btn btn-sm"
                  disabled={test.isPending}
                  onClick={() =>
                    test.mutate(alert.id, {
                      onSuccess: (result) => {
                        const failed = Object.entries(result.outcomes).filter(
                          ([, outcome]) => outcome !== 'sent',
                        )
                        toast(
                          failed.length
                            ? `${failed[0][0]}: ${failed[0][1]}`
                            : 'Test sent — check your inbox',
                        )
                      },
                    })
                  }
                >
                  Send a test
                </button>
                <button className="btn btn-sm" onClick={() => setEditing(alert)}>
                  Edit
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => setConfirming(alert)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {confirming && (
        <ConfirmDialog
          danger
          title="Delete this alert?"
          body={`"${confirming.name}" stops watching, and its history of what it already sent is cleared.`}
          confirmLabel="Delete alert"
          onCancel={() => setConfirming(null)}
          onConfirm={() => {
            remove.mutate(confirming.id, { onSuccess: () => toast('Alert deleted') })
            setConfirming(null)
          }}
        />
      )}
    </section>
  )
}

function DeliverySection() {
  const meta = useMeta()
  const push = usePushSubscriptions()
  const savePush = useSavePush()
  const { user } = useAuth()
  const updateProfile = useUpdateProfile()
  const { toast } = useToast()
  const [phone, setPhone] = useState(user?.phone ?? '')
  const [pushError, setPushError] = useState('')

  const channels = meta.data?.channels ?? []
  const email = channels.find((c) => c.id === 'email')
  const webpush = channels.find((c) => c.id === 'webpush')
  const sms = channels.find((c) => c.id === 'sms')
  const subscribed = (push.data?.items.length ?? 0) > 0

  // "Confirmed" is about the address; whether we can actually send is a
  // separate question, and the answer here was previously always yes.
  const emailStatus = !email?.enabled
    ? "Email isn't switched on for this site, so email alerts are unavailable."
    : user?.email_verified
      ? 'Confirmed. Email alerts can be switched on.'
      : 'Not confirmed yet — check your inbox for the link before turning on email alerts.'

  return (
    <section className="settings-card">
      <h2 className="title-block">How we reach you</h2>

      <div className="delivery-row">
        <div>
          <p>
            <strong>Email</strong> — {user?.email}
          </p>
          <p className="faint">{emailStatus}</p>
        </div>
      </div>

      {webpush?.enabled && (
        <div className="delivery-row">
          <div>
            <p>
              <strong>Instant push</strong> — {subscribed ? 'on for this browser' : 'off'}
            </p>
            <p className="faint">{webpush.note}</p>
            {pushError && (
              <p className="error-banner" role="alert">
                {pushError}
              </p>
            )}
          </div>
          <button
            className="btn"
            disabled={!pushSupported() || savePush.isPending}
            onClick={async () => {
              setPushError('')
              try {
                const subscription = await subscribeToPush(push.data?.public_key ?? '')
                savePush.mutate(subscription, {
                  onSuccess: () => toast('Push is on for this browser'),
                })
              } catch (err) {
                setPushError(err instanceof Error ? err.message : 'Could not turn on push')
              }
            }}
          >
            {subscribed ? 'Re-enable on this browser' : 'Turn on push here'}
          </button>
        </div>
      )}

      {sms?.enabled && (
        <div className="delivery-row">
          <div className="field">
            <span>Mobile number</span>
            <input
              className="input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 555 123 4567"
              inputMode="tel"
            />
            <span className="faint">{sms.note}</span>
          </div>
          <button
            className="btn"
            disabled={updateProfile.isPending || phone === user?.phone}
            onClick={() =>
              updateProfile.mutate({ phone }, { onSuccess: () => toast('Number saved') })
            }
          >
            Save number
          </button>
        </div>
      )}

      {!channels.some((c) => c.enabled) && (
        <p className="muted">
          No delivery channel is switched on for this site yet.
        </p>
      )}
    </section>
  )
}

export function SettingsPage() {
  const { user, signOut } = useAuth()
  const updateProfile = useUpdateProfile()
  const { toast } = useToast()
  const [name, setName] = useState(user?.display_name ?? '')

  return (
    <div className="settings-page">
      <h1 className="title-block page-title">Settings</h1>

      <AlertsSection />
      <DeliverySection />

      <section className="settings-card">
        <h2 className="title-block">Your account</h2>
        <div className="delivery-row">
          <label className="field">
            <span>Name</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <button
            className="btn"
            disabled={updateProfile.isPending || name === user?.display_name}
            onClick={() =>
              updateProfile.mutate({ display_name: name }, { onSuccess: () => toast('Name saved') })
            }
          >
            Save
          </button>
        </div>
        {user?.providers.length ? (
          <p className="faint">
            Signed in with {user.providers.map((p) => p.provider).join(', ')}.
          </p>
        ) : null}
        <div>
          <button className="btn" onClick={signOut}>
            Sign out
          </button>
        </div>
      </section>
    </div>
  )
}
