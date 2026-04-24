import { useState, useEffect, useRef, type MouseEvent } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  Send,
  Plus,
  Settings,
  Users,
  UserPlus,
  Shield,
  MessageSquare,
  Lock,
  Hash,
  ChevronDown,
  Smile,
  Reply,
  Trash2,
  Edit3,
  Check,
  X,
  Crown,
  UserX,
  Search,
  Moon,
  Sun,
  Languages,
  ArrowLeft,
  Image as ImageIcon,
  User,
  ShieldCheck,
} from "lucide-react"
import { useAuthStore } from "../store/authStore"
import { useThemeStore } from "../store/themeStore"
import { useTranslation } from "../hooks/useTranslation"
import LanguageSelector from "../components/LanguageSelector"
import ProfileModal from "../components/ProfileModal"
import RoomComposerModal from "../components/RoomComposerModal"
import ImageViewerModal from "../components/ImageViewerModal"
import MessageContextMenu from "../components/MessageContextMenu"
import { apiJson, apiVoid, buildWebSocketUrl } from "../lib/api"
import { optimizeUploadFile } from "../lib/media"

interface Room {
  id: number
  name: string
  type: "private" | "group" | "channel"
  description?: string
  avatar_url?: string
  owner_id?: number
  member_count?: number
  unread?: number
  last_message?: string
  created_at?: string
  updated_at?: string
}
interface Member {
  user_id: number
  role: "owner" | "admin" | "member"
  can_send_messages?: boolean
  user?: {
    id: number
    username: string
    avatar_url?: string
    is_online?: boolean
  }
}
interface MessageReaction {
  emoji: string
  count: number
}
interface MessageAttachment {
  id?: number
  file_url: string
  file_name: string
  file_type: string
  file_size: number
}
interface Message {
  id: number
  room_id: number
  sender_id: number
  content: string
  reply_to_id?: number | null
  created_at: string
  sender?: { id: number; username: string; avatar_url?: string }
  reactions?: MessageReaction[]
  reply_to?: Message | null
  attachments?: MessageAttachment[]
  is_deleted?: boolean
}
interface FriendRequest {
  id: number
  from_user_id: number
  to_user_id: number
  status: string
  from_user?: { id: number; username: string; avatar_url?: string }
  to_user?: { id: number; username: string; avatar_url?: string }
}
interface Friend {
  id: number
  friend_id: number
  status: string
  user?: { id: number; username: string; avatar_url?: string; is_online?: boolean }
  friend?: { id: number; username: string; avatar_url?: string; is_online?: boolean }
}
interface UserProfile {
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

interface UploadedAttachment {
  file_url: string
  file_name: string
  file_type: string
  file_size: number
}

interface ProfileFormState {
  display_name: string
  email: string
  date_of_birth: string
  avatar_url: string
}

interface RoomDraftState {
  name: string
  description: string
  avatar_url: string
  member_ids: number[]
}

interface ImagePreviewState {
  src: string
  title: string
}

interface MessageMenuState {
  x: number
  y: number
  message: Message
}

interface ToastNotice {
  id: number
  message: string
}

function safeMap<T, R>(
  arr: T[] | null | undefined,
  fn: (item: T, idx: number) => R
): R[] {
  return Array.isArray(arr) ? arr.map(fn) : []
}

const RoomAvatar = ({ url, name }: { url?: string; name?: string }) => (
  <div className="room-avatar">
    {url ? <img src={url} alt="" /> : name?.[0]?.toUpperCase() || "?"}
  </div>
)

function buildProfileForm(profile?: Partial<UserProfile> | null): ProfileFormState {
  return {
    display_name: profile?.display_name || "",
    email: profile?.email || "",
    date_of_birth: profile?.date_of_birth || "",
    avatar_url: profile?.avatar_url || "",
  }
}

function createRoomDraft(room?: Partial<Room>): RoomDraftState {
  return {
    name: room?.name || "",
    description: room?.description || "",
    avatar_url: room?.avatar_url || "",
    member_ids: [],
  }
}

const SmallAvatar = ({
  url,
  name,
  size = 32,
}: {
  url?: string
  name?: string
  size?: number
}) => (
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
      <span style={{ fontSize: size * 0.4 }}>
        {name?.[0]?.toUpperCase() || "?"}
      </span>
    )}
  </div>
)

export default function ChatPage() {
  const navigate = useNavigate()
  const { roomId } = useParams()
  const { user, logout, setUser } = useAuthStore()
  const { theme, toggleTheme, language, setLanguage } = useThemeStore()
  const { t } = useTranslation(language)

  const [rooms, setRooms] = useState<Room[]>([])
  const [activeRoom, setActiveRoom] = useState<number>(Number(roomId) || 0)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState("")
  const [replyTo, setReplyTo] = useState<Message | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [friends, setFriends] = useState<Friend[]>([])
  const [requests, setRequests] = useState<FriendRequest[]>([])
  const [users, setUsers] = useState<UserProfile[]>([])
  const [search, setSearch] = useState("")
  const [ws, setWs] = useState<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [typing, setTyping] = useState(false)
  const [sidebarTab, setSidebarTab] = useState<"rooms" | "friends" | "settings">("rooms")
  const [showProfile, setShowProfile] = useState(false)
  const [profileUser, setProfileUser] = useState<UserProfile | null>(null)
  const [profileForm, setProfileForm] = useState<ProfileFormState>(buildProfileForm())
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileUploadingAvatar, setProfileUploadingAvatar] = useState(false)
  const [profileFeedback, setProfileFeedback] = useState<{
    type: "success" | "error"
    message: string
  } | null>(null)
  const [showAdmin, setShowAdmin] = useState(false)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [showAddFriend, setShowAddFriend] = useState(false)
  const [showNewChat, setShowNewChat] = useState(false)
  const [friendUsername, setFriendUsername] = useState("")
  const [groupDraft, setGroupDraft] = useState<RoomDraftState>(createRoomDraft())
  const [channelDraft, setChannelDraft] = useState<RoomDraftState>(createRoomDraft())
  const [roomEditDraft, setRoomEditDraft] = useState<RoomDraftState>(createRoomDraft())
  const [showRoomEditor, setShowRoomEditor] = useState(false)
  const [groupSubmitting, setGroupSubmitting] = useState(false)
  const [channelSubmitting, setChannelSubmitting] = useState(false)
  const [roomEditSubmitting, setRoomEditSubmitting] = useState(false)
  const [groupUploadingAvatar, setGroupUploadingAvatar] = useState(false)
  const [channelUploadingAvatar, setChannelUploadingAvatar] = useState(false)
  const [roomEditUploadingAvatar, setRoomEditUploadingAvatar] = useState(false)
  const [groupFeedback, setGroupFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null)
  const [channelFeedback, setChannelFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null)
  const [roomEditFeedback, setRoomEditFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null)
  const [showMembers, setShowMembers] = useState(false)
  const [showRoomMenu, setShowRoomMenu] = useState<number | null>(null)
  const [attachFile, setAttachFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(null)
  const [messageMenu, setMessageMenu] = useState<MessageMenuState | null>(null)
  const [forwardMessage, setForwardMessage] = useState<Message | null>(null)
  const [toasts, setToasts] = useState<ToastNotice[]>([])
  const [mobileSidebar, setMobileSidebar] = useState(true)
  const messagesEnd = useRef<HTMLDivElement>(null)
  const typingTimeout = useRef<any>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const activeRoomRef = useRef(activeRoom)

  const currentRoom = rooms.find((r) => r.id === activeRoom)
  const isOwnProfile = !!profileUser && profileUser.id === user?.id
  const currentMembership = members.find((member) => member.user_id === user?.id)
  const roomMemberCount = currentRoom?.member_count ?? members.length

  useEffect(() => {
    if (roomId) {
      setActiveRoom(Number(roomId))
    }
  }, [roomId])

  useEffect(() => {
    loadRooms()
    loadFriends()
    loadRequests()
    loadUsers()
  }, [])

  useEffect(() => {
    if (!showProfile) {
      setProfileFeedback(null)
    }
  }, [showProfile])

  useEffect(() => {
    setShowRoomMenu(null)
    setMessageMenu(null)
    setForwardMessage(null)
  }, [activeRoom])

  useEffect(() => {
    activeRoomRef.current = activeRoom
  }, [activeRoom])

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    if (!messageMenu) return

    const closeMenu = () => setMessageMenu(null)
    window.addEventListener("click", closeMenu)
    window.addEventListener("scroll", closeMenu, true)
    window.addEventListener("resize", closeMenu)

    return () => {
      window.removeEventListener("click", closeMenu)
      window.removeEventListener("scroll", closeMenu, true)
      window.removeEventListener("resize", closeMenu)
    }
  }, [messageMenu])

  useEffect(() => {
    if (!user || activeRoom <= 0) return
    if (ws) {
      ws.close()
      setWs(null)
    }

    const socket = new WebSocket(buildWebSocketUrl(`/ws/chat/${activeRoom}`))

    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)

    socket.onmessage = (ev) => {
      const data = JSON.parse(ev.data)
      if (data.type === "message") {
        setMessages((prev) =>
          prev.some((message) => message.id === data.message?.id)
            ? prev.map((message) =>
                message.id === data.message?.id ? data.message : message
              )
            : [...prev, data.message]
        )
        setRooms((prev) =>
          prev.map((room) =>
            room.id === activeRoom
              ? {
                  ...room,
                  last_message: data.message?.content || room.last_message,
                  unread: 0,
                }
              : room
          )
        )
        if (data.message?.sender_id !== user?.id) {
          markRoomRead(activeRoom)
        }
      } else if (data.type === "typing") {
        setTyping(true)
        clearTimeout(typingTimeout.current)
        typingTimeout.current = setTimeout(() => setTyping(false), 2000)
      } else if (data.type === "reaction_update") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === data.message_id
              ? { ...m, reactions: data.reactions || [] }
              : m
          )
        )
      } else if (data.type === "profile_update" && data.user?.id) {
        applyProfileUpdate(data.user)
      }
    }

    setWs(socket)
    loadMessages(activeRoom)
    loadMembers(activeRoom)

    return () => {
      socket.close()
    }
  }, [activeRoom, user])

  async function loadRooms() {
    try {
      const d = await apiJson<Room[]>("/api/v1/chat/rooms/")
      setRooms(sortRooms(Array.isArray(d) ? d : []))
    } catch (e) {
      console.error(e)
    }
  }

  async function loadMessages(roomId: number) {
    if (roomId <= 0) return
    try {
      const d = await apiJson<Message[]>(
        `/api/v1/chat/rooms/${roomId}/messages?limit=100`
      )
      setMessages(Array.isArray(d) ? d : [])
      setRooms((prev) =>
        prev.map((room) =>
          room.id === roomId ? { ...room, unread: 0 } : room
        )
      )
    } catch (e) {
      console.error(e)
    }
  }

  async function loadMembers(roomId: number) {
    if (roomId <= 0) return
    try {
      const d = await apiJson<Member[]>(`/api/v1/chat/rooms/${roomId}/members`)
      setMembers(Array.isArray(d) ? d : [])
    } catch (e) {
      console.error(e)
    }
  }

  async function loadFriends() {
    try {
      const d = await apiJson<Friend[]>("/api/v1/friends/")
      setFriends(Array.isArray(d) ? d : [])
    } catch (e) {
      console.error(e)
    }
  }

  async function loadRequests() {
    try {
      const d = await apiJson<FriendRequest[]>("/api/v1/friends/requests/")
      setRequests(Array.isArray(d) ? d : [])
    } catch (e) {
      console.error(e)
    }
  }

  async function loadUsers() {
    try {
      const d = await apiJson<UserProfile[]>("/api/v1/users/")
      setUsers(Array.isArray(d) ? d : [])
    } catch (e) {
      console.error(e)
    }
  }

  async function markRoomRead(roomId: number) {
    if (roomId <= 0) return
    try {
      await apiVoid(`/api/v1/chat/rooms/${roomId}/read`, {
        method: "POST",
      })
      setRooms((prev) =>
        prev.map((room) =>
          room.id === roomId ? { ...room, unread: 0 } : room
        )
      )
    } catch (e) {
      console.error(e)
    }
  }

  function pushToast(message: string) {
    const id = Date.now() + Math.floor(Math.random() * 1000)
    setToasts((prev) => [...prev, { id, message }])
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id))
    }, 4500)
  }

  function sortRooms(list: Room[]) {
    return [...list].sort((a, b) => {
      const aTime = a.updated_at ? Date.parse(a.updated_at) : 0
      const bTime = b.updated_at ? Date.parse(b.updated_at) : 0
      return bTime - aTime || b.id - a.id
    })
  }

  function upsertRoom(room: Room) {
    setRooms((prev) => {
      const existing = prev.find((item) => item.id === room.id)
      const next = existing
        ? prev.map((item) => (item.id === room.id ? { ...item, ...room } : item))
        : [...prev, room]
      return sortRooms(next)
    })
  }

  function removeRoom(roomId: number) {
    setRooms((prev) => prev.filter((room) => room.id !== roomId))
  }

  useEffect(() => {
    if (!user) return

    const socket = new WebSocket(buildWebSocketUrl("/ws/notifications"))

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === "room_snapshot" && data.room?.id) {
        upsertRoom(data.room)
        if (data.message && activeRoomRef.current !== data.room.id) {
          pushToast(data.message)
        }
      } else if (data.type === "room_membership_added" && data.room?.id) {
        upsertRoom(data.room)
        if (data.room?.type === "channel" && data.message) {
          pushToast(data.message)
        }
      } else if (data.type === "room_membership_removed") {
        removeRoom(data.room_id)
        if (data.message) {
          pushToast(data.message)
        }
        if (activeRoomRef.current === data.room_id) {
          setMessages([])
          setMembers([])
          setActiveRoom(0)
          navigate("/chat/0")
        }
      }
    }

    return () => {
      socket.close()
    }
  }, [user, navigate])

  function applyProfileUpdate(updatedProfile: UserProfile) {
    setUsers((prev) =>
      prev.map((item) => (item.id === updatedProfile.id ? { ...item, ...updatedProfile } : item))
    )
    setMembers((prev) =>
      prev.map((member) =>
        member.user?.id === updatedProfile.id
          ? { ...member, user: { ...member.user, ...updatedProfile } }
          : member
      )
    )
    setFriends((prev) =>
      prev.map((friend) => ({
        ...friend,
        friend:
          friend.friend?.id === updatedProfile.id
            ? { ...friend.friend, ...updatedProfile }
            : friend.friend,
        user:
          friend.user?.id === updatedProfile.id
            ? { ...friend.user, ...updatedProfile }
            : friend.user,
      }))
    )
    setRequests((prev) =>
      prev.map((request) => ({
        ...request,
        from_user:
          request.from_user?.id === updatedProfile.id
            ? { ...request.from_user, ...updatedProfile }
            : request.from_user,
        to_user:
          request.to_user?.id === updatedProfile.id
            ? { ...request.to_user, ...updatedProfile }
            : request.to_user,
      }))
    )
    setMessages((prev) =>
      prev.map((message) => ({
        ...message,
        sender:
          message.sender?.id === updatedProfile.id
            ? { ...message.sender, ...updatedProfile }
            : message.sender,
        reply_to:
          message.reply_to?.sender?.id === updatedProfile.id
            ? {
                ...message.reply_to,
                sender: { ...message.reply_to.sender, ...updatedProfile },
              }
            : message.reply_to,
      }))
    )
    setProfileUser((prev) => (prev?.id === updatedProfile.id ? { ...prev, ...updatedProfile } : prev))

    if (updatedProfile.id === user?.id) {
      setUser({ ...(user || {}), ...updatedProfile } as any)
    }
  }

  function resolveKnownUser(
    userId?: number | null,
    fallback?: Partial<UserProfile> | null
  ): Partial<UserProfile> | null {
    if (!userId) return fallback || null
    if (user?.id === userId) {
      return user
    }

    const memberUser = members.find((member) => member.user?.id === userId)?.user
    if (memberUser) return memberUser

    const friendUser = friends.find(
      (friend) => friend.friend?.id === userId || friend.user?.id === userId
    )
    if (friendUser?.friend?.id === userId) return friendUser.friend
    if (friendUser?.user?.id === userId) return friendUser.user

    const requestUser = requests.find(
      (request) => request.from_user?.id === userId || request.to_user?.id === userId
    )
    if (requestUser?.from_user?.id === userId) return requestUser.from_user
    if (requestUser?.to_user?.id === userId) return requestUser.to_user

    const directoryUser = users.find((item) => item.id === userId)
    return directoryUser || fallback || null
  }

  function openMessageMenuAt(event: MouseEvent, message: Message) {
    event.preventDefault()
    event.stopPropagation()

    const menuWidth = 220
    const menuHeight = 180
    const padding = 16
    let x = event.clientX
    let y = event.clientY

    if (x + menuWidth > window.innerWidth - padding) {
      x = window.innerWidth - menuWidth - padding
    }
    if (y + menuHeight > window.innerHeight - padding) {
      y = window.innerHeight - menuHeight - padding
    }

    setMessageMenu({ x, y, message })
  }

  async function forwardSelectedMessage(targetRoomId: number) {
    if (!forwardMessage) return

    try {
      const created = await apiJson<Message>(`/api/v1/chat/rooms/${targetRoomId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content: forwardMessage.content,
          reply_to_id: null,
          attachments: (forwardMessage.attachments || []).map((attachment) => ({
            file_url: attachment.file_url,
            file_name: attachment.file_name,
            file_type: attachment.file_type,
            file_size: attachment.file_size,
          })),
        }),
      })

      if (targetRoomId === activeRoom) {
        setMessages((prev) => [...prev, created])
      }

      setRooms((prev) =>
        prev.map((room) =>
          room.id === targetRoomId
            ? {
                ...room,
                last_message:
                  created.content ||
                  created.attachments?.[0]?.file_name ||
                  room.last_message,
                unread: targetRoomId === activeRoom ? 0 : room.unread,
              }
            : room
        )
      )
      setForwardMessage(null)
      setMessageMenu(null)
      await loadRooms()
    } catch (e) {
      console.error(e)
    }
  }

  const sendMessage = async () => {
    if (activeRoom <= 0 || (!draft.trim() && !attachFile)) return

    if (attachFile) {
      try {
        const preparedFile = await optimizeUploadFile(attachFile)
        const fd = new FormData()
        fd.append("file", preparedFile)
        const uploaded = await apiJson<any>("/api/v1/upload/", {
          method: "POST",
          body: fd,
        })
        const created = await apiJson<Message>(`/api/v1/chat/rooms/${activeRoom}/messages`, {
          method: "POST",
          body: JSON.stringify({
            content: draft.trim(),
            reply_to_id: replyTo?.id || null,
            attachments: [uploaded],
          }),
        })
        setMessages((prev) => [...prev, created])
        setRooms((prev) =>
          prev.map((room) =>
            room.id === activeRoom
              ? {
                  ...room,
                  last_message: created.content || uploaded.file_name,
                  unread: 0,
                }
              : room
          )
        )
      } catch (e) {
        console.error(e)
      }
    } else {
      ws?.send(
        JSON.stringify({
          type: "message",
          content: draft.trim(),
          reply_to_id: replyTo?.id || null,
        })
      )
    }
    setDraft("")
    setReplyTo(null)
    setAttachFile(null)
  }

  const handleTyping = () => {
    ws?.send(JSON.stringify({ type: "typing" }))
  }

  const doAccept = async (rid: number) => {
    try {
      await apiVoid(`/api/v1/friends/requests/${rid}/accept`, {
        method: "POST",
      })
      setRequests((p) => p.filter((r) => r.id !== rid))
      loadFriends()
      loadRooms()
    } catch (e) {
      console.error(e)
    }
  }

  const doReject = async (rid: number) => {
    try {
      await apiVoid(`/api/v1/friends/requests/${rid}/reject`, {
        method: "POST",
      })
      setRequests((p) => p.filter((r) => r.id !== rid))
    } catch (e) {
      console.error(e)
    }
  }

  const doDeleteFriend = async (fid: number) => {
    try {
      await apiVoid(`/api/v1/friends/${fid}`, {
        method: "DELETE",
      })
      setFriends((p) => p.filter((f) => f.id !== fid))
    } catch (e) {
      console.error(e)
    }
  }

  const startPrivate = async (uid: number) => {
    try {
      const d = await apiJson<Room>("/api/v1/chat/rooms/private", {
        method: "POST",
        body: JSON.stringify({ user_id: uid }),
      })
      if (d.id) {
        loadRooms()
        navigate(`/chat/${d.id}`)
        setSidebarTab("rooms")
        setMobileSidebar(false)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const doKick = async (uid: number) => {
    try {
      await apiVoid(`/api/v1/chat/rooms/${activeRoom}/members/${uid}`, {
        method: "DELETE",
      })
      loadMembers(activeRoom)
    } catch (e) {
      console.error(e)
    }
  }

  const doAddMember = async (uid: number) => {
    try {
      await apiVoid(`/api/v1/chat/rooms/${activeRoom}/members`, {
        method: "POST",
        body: JSON.stringify({ user_id: uid }),
      })
      loadMembers(activeRoom)
    } catch (e) {
      console.error(e)
    }
  }

  const doToggleMute = async (uid: number, canSendMessages: boolean) => {
    try {
      await apiJson<Member>(`/api/v1/chat/rooms/${activeRoom}/members/${uid}`, {
        method: "PATCH",
        body: JSON.stringify({ can_send_messages: !canSendMessages }),
      })
      loadMembers(activeRoom)
    } catch (e) {
      console.error(e)
    }
  }

  const doToggleAdminRole = async (uid: number, currentRole: Member["role"]) => {
    try {
      await apiJson<Member>(`/api/v1/chat/rooms/${activeRoom}/members/${uid}`, {
        method: "PATCH",
        body: JSON.stringify({ role: currentRole === "admin" ? "member" : "admin" }),
      })
      loadMembers(activeRoom)
    } catch (e) {
      console.error(e)
    }
  }

  const doReaction = async (mid: number, emoji: string) => {
    try {
      await apiVoid(`/api/v1/chat/messages/${mid}/reactions`, {
        method: "POST",
        body: JSON.stringify({ emoji }),
      })
      loadMessages(activeRoom)
    } catch (e) {
      console.error(e)
    }
  }

  const openOwnProfile = async () => {
    try {
      const data = await apiJson<UserProfile>("/api/v1/users/me")
      setProfileUser(data)
      setProfileForm(buildProfileForm(data))
      setProfileFeedback(null)
      setShowProfile(true)
    } catch (e) {
      console.error(e)
    }
  }

  const openUserProfile = async (targetUserId: number, fallback?: Partial<UserProfile>) => {
    try {
      const data = await apiJson<UserProfile>(`/api/v1/users/${targetUserId}`)
      setProfileUser(data)
      setProfileForm(buildProfileForm(data))
      setProfileFeedback(null)
      setShowProfile(true)
    } catch (e) {
      console.error(e)
      if (fallback?.id) {
        setProfileUser(fallback as UserProfile)
        setProfileForm(buildProfileForm(fallback))
        setProfileFeedback(null)
        setShowProfile(true)
      }
    }
  }

  const uploadProfileAvatar = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      setProfileFeedback({ type: "error", message: t("avatarImageOnly") })
      return
    }

    setProfileUploadingAvatar(true)
    setProfileFeedback(null)

    try {
      const optimizedFile = await optimizeUploadFile(file)
      const formData = new FormData()
      formData.append("file", optimizedFile)
      const uploaded = await apiJson<UploadedAttachment>("/api/v1/upload/", {
        method: "POST",
        body: formData,
      })
      setProfileForm((prev) => ({ ...prev, avatar_url: uploaded.file_url }))
      setProfileUser((prev) => (prev ? { ...prev, avatar_url: uploaded.file_url } : prev))
      setProfileFeedback({ type: "success", message: t("avatarReadyToSave") })
    } catch (e) {
      console.error(e)
      setProfileFeedback({
        type: "error",
        message: e instanceof Error ? e.message : t("error"),
      })
    } finally {
      setProfileUploadingAvatar(false)
    }
  }

  const saveProfile = async () => {
    if (!user) return

    setProfileSaving(true)
    setProfileFeedback(null)

    try {
      const updated = await apiJson<UserProfile>("/api/v1/users/me", {
        method: "PUT",
        body: JSON.stringify({
          display_name: profileForm.display_name.trim() || user.username,
          email: profileForm.email.trim() || null,
          date_of_birth: profileForm.date_of_birth || null,
          avatar_url: profileForm.avatar_url || null,
        }),
      })

      applyProfileUpdate(updated)
      setUser(updated as any)
      setProfileUser(updated)
      setProfileForm(buildProfileForm(updated))
      setProfileFeedback({ type: "success", message: t("profileSaved") })
    } catch (e) {
      console.error(e)
      setProfileFeedback({
        type: "error",
        message: e instanceof Error ? e.message : t("error"),
      })
    } finally {
      setProfileSaving(false)
    }
  }

  const doDeleteMessage = async (mid: number) => {
    try {
      await apiVoid(`/api/v1/chat/messages/${mid}`, {
        method: "DELETE",
      })
      setMessages((p) => p.filter((m) => m.id !== mid))
    } catch (e) {
      console.error(e)
    }
  }

  const toggleRoomDraftMember = (
    kind: "group" | "channel",
    userId: number
  ) => {
    const setter = kind === "group" ? setGroupDraft : setChannelDraft
    setter((prev) => ({
      ...prev,
      member_ids: prev.member_ids.includes(userId)
        ? prev.member_ids.filter((id) => id !== userId)
        : [...prev.member_ids, userId],
    }))
  }

  const uploadRoomAvatar = async (
    kind: "group" | "channel" | "edit",
    file: File
  ) => {
    if (!file.type.startsWith("image/")) {
      const message = t("avatarImageOnly")
      if (kind === "group") setGroupFeedback({ type: "error", message })
      if (kind === "channel") setChannelFeedback({ type: "error", message })
      if (kind === "edit") setRoomEditFeedback({ type: "error", message })
      return
    }

    const setUploading =
      kind === "group"
        ? setGroupUploadingAvatar
        : kind === "channel"
          ? setChannelUploadingAvatar
          : setRoomEditUploadingAvatar

    const setFeedback =
      kind === "group"
        ? setGroupFeedback
        : kind === "channel"
          ? setChannelFeedback
          : setRoomEditFeedback

    const setDraft =
      kind === "group"
        ? setGroupDraft
        : kind === "channel"
          ? setChannelDraft
          : setRoomEditDraft

    setUploading(true)
    setFeedback(null)

    try {
      const optimizedFile = await optimizeUploadFile(file)
      const formData = new FormData()
      formData.append("file", optimizedFile)
      const uploaded = await apiJson<UploadedAttachment>("/api/v1/upload/", {
        method: "POST",
        body: formData,
      })
      setDraft((prev) => ({ ...prev, avatar_url: uploaded.file_url }))
      setFeedback({ type: "success", message: t("avatarReadyToSave") })
    } catch (e) {
      console.error(e)
      setFeedback({
        type: "error",
        message: e instanceof Error ? e.message : t("error"),
      })
    } finally {
      setUploading(false)
    }
  }

  const doCreateGroup = async () => {
    if (!groupDraft.name.trim()) return
    if (groupDraft.member_ids.length === 0) {
      setGroupFeedback({ type: "error", message: t("groupNeedsMembers") })
      return
    }

    setGroupSubmitting(true)
    setGroupFeedback(null)

    try {
      const d = await apiJson<Room>("/api/v1/chat/rooms/", {
        method: "POST",
        body: JSON.stringify({
          name: groupDraft.name.trim(),
          room_type: "group",
          description: groupDraft.description.trim(),
          avatar_url: groupDraft.avatar_url || null,
          member_ids: groupDraft.member_ids,
        }),
      })
      if (d.id) {
        loadRooms()
        navigate(`/chat/${d.id}`)
        setShowCreateGroup(false)
        setGroupDraft(createRoomDraft())
        setMobileSidebar(false)
      }
    } catch (e) {
      console.error(e)
      setGroupFeedback({
        type: "error",
        message: e instanceof Error ? e.message : t("error"),
      })
    } finally {
      setGroupSubmitting(false)
    }
  }

  const doCreateChannel = async () => {
    if (!channelDraft.name.trim()) return

    setChannelSubmitting(true)
    setChannelFeedback(null)

    try {
      const d = await apiJson<Room>("/api/v1/chat/rooms/", {
        method: "POST",
        body: JSON.stringify({
          name: channelDraft.name.trim(),
          room_type: "channel",
          description: channelDraft.description.trim(),
          avatar_url: channelDraft.avatar_url || null,
          member_ids: channelDraft.member_ids,
        }),
      })
      if (d.id) {
        loadRooms()
        navigate(`/chat/${d.id}`)
        setShowCreateChannel(false)
        setChannelDraft(createRoomDraft())
        setMobileSidebar(false)
      }
    } catch (e) {
      console.error(e)
      setChannelFeedback({
        type: "error",
        message: e instanceof Error ? e.message : t("error"),
      })
    } finally {
      setChannelSubmitting(false)
    }
  }

  const openCurrentRoomEditor = () => {
    if (!currentRoom) return
    setRoomEditDraft(createRoomDraft(currentRoom))
    setRoomEditFeedback(null)
    setShowRoomEditor(true)
  }

  const saveRoomEditor = async () => {
    if (!currentRoom || !roomEditDraft.name.trim()) return

    setRoomEditSubmitting(true)
    setRoomEditFeedback(null)

    try {
      await apiVoid(`/api/v1/chat/rooms/${currentRoom.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: roomEditDraft.name.trim(),
          description: roomEditDraft.description.trim(),
          avatar_url: roomEditDraft.avatar_url || null,
        }),
      })
      await loadRooms()
      setRoomEditFeedback({ type: "success", message: t("roomSaved") })
      setShowRoomEditor(false)
    } catch (e) {
      console.error(e)
      setRoomEditFeedback({
        type: "error",
        message: e instanceof Error ? e.message : t("error"),
      })
    } finally {
      setRoomEditSubmitting(false)
    }
  }

  const doAddFriend = async () => {
    if (!friendUsername.trim()) return
    try {
      await apiVoid("/api/v1/friends/requests", {
        method: "POST",
        body: JSON.stringify({ username: friendUsername.trim() }),
      })
      setFriendUsername("")
      setShowAddFriend(false)
      loadRequests()
    } catch (e) {
      console.error(e)
    }
  }

  const doLogout = async () => {
    try {
      await apiVoid("/api/v1/auth/logout", {
        method: "POST",
      })
    } catch (e) {
      console.error(e)
    }
    logout()
    navigate("/")
  }

  const filteredRooms = rooms.filter((r) =>
    r.name?.toLowerCase().includes(search.toLowerCase())
  )
  const acceptedFriends = friends
    .filter((friend) => friend.status === "accepted" && friend.friend)
    .map((friend) => friend.friend!)

  const isOwner = currentRoom?.owner_id === user?.id
  const isRoomAdmin = currentMembership?.role === "admin"
  const canAdmin = !!isOwner || !!isRoomAdmin
  const canManageRoom = currentRoom?.type === "channel" ? !!isOwner : canAdmin
  const canManageMembers = currentRoom?.type === "channel" ? !!isOwner : canAdmin
  const canAssignAdmins = currentRoom?.type === "group" && !!isOwner
  const canSendInCurrentRoom =
    currentRoom?.type === "channel"
      ? !!isOwner
      : currentMembership?.can_send_messages !== false

  return (
    <div className="chat-layout">
      {!mobileSidebar && (
        <div className="mobile-overlay" onClick={() => setMobileSidebar(true)} />
      )}

      <aside
        className={`chat-sidebar ${mobileSidebar ? "open" : "closed"}`}
      >
        <div className="sidebar-header">
          <SmallAvatar
            url={user?.avatar_url}
            name={user?.username}
            size={40}
          />
          <div className="sidebar-header-info">
            <div className="sidebar-header-name">
              {user?.display_name || user?.username || "User"}
            </div>
            <div className="sidebar-header-status">
              {connected ? t("online") : t("connecting")}
            </div>
          </div>
          <button
            className="icon-btn"
            onClick={openOwnProfile}
            title={t("profile")}
          >
            <User size={18} />
          </button>
        </div>

        <div className="sidebar-tabs">
          <button
            className={sidebarTab === "rooms" ? "active" : ""}
            onClick={() => setSidebarTab("rooms")}
          >
            <MessageSquare size={18} />
          </button>
          <button
            className={sidebarTab === "friends" ? "active" : ""}
            onClick={() => setSidebarTab("friends")}
          >
            <Users size={18} />
          </button>
          <button
            className={sidebarTab === "settings" ? "active" : ""}
            onClick={() => setSidebarTab("settings")}
          >
            <Settings size={18} />
          </button>
        </div>

        {sidebarTab === "rooms" && (
          <div className="sidebar-content">
            <div className="sidebar-search">
              <Search size={14} />
              <input
                placeholder={t("searchRooms")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="new-chat-dropdown">
              <div
                className="new-chat-trigger"
                onClick={() => setShowNewChat(!showNewChat)}
              >
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <Plus size={16} /> {t("newChat")}
                </span>
                <ChevronDown
                  size={16}
                  style={{
                    transform: showNewChat
                      ? "rotate(180deg)"
                      : "rotate(0)",
                    transition: "transform 0.2s",
                  }}
                />
              </div>
              {showNewChat && (
                <div className="new-chat-menu">
                  <button
                    onClick={() => {
                      setShowAddFriend(true)
                      setShowNewChat(false)
                    }}
                  >
                    <UserPlus size={16} /> {t("addFriend")}
                  </button>
                  <button
                    onClick={() => {
                      setShowCreateGroup(true)
                      setShowNewChat(false)
                    }}
                  >
                    <Users size={16} /> {t("newGroup")}
                  </button>
                  <button
                    onClick={() => {
                      setShowCreateChannel(true)
                      setShowNewChat(false)
                    }}
                  >
                    <Hash size={16} /> {t("newChannel")}
                  </button>
                </div>
              )}
            </div>

            <div className="room-list">
              {safeMap(filteredRooms, (r) => (
                <div
                  key={r.id}
                  className={`room-item ${activeRoom === r.id ? "active" : ""}`}
                  onClick={() => {
                    navigate(`/chat/${r.id}`)
                    setMobileSidebar(false)
                  }}
                >
                  <RoomAvatar url={r.avatar_url} name={r.name} />
                  <div className="room-info">
                    <div className="room-name">{r.name}</div>
                    <div className="room-last">
                      {r.last_message || r.description || t("noMessages")}
                    </div>
                  </div>
                  <div className="room-meta">
                    {r.unread ? (
                      <div className="room-badge">{r.unread}</div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {sidebarTab === "friends" && (
          <div className="sidebar-content">
            {requests.length > 0 && (
              <div className="friend-section">
                <div className="friend-section-title">
                  {t("requests")} ({requests.length})
                </div>
                {safeMap(requests, (req) => (
                  <div key={req.id} className="friend-item">
                    <SmallAvatar
                      url={req.from_user?.avatar_url}
                      name={req.from_user?.username}
                    />
                    <div className="friend-info">
                      <div className="friend-name">
                        {req.from_user?.username}
                      </div>
                    </div>
                    <div className="friend-actions">
                      <button
                        className="icon-btn success"
                        onClick={() => doAccept(req.id)}
                      >
                        <Check size={14} />
                      </button>
                      <button
                        className="icon-btn danger"
                        onClick={() => doReject(req.id)}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="friend-section">
              <div className="friend-section-title">{t("friends")}</div>
              {safeMap(
                friends.filter((f) => f.status === "accepted"),
                (f) => {
                  const person = f.friend || f.user
                  return (
                    <div key={f.id} className="friend-item">
                      <SmallAvatar
                        url={person?.avatar_url}
                        name={person?.username}
                      />
                      <button
                        type="button"
                        className="friend-info friend-profile-button"
                        onClick={() =>
                          person?.id &&
                          openUserProfile(person.id, person)
                        }
                      >
                        <div className="friend-name">
                          {person?.username}{" "}
                          {person?.is_online ? (
                            <span className="online-dot" />
                          ) : null}
                        </div>
                      </button>
                      <div className="friend-actions">
                        <button
                          className="icon-btn"
                          onClick={() => startPrivate(person?.id || 0)}
                          title={t("sendMessage")}
                        >
                          <MessageSquare size={14} />
                        </button>
                        <button
                          className="icon-btn danger"
                          onClick={() => doDeleteFriend(f.id)}
                          title={t("delete")}
                        >
                          <UserX size={14} />
                        </button>
                      </div>
                    </div>
                  )
                }
              )}
            </div>
          </div>
        )}

        {sidebarTab === "settings" && (
          <div className="sidebar-content">
            <div className="settings-block">
              <div className="settings-label">
                <Languages size={14} /> {t("language")}
              </div>
              <LanguageSelector
                value={language}
                onChange={setLanguage}
              />
            </div>
            <div className="settings-block">
              <div className="settings-label">
                {theme === "dark" ? (
                  <Moon size={14} />
                ) : (
                  <Sun size={14} />
                )}{" "}
                {t("theme")}
              </div>
              <button
                className="glass-button small"
                onClick={toggleTheme}
              >
                {theme === "dark" ? t("light") : t("dark")}
              </button>
            </div>
            {user?.is_superuser && (
              <div className="settings-block">
                <button
                  className="glass-button"
                  onClick={() => setShowAdmin(true)}
                >
                  <Shield size={14} /> {t("adminPanel")}
                </button>
              </div>
            )}
          </div>
        )}
      </aside>

      <main className="chat-main">
        {currentRoom ? (
          <>
            <header className="chat-header">
              <button
                className="icon-btn mobile-only"
                onClick={() => setMobileSidebar(true)}
              >
                <ArrowLeft size={18} />
              </button>
              <div className="chat-header-avatar">
                {currentRoom.avatar_url ? (
                  <img src={currentRoom.avatar_url} alt="" />
                ) : (
                  currentRoom.name?.[0]?.toUpperCase() || "?"
                )}
              </div>
              <div className="chat-header-info">
                <div className="chat-header-name">
                  {currentRoom.name}
                </div>
                <div className="chat-header-meta">
                  <span>{t("members")}</span>
                  <span className="count-pill">{roomMemberCount}</span>
                  {typing ? <span className="typing-indicator">{t("typing")}</span> : null}
                </div>
              </div>
              <div className="chat-header-actions">
                <button
                  className="icon-btn"
                  onClick={() => setShowMembers(true)}
                >
                  <Users size={18} />
                </button>
                <button
                  className="icon-btn"
                  onClick={() =>
                    setShowRoomMenu(
                      showRoomMenu === currentRoom.id
                        ? null
                        : currentRoom.id
                    )
                  }
                >
                  <ChevronDown size={18} />
                </button>
              </div>
              {showRoomMenu === currentRoom.id && (
                <div className="dropdown-menu">
                  {currentRoom.type !== "private" && canManageRoom && (
                    <button
                      onClick={() => {
                        openCurrentRoomEditor()
                        setShowRoomMenu(null)
                      }}
                    >
                      <Edit3 size={14} /> {t("editRoom")}
                    </button>
                  )}
                  {(currentRoom.type === "group" ||
                    currentRoom.type === "channel") && canManageMembers && (
                    <button
                      onClick={() => {
                        setShowMembers(true)
                        setShowRoomMenu(null)
                      }}
                    >
                      <UserPlus size={14} /> {t("addMember")}
                    </button>
                  )}
                  {isOwner && (
                    <button
                      className="danger"
                      onClick={async () => {
                        try {
                          await apiVoid(
                            `/api/v1/chat/rooms/${currentRoom.id}`,
                            {
                              method: "DELETE",
                            }
                          )
                          loadRooms()
                          navigate("/chat/0")
                          setShowRoomMenu(null)
                        } catch (e) {
                          console.error(e)
                        }
                      }}
                    >
                      <Trash2 size={14} /> {t("deleteRoom")}
                    </button>
                  )}
                </div>
              )}
            </header>

            <div className="messages-area">
              <div className="messages-column">
                {safeMap(messages, (msg, index) => {
                  const mine = msg.sender_id === user?.id
                  const previousMessage = index > 0 ? messages[index - 1] : null
                  const isGroupStart =
                    !previousMessage || previousMessage.sender_id !== msg.sender_id
                  const attachments = msg.attachments || []
                  const hasOnlyImageAttachment =
                    !msg.content &&
                    attachments.length > 0 &&
                    attachments.every((attachment) =>
                      attachment.file_type?.startsWith("image")
                    )
                  const senderProfile = resolveKnownUser(
                    msg.sender?.id ?? msg.sender_id,
                    msg.sender
                  )
                  const senderName =
                    senderProfile?.display_name ||
                    senderProfile?.username ||
                    msg.sender?.username ||
                    t("unknown")
                  const senderAvatar = senderProfile?.avatar_url || msg.sender?.avatar_url
                  const senderId = senderProfile?.id ?? msg.sender?.id ?? msg.sender_id
                  const isStandaloneMedia = hasOnlyImageAttachment
                  const attachmentElements = safeMap(
                    attachments,
                    (attachment, attachmentIndex) => (
                      <div
                        key={attachment.id || `${msg.id}-${attachmentIndex}`}
                        className="message-attachment"
                      >
                        {attachment.file_type?.startsWith("image") ? (
                          <button
                            type="button"
                            className="message-image-button"
                            onClick={() =>
                              setImagePreview({
                                src: attachment.file_url,
                                title: attachment.file_name || senderName,
                              })
                            }
                          >
                            <img
                              src={attachment.file_url}
                              alt={attachment.file_name || senderName}
                              className="message-image"
                            />
                          </button>
                        ) : attachment.file_type?.startsWith("video") ? (
                          <video
                            src={attachment.file_url}
                            controls
                            className="message-video"
                          />
                        ) : (
                          <div className="message-file-card">
                            <a
                              href={attachment.file_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {attachment.file_name}
                            </a>
                          </div>
                        )}
                      </div>
                    )
                  )
                  return (
                    <div
                      key={msg.id}
                      className={`message-row ${mine ? "mine" : ""} ${
                        isGroupStart ? "group-start" : "continued"
                      }`}
                      onContextMenu={(event) => openMessageMenuAt(event, msg)}
                    >
                      <div className={`message-card ${isGroupStart ? "group-start" : "continued"}`}>
                        {isGroupStart ? (
                          <div className={`message-meta-line ${mine ? "mine" : ""}`}>
                            <button
                              type="button"
                              className={`message-author ${mine ? "mine" : ""}`}
                              onClick={() => {
                                if (!senderId) return
                                if (senderId === user?.id) {
                                  openOwnProfile()
                                  return
                                }
                                openUserProfile(senderId, senderProfile || undefined)
                              }}
                            >
                              <SmallAvatar
                                url={senderAvatar}
                                name={senderName}
                                size={30}
                              />
                              <span className="message-sender">{senderName}</span>
                            </button>
                          </div>
                        ) : null}
                        {isStandaloneMedia ? (
                          <div className={`message-media-stack ${mine ? "mine" : ""}`}>
                            {msg.reply_to ? (
                              <button
                                type="button"
                                className={`message-reply ${mine ? "own-reply" : ""}`}
                                onClick={() => setReplyTo(msg.reply_to || null)}
                              >
                                <Reply size={12} />
                                <span>
                                  {msg.reply_to.sender?.username}:{" "}
                                  {msg.reply_to.content?.slice(0, 48)}
                                </span>
                              </button>
                            ) : null}
                            {attachmentElements}
                          </div>
                        ) : (
                          <div
                            className={`message-bubble ${mine ? "mine" : ""} ${
                              hasOnlyImageAttachment ? "image-only" : ""
                            }`}
                          >
                            {msg.reply_to ? (
                              <button
                                type="button"
                                className={`message-reply ${mine ? "own-reply" : ""}`}
                                onClick={() => setReplyTo(msg.reply_to || null)}
                              >
                                <Reply size={12} />
                                <span>
                                  {msg.reply_to.sender?.username}:{" "}
                                  {msg.reply_to.content?.slice(0, 48)}
                                </span>
                              </button>
                            ) : null}
                            {msg.content ? (
                              <div className="message-content">
                                {msg.content}
                              </div>
                            ) : null}
                            {attachmentElements}
                          </div>
                        )}
                        <div className={`message-foot ${mine ? "mine" : ""}`}>
                        <span className="message-time-pill">
                          {new Date(msg.created_at).toLocaleTimeString(
                            [],
                            {
                              hour: "2-digit",
                              minute: "2-digit",
                            }
                          )}
                        </span>
                        <div className="message-actions">
                          <button
                            className="icon-btn tiny"
                            onClick={() => setReplyTo(msg)}
                          >
                            <Reply size={12} />
                          </button>
                          <button
                            className="icon-btn tiny"
                            onClick={() => doReaction(msg.id, "❤️")}
                          >
                            <Smile size={12} />
                          </button>
                          {mine && (
                            <button
                              className="icon-btn tiny danger"
                              onClick={() =>
                                doDeleteMessage(msg.id)
                              }
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </div>
                      {msg.reactions?.length ? (
                        <div className={`message-reactions-row ${mine ? "mine" : ""}`}>
                          {safeMap(msg.reactions, (re, idx) => (
                            <button
                              key={idx}
                              type="button"
                              className="reaction-chip"
                              onClick={() =>
                                doReaction(msg.id, re.emoji)
                              }
                            >
                              {re.emoji} {re.count}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                )
              })}
                <div ref={messagesEnd} />
              </div>
            </div>

            {replyTo && (
              <div className="reply-bar">
                <div className="reply-bar-inner">
                  <Reply size={14} />
                  <span>
                    {replyTo.sender?.username}:{" "}
                    {replyTo.content?.slice(0, 50)}
                  </span>
                  <button
                    className="icon-btn"
                    onClick={() => setReplyTo(null)}
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            )}

            {attachFile && (
              <div className="reply-bar">
                <div className="reply-bar-inner">
                  <ImageIcon size={14} />
                  <span>{attachFile.name}</span>
                  <button
                    className="icon-btn"
                    onClick={() => setAttachFile(null)}
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            )}

            {canSendInCurrentRoom ? (
              <div className="input-area">
                <div className="input-area-inner">
                  <input
                    type="file"
                    ref={fileInput}
                    accept="image/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.txt,.json"
                    style={{ display: "none" }}
                    onChange={(e) =>
                      e.target.files?.[0] &&
                      setAttachFile(e.target.files[0])
                    }
                  />
                  <button
                    className="icon-btn"
                    onClick={() => fileInput.current?.click()}
                  >
                    <ImageIcon size={18} />
                  </button>
                  <input
                    className="chat-input"
                    placeholder={t("typeMessage")}
                    value={draft}
                    onChange={(e) => {
                      setDraft(e.target.value)
                      handleTyping()
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        sendMessage()
                      }
                    }}
                  />
                  <button
                    className="send-button"
                    onClick={sendMessage}
                  >
                    <Send size={18} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="reply-bar">
                <div className="reply-bar-inner read-only-hint">
                  {currentRoom.type === "channel"
                    ? t("channelReadOnly")
                    : t("mutedHint")}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="empty-chat">
            <MessageSquare size={48} opacity={0.3} />
            <p>{t("selectRoom")}</p>
          </div>
        )}
      </main>

      {showMembers && currentRoom && (
        <div
          className="modal-overlay"
          onClick={() => setShowMembers(false)}
        >
          <div
            className="modal-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <Users size={16} /> {t("members")}
              <span className="count-pill">{roomMemberCount}</span>
              <button
                className="icon-btn"
                onClick={() => setShowMembers(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              {safeMap(members, (m) => (
                <div
                  key={m.user_id}
                  className="member-row"
                  onClick={() => {
                    if (m.user?.id) {
                      openUserProfile(m.user.id, m.user)
                    }
                    setShowMembers(false)
                  }}
                >
                  <SmallAvatar
                    url={m.user?.avatar_url}
                    name={m.user?.username}
                    size={32}
                  />
                  <div className="member-name">
                    {m.user?.username}{" "}
                    {m.role === "owner" ? (
                      <Crown size={12} className="owner-icon" />
                    ) : null}
                    {m.role === "admin" ? (
                      <span className="tag">{t("admin")}</span>
                    ) : null}
                    {m.can_send_messages === false ? (
                      <span className="tag">{t("muted")}</span>
                    ) : null}
                  </div>
                  {canManageMembers && m.user_id !== user?.id && (
                    <div className="friend-actions">
                      {canAssignAdmins && (
                        <button
                          className="icon-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            doToggleAdminRole(m.user_id, m.role)
                          }}
                          title={m.role === "admin" ? t("removeAdmin") : t("makeAdmin")}
                        >
                          <ShieldCheck size={14} />
                        </button>
                      )}
                      {currentRoom.type === "group" && (
                        <button
                          className="icon-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            doToggleMute(m.user_id, m.can_send_messages !== false)
                          }}
                          title={m.can_send_messages === false ? t("unmute") : t("mute")}
                        >
                          <Lock size={14} />
                        </button>
                      )}
                      <button
                        className="icon-btn danger"
                        onClick={(e) => {
                          e.stopPropagation()
                          doKick(m.user_id)
                        }}
                      >
                        <UserX size={14} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {canManageMembers && (
                <div className="add-member-box">
                  <div className="settings-label">
                    {t("addMember")}
                  </div>
                  <select
                    className="add-member-select"
                    onChange={(e) => {
                      if (e.target.value) {
                        doAddMember(Number(e.target.value))
                        e.target.value = ""
                      }
                    }}
                  >
                    <option value="">{t("selectUser")}</option>
                    {safeMap(
                      acceptedFriends.filter(
                        (u) =>
                          !members.some(
                            (m) => m.user_id === u.id
                          )
                      ),
                      (u) => (
                        <option key={u.id} value={u.id}>
                          {u.username}
                        </option>
                      )
                    )}
                  </select>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {showProfile && profileUser && (
        <ProfileModal
          user={profileUser}
          isCurrentUser={isOwnProfile}
          form={profileForm}
          isSaving={profileSaving}
          isUploadingAvatar={profileUploadingAvatar}
          feedback={profileFeedback}
          requests={requests}
          friends={friends.filter((friend) => friend.status === "accepted")}
          onClose={() => setShowProfile(false)}
          onFormChange={(patch) =>
            setProfileForm((prev) => ({ ...prev, ...patch }))
          }
          onSave={saveProfile}
          onLogout={doLogout}
          onAvatarOpen={(src, title) => setImagePreview({ src, title })}
          onAvatarSelected={uploadProfileAvatar}
          onAcceptRequest={doAccept}
          onRejectRequest={doReject}
          onRemoveFriend={doDeleteFriend}
          onStartPrivateChat={startPrivate}
          onOpenUserProfile={(userId) => openUserProfile(userId)}
          onStartChat={
            !isOwnProfile
              ? () => {
                  startPrivate(profileUser.id)
                  setShowProfile(false)
                }
              : undefined
          }
          t={t}
        />
      )}

      {showAdmin && (
        <div
          className="modal-overlay"
          onClick={() => setShowAdmin(false)}
        >
          <div
            className="modal-panel wide"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <Shield size={16} /> {t("adminPanel")}{" "}
              <button
                className="icon-btn"
                onClick={() => setShowAdmin(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <div className="admin-section">
                <div className="settings-label">
                  {t("allUsers")}
                </div>
                <div className="admin-list">
                  {safeMap(users, (u) => (
                    <div key={u.id} className="admin-row">
                      <SmallAvatar
                        url={u.avatar_url}
                        name={u.username}
                        size={28}
                      />
                      <span>{u.username}</span>
                      <span className="tag">
                        {u.is_superuser ? t("admin") : t("user")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="admin-section">
                <div className="settings-label">
                  {t("allRooms")}
                </div>
                <div className="admin-list">
                  {safeMap(rooms, (r) => (
                    <div key={r.id} className="admin-row">
                      <span>{r.name}</span>
                      <span className="tag">{r.type}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {showCreateGroup && (
        <RoomComposerModal
          title={t("newGroup")}
          copy={t("groupChatsDesc")}
          submitLabel={t("create")}
          nameLabel={t("groupName")}
          draft={groupDraft}
          friends={acceptedFriends}
          allowEmptyMembers={false}
          isSubmitting={groupSubmitting}
          isUploadingAvatar={groupUploadingAvatar}
          feedback={groupFeedback}
          onClose={() => {
            setShowCreateGroup(false)
            setGroupFeedback(null)
            setGroupDraft(createRoomDraft())
          }}
          onChange={(patch) =>
            setGroupDraft((prev) => ({ ...prev, ...patch }))
          }
          onToggleMember={(userId) => toggleRoomDraftMember("group", userId)}
          onAvatarSelected={(file) => uploadRoomAvatar("group", file)}
          onSubmit={doCreateGroup}
          t={t}
        />
      )}

      {showCreateChannel && (
        <RoomComposerModal
          title={t("newChannel")}
          copy={t("channelMembersOptional")}
          submitLabel={t("create")}
          nameLabel={t("channelName")}
          draft={channelDraft}
          friends={acceptedFriends}
          allowEmptyMembers
          isSubmitting={channelSubmitting}
          isUploadingAvatar={channelUploadingAvatar}
          feedback={channelFeedback}
          onClose={() => {
            setShowCreateChannel(false)
            setChannelFeedback(null)
            setChannelDraft(createRoomDraft())
          }}
          onChange={(patch) =>
            setChannelDraft((prev) => ({ ...prev, ...patch }))
          }
          onToggleMember={(userId) => toggleRoomDraftMember("channel", userId)}
          onAvatarSelected={(file) => uploadRoomAvatar("channel", file)}
          onSubmit={doCreateChannel}
          t={t}
        />
      )}

      {showRoomEditor && currentRoom && (
        <RoomComposerModal
          title={t("editRoom")}
          copy={t("roomSettingsHint")}
          submitLabel={t("save")}
          nameLabel={currentRoom.type === "channel" ? t("channelName") : t("groupName")}
          draft={roomEditDraft}
          friends={[]}
          allowEmptyMembers
          showMemberPicker={false}
          isSubmitting={roomEditSubmitting}
          isUploadingAvatar={roomEditUploadingAvatar}
          feedback={roomEditFeedback}
          onClose={() => {
            setShowRoomEditor(false)
            setRoomEditFeedback(null)
          }}
          onChange={(patch) =>
            setRoomEditDraft((prev) => ({ ...prev, ...patch }))
          }
          onToggleMember={() => undefined}
          onAvatarSelected={(file) => uploadRoomAvatar("edit", file)}
          onSubmit={saveRoomEditor}
          t={t}
        />
      )}

      {showAddFriend && (
        <div
          className="modal-overlay"
          onClick={() => setShowAddFriend(false)}
        >
          <div
            className="modal-panel wide"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <UserPlus size={16} /> {t("addFriend")}{" "}
              <button
                className="icon-btn"
                onClick={() => setShowAddFriend(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <p className="modal-copy">
                {t("sendRequest")}
              </p>
              <input
                className="glass-input"
                placeholder={t("username")}
                value={friendUsername}
                onChange={(e) =>
                  setFriendUsername(e.target.value)
                }
                onKeyDown={(e) =>
                  e.key === "Enter" && doAddFriend()
                }
              />
              <div className="modal-actions">
                <button
                  className="glass-button"
                  onClick={() => setShowAddFriend(false)}
                >
                  {t("cancel")}
                </button>
                <button
                  className="glass-button primary"
                  onClick={doAddFriend}
                >
                  {t("sendRequest")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {messageMenu && (
        <MessageContextMenu
          x={messageMenu.x}
          y={messageMenu.y}
          showDelete={messageMenu.message.sender_id === user?.id}
          onReply={() => {
            setReplyTo(messageMenu.message)
            setMessageMenu(null)
          }}
          onForward={() => {
            setForwardMessage(messageMenu.message)
            setMessageMenu(null)
          }}
          onReact={(emoji) => {
            doReaction(messageMenu.message.id, emoji)
            setMessageMenu(null)
          }}
          onDelete={() => {
            doDeleteMessage(messageMenu.message.id)
            setMessageMenu(null)
          }}
          t={t}
        />
      )}

      {forwardMessage && (
        <div
          className="modal-overlay"
          onClick={() => setForwardMessage(null)}
        >
          <div
            className="modal-panel wide"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <Reply size={16} /> {t("forward")}
              <button
                className="icon-btn"
                onClick={() => setForwardMessage(null)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <p className="modal-copy">{t("chooseRoomToForward")}</p>
              <div className="profile-list">
                {safeMap(rooms, (room) => (
                  <button
                    key={room.id}
                    type="button"
                    className="profile-list-row profile-list-row-button"
                    onClick={() => forwardSelectedMessage(room.id)}
                  >
                    <div className="profile-list-main">
                      <RoomAvatar url={room.avatar_url} name={room.name} />
                      <div className="profile-list-copy">
                        <strong>{room.name}</strong>
                        <span>{room.type}</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {imagePreview && (
        <ImageViewerModal
          src={imagePreview.src}
          caption={imagePreview.title}
          onClose={() => setImagePreview(null)}
        />
      )}

      {toasts.length > 0 && (
        <div className="toast-stack">
          {toasts.map((toast) => (
            <div key={toast.id} className="toast-card">
              {toast.message}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
