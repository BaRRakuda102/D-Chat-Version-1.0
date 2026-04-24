import { X } from "lucide-react"

interface ImageViewerModalProps {
  src: string
  alt?: string
  caption?: string
  onClose: () => void
}

export default function ImageViewerModal({
  src,
  alt = "",
  caption,
  onClose,
}: ImageViewerModalProps) {
  return (
    <div className="modal-overlay image-viewer-overlay" onClick={onClose}>
      <div className="image-viewer" onClick={(event) => event.stopPropagation()}>
        <button className="icon-btn image-viewer-close" onClick={onClose}>
          <X size={18} />
        </button>
        <div className="image-viewer-frame">
          <img src={src} alt={alt} className="image-viewer-image" />
        </div>
        {caption ? <div className="image-viewer-caption">{caption}</div> : null}
      </div>
    </div>
  )
}
