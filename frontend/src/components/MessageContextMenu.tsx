import { Forward, Reply, Trash2 } from "lucide-react"

const QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "🔥"]

interface MessageContextMenuProps {
  x: number
  y: number
  showDelete?: boolean
  onReply: () => void
  onForward: () => void
  onReact: (emoji: string) => void
  onDelete?: () => void
  t: (key: string) => string
}

export default function MessageContextMenu({
  x,
  y,
  showDelete = false,
  onReply,
  onForward,
  onReact,
  onDelete,
  t,
}: MessageContextMenuProps) {
  return (
    <div
      className="message-context-menu"
      style={{ left: x, top: y }}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="message-context-reactions">
        {QUICK_REACTIONS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            className="message-context-reaction"
            onClick={() => onReact(emoji)}
          >
            {emoji}
          </button>
        ))}
      </div>

      <div className="message-context-actions">
        <button type="button" onClick={onReply}>
          <Reply size={14} />
          {t("reply")}
        </button>
        <button type="button" onClick={onForward}>
          <Forward size={14} />
          {t("forward")}
        </button>
        {showDelete && onDelete ? (
          <button type="button" className="danger" onClick={onDelete}>
            <Trash2 size={14} />
            {t("delete")}
          </button>
        ) : null}
      </div>
    </div>
  )
}
