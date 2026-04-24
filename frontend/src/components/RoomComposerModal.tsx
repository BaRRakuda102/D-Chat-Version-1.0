import { useRef } from "react"
import { Camera, Check, Users, X } from "lucide-react"

interface FriendOption {
  id: number
  username: string
  avatar_url?: string
  is_online?: boolean
}

interface RoomDraftState {
  name: string
  description: string
  avatar_url: string
  member_ids: number[]
}

interface RoomComposerModalProps {
  title: string
  copy: string
  submitLabel: string
  nameLabel: string
  draft: RoomDraftState
  friends: FriendOption[]
  allowEmptyMembers: boolean
  isSubmitting: boolean
  isUploadingAvatar: boolean
  feedback: { type: "success" | "error"; message: string } | null
  showMemberPicker?: boolean
  onClose: () => void
  onChange: (patch: Partial<RoomDraftState>) => void
  onToggleMember: (userId: number) => void
  onAvatarSelected: (file: File) => void
  onSubmit: () => void
  t: (key: string) => string
}

function AvatarPreview({
  url,
  name,
}: {
  url?: string
  name?: string
}) {
  return (
    <div className="room-composer-avatar">
      {url ? <img src={url} alt="" /> : name?.[0]?.toUpperCase() || "?"}
    </div>
  )
}

export default function RoomComposerModal({
  title,
  copy,
  submitLabel,
  nameLabel,
  draft,
  friends,
  allowEmptyMembers,
  isSubmitting,
  isUploadingAvatar,
  feedback,
  showMemberPicker = true,
  onClose,
  onChange,
  onToggleMember,
  onAvatarSelected,
  onSubmit,
  t,
}: RoomComposerModalProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel wide" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <Users size={16} /> {title}
          <button className="icon-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <p className="modal-copy">{copy}</p>

          <div className="room-composer-hero">
            <AvatarPreview url={draft.avatar_url} name={draft.name || title} />
            <div className="room-composer-hero-copy">
              <strong>{draft.name || title}</strong>
              <span>
                {showMemberPicker
                  ? `${draft.member_ids.length + 1} ${t("members")}`
                  : copy}
              </span>
            </div>
            <input
              ref={inputRef}
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
              onClick={() => inputRef.current?.click()}
              disabled={isUploadingAvatar}
            >
              <Camera size={14} />
              {isUploadingAvatar ? t("uploading") : t("changeAvatar")}
            </button>
          </div>

          {feedback && (
            <div className={`modal-feedback ${feedback.type}`}>
              {feedback.message}
            </div>
          )}

          <label className="modal-field">
            <span>{nameLabel}</span>
            <input
              className="glass-input"
              value={draft.name}
              onChange={(event) => onChange({ name: event.target.value })}
              placeholder={title}
            />
          </label>

          <label className="modal-field">
            <span>{t("description")}</span>
            <input
              className="glass-input"
              value={draft.description}
              onChange={(event) => onChange({ description: event.target.value })}
              placeholder={t("description")}
            />
          </label>

          {showMemberPicker && (
            <div className="room-composer-members">
              <div className="profile-section-head">
                <h4>{t("friends")}</h4>
                <span className="tag">{draft.member_ids.length}</span>
              </div>
              {!allowEmptyMembers && (
                <p className="modal-copy">{t("groupNeedsMembers")}</p>
              )}
              {friends.length === 0 ? (
                <p className="modal-copy">{t("noFriendsYet")}</p>
              ) : (
                <div className="room-composer-grid">
                  {friends.map((friend) => {
                    const selected = draft.member_ids.includes(friend.id)
                    return (
                      <button
                        key={friend.id}
                        type="button"
                        className={`room-composer-member ${selected ? "selected" : ""}`}
                        onClick={() => onToggleMember(friend.id)}
                      >
                        <AvatarPreview url={friend.avatar_url} name={friend.username} />
                        <div className="room-composer-member-copy">
                          <strong>{friend.username}</strong>
                          <span>{friend.is_online ? t("online") : t("offline")}</span>
                        </div>
                        {selected && <Check size={16} />}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          <div className="modal-actions">
            <button className="glass-button" onClick={onClose}>
              {t("cancel")}
            </button>
            <button className="glass-button primary" onClick={onSubmit} disabled={isSubmitting}>
              {isSubmitting ? t("saving") : submitLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
