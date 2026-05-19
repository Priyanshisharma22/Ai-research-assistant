import { useState } from "react"
import Sidebar from "./components/Sidebar"
import ChatWindow from "./components/ChatWindow"
import ProfilePage from "./components/ProfilePage"

export default function App() {
  const [showProfile, setShowProfile] = useState(false)

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, sans-serif" }}>
      <Sidebar onOpenProfile={() => setShowProfile(true)} />
      {showProfile ? (
        <ProfilePage onBack={() => setShowProfile(false)} />
      ) : (
        <ChatWindow />
      )}
    </div>
  )
}