import { useMemo, useRef } from "react"
import { CalendarDays, Camera, Check, LogOut, Mail, MessageSquare, Save, ShieldCheck, Trash2, User, X } from "lucide-react"

interface ProfileUser {
  id: number
  username: string
  display_name?: string
  email?: string
  avatar_url?: string
  is_online?: boolean
  is_superuser?: boolean
  is_verified?: boolean
  date_of_birth?: string
  age?: number
  created_at?: string
}

interface ProfileRequestUser {
  id: number
  username: string
  avatar_url?: string
  is_online?: boolean
}

interface ProfileFriendRequest {
  id: number
  from_user?: ProfileRequestUser
}

interface ProfileFriend {
  id: number
  friend_id: number
  friend?: ProfileRequestUser
}

interface ProfileFormState {
  display_name: string
  email: string
  date_of_birth: string
  avatar_url: string
}

interface ProfileModalProps {
  user: ProfileUser
  isCurrentUser: boolean
  form: ProfileFormState
  isSaving: boolean
  isUploadingAvatar: boolean
  feedback: { type: "success" | "error"; message: string } | null
  onClose: () => void
  onFormChange: (patch: Partial<ProfileFormState>) => void
  onSave: () => void
  onLogout: () => void
  onStartChat?: () => void
  onAvatarOpen?: (src: string, title: string) => void
  onAvatarSelected: (file: File) => void
  requests?: ProfileFriendRequest[]
  friends?: ProfileFriend[]
  onAcceptRequest?: (requestId: number) => void
  onRejectRequest?: (requestId: number) => void
  onRemoveFriend?: (friendshipId: number) => void
  onStartPrivateChat?: (userId: number) => void
  onOpenUserProfile?: (userId: number) => void
  t: (key: string) => string
}

function AvatarPreview({
  url,
  name,
  size = 96,
}: {
  url?: string
  name?: string
  size?: number
}) {
  return (
    <div
      className="avatar-placeholder"
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      {url ? (
        <img
          src={url}
          alt=""
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <span style={{ fontSize: size * 0.38 }}>
          {name?.[0]?.toUpperCase() || "?"}
        </span>
      )}
    </div>
  )
}

function formatMemberSince(value?: string) {
  if (!value) return null

  try {
    return new Date(value).toLocaleDateString()
  } catch {
    return null
  }
}

export default function ProfileModal({
  user,
  isCurrentUser,
  form,
  isSaving,
  isUploadingAvatar,
  feedback,
  onClose,
  onFormChange,
  onSave,
  onLogout,
  onStartChat,
  onAvatarOpen,
  onAvatarSelected,
  requests = [],
  friends = [],
  onAcceptRequest,
  onRejectRequest,
  onRemoveFriend,
  onStartPrivateChat,
  onOpenUserProfile,
  t,
}: ProfileModalProps) {
  const avatarInputRef = useRef<HTMLInputElement>(null)

  const memberSince = useMemo(
    () => formatMemberSince(user.created_at),
    [user.created_at]
  )

  const shownAge = useMemo(() => {
    if (!form.date_of_birth) return user.age ?? null

    const birthDate = new Date(form.date_of_birth)
    if (Number.isNaN(birthDate.getTime())) return user.age ?? null

    const today = new Date()
    let age = today.getFullYear() - birthDate.getFullYear()
    const monthDelta = today.getMonth() - birthDate.getMonth()
    const dayDelta = today.getDate() - birthDate.getDate()

    if (monthDelta < 0 || (monthDelta === 0 && dayDelta < 0)) {
      age -= 1
    }

    return age >= 0 ? age : null
  }, [form.date_of_birth, user.age])

  const profileName = user.display_name || user.username
  const profileAvatar = isCurrentUser ? form.avatar_url || user.avatar_url : user.avatar_url

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel wide profile-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <User size={16} /> {t("profile")}
          <button className="icon-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <div className="profile-hero">
            <div className="profile-avatar-stack">
              <button
                type="button"
                className="profile-avatar-button"
                onClick={() => profileAvatar && onAvatarOpen?.(profileAvatar, profileName)}
                disabled={!profileAvatar}
              >
                <AvatarPreview url={profileAvatar} name={profileName} size={96} />
              </button>
              {isCurrentUser && (
                <>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    style={{ display: "none" }}
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) {
                        onAvatarSelected(file)
                        event.target.value = ""
                      }
                    }}
                  />
                  <button
                    className="glass-button small"
                    onClick={() => avatarInputRef.current?.click()}
                    disabled={isUploadingAvatar}
                  >
                    <Camera size={14} />
                    {isUploadingAvatar ? t("uploading") : t("changeAvatar")}
                  </button>
                </>
              )}
            </div>

            <div className="profile-hero-content">
              <h3>{profileName}</h3>
              <p className="profile-subtitle">@{user.username}</p>
              <div className="profile-badges">
                <span className={`status-pill ${user.is_online ? "online" : "offline"}`}>
                  {user.is_online ? t("online") : t("offline")}
                </span>
                {user.is_verified && (
                  <span className="status-pill verified">
                    <ShieldCheck size={12} /> {t("verified")}
                  </span>
                )}
              </div>
            </div>
          </div>

          {feedback && (
            <div className={`modal-feedback ${feedback.type}`}>
              {feedback.message}
            </div>
          )}

          {isCurrentUser ? (
            <>
              <div className="profile-grid">
                <label className="modal-field">
                  <span>{t("displayName")}</span>
                  <input
                    className="glass-input"
                    value={form.display_name}
                    onChange={(event) => onFormChange({ display_name: event.target.value })}
                    placeholder={t("displayName")}
                  />
                </label>

                <label className="modal-field">
                  <span>{t("email")}</span>
                  <input
                    className="glass-input"
                    type="email"
                    value={form.email}
                    onChange={(event) => onFormChange({ email: event.target.value })}
                    placeholder="name@example.com"
                  />
                </label>

                <label className="modal-field">
                  <span>{t("birthDate")}</span>
                  <input
                    className="glass-input"
                    type="date"
                    value={form.date_of_birth}
                    onChange={(event) => onFormChange({ date_of_birth: event.target.value })}
                  />
                </label>

                <div className="profile-stat-card">
                  <span>{t("age")}</span>
                  <strong>{shownAge ?? "—"}</strong>
                </div>
              </div>

              <div className="profile-meta">
                <div>
                  <Mail size={14} />
                  <span>{form.email || "—"}</span>
                </div>
                <div>
                  <CalendarDays size={14} />
                  <span>
                    {memberSince
                      ? `${t("memberSince")}: ${memberSince}`
                      : t("memberSinceUnknown")}
                  </span>
                </div>
              </div>

              <div className="modal-actions">
                <button className="glass-button" onClick={onLogout}>
                  <LogOut size={14} /> {t("logout")}
                </button>
                <button className="glass-button primary" onClick={onSave} disabled={isSaving}>
                  <Save size={14} /> {isSaving ? t("saving") : t("saveChanges")}
                </button>
              </div>

              <div className="profile-list-section">
                <div className="profile-section-head">
                  <h4>{t("requests")}</h4>
                  <span className="tag">{requests.length}</span>
                </div>
                {requests.length === 0 ? (
                  <p className="modal-copy">{t("noRequests")}</p>
                ) : (
                  <div className="profile-list">
                    {requests.map((request) => (
                      <div key={request.id} className="profile-list-row">
                        <div className="profile-list-main">
                          <AvatarPreview
                            url={request.from_user?.avatar_url}
                            name={request.from_user?.username}
                            size={42}
                          />
                          <div className="profile-list-copy">
                            <strong>{request.from_user?.username || t("unknown")}</strong>
                            <span>{t("incomingRequest")}</span>
                          </div>
                        </div>
                        <div className="profile-list-actions">
                          <button
                            className="icon-btn success"
                            onClick={() => onAcceptRequest?.(request.id)}
                          >
                            <Check size={14} />
                          </button>
                          <button
                            className="icon-btn danger"
                            onClick={() => onRejectRequest?.(request.id)}
                          >
                            <X size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="profile-list-section">
                <div className="profile-section-head">
                  <h4>{t("friends")}</h4>
                  <span className="tag">{friends.length}</span>
                </div>
                {friends.length === 0 ? (
                  <p className="modal-copy">{t("noFriendsYet")}</p>
                ) : (
                  <div className="profile-list">
                    {friends.map((friend) => (
                      <div key={friend.id} className="profile-list-row">
                        <button
                          type="button"
                          className="profile-list-main profile-list-main-button"
                          onClick={() => friend.friend_id && onOpenUserProfile?.(friend.friend_id)}
                        >
                          <AvatarPreview
                            url={friend.friend?.avatar_url}
                            name={friend.friend?.username}
                            size={42}
                          />
                          <div className="profile-list-copy">
                            <strong>{friend.friend?.username || t("unknown")}</strong>
                            <span>
                              {friend.friend?.is_online ? t("online") : t("offline")}
                            </span>
                          </div>
                        </button>
                        <div className="profile-list-actions">
                          <button
                            className="glass-button small"
                            onClick={() => friend.friend_id && onStartPrivateChat?.(friend.friend_id)}
                          >
                            <MessageSquare size={14} /> {t("sendMessage")}
                          </button>
                          <button
                            className="icon-btn danger"
                            onClick={() => onRemoveFriend?.(friend.id)}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="profile-meta">
                {user.age != null && (
                  <div>
                    <CalendarDays size={14} />
                    <span>
                      {t("age")}: {user.age}
                    </span>
                  </div>
                )}
                {memberSince && (
                  <div>
                    <ShieldCheck size={14} />
                    <span>
                      {t("memberSince")}: {memberSince}
                    </span>
                  </div>
                )}
              </div>

              {onStartChat && (
                <div className="modal-actions">
                  <button className="glass-button primary" onClick={onStartChat}>
                    <MessageSquare size={14} /> {t("sendMessage")}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
