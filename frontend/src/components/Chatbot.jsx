import { useState, useRef, useEffect } from 'react'
import './Chatbot.css'

const API_BASE_URL = 'http://localhost:8000'

// Generate a unique session ID
const generateSessionId = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

function Chatbot({ onNavigateToDashboard }) {
  const [messages, setMessages] = useState([
    { 
      id: 1, 
      content: "Hi there! 👋 I'm here to help with your questions. What can I assist you with today?", 
      isUser: false,
      time: new Date()
    }
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [systemStatus, setSystemStatus] = useState({ status: 'healthy', dbAvailable: true })
  const [sessionId] = useState(() => generateSessionId()) // Generate once per chat session
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Check system health on mount and periodically
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/health`)
        if (response.ok) {
          const data = await response.json()
          setSystemStatus({
            status: data.status,
            dbAvailable: data.dependencies?.database?.status === 'healthy',
            llmAvailable: data.dependencies?.llm?.status === 'healthy'
          })
        }
      } catch {
        setSystemStatus({ status: 'offline', dbAvailable: false, llmAvailable: false })
      }
    }
    
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error])

  const formatTime = (date) => {
    return new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const message = input.trim()
    if (!message || isLoading) return

    const userMessage = { id: Date.now(), content: message, isUser: true, time: new Date() }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    setIsLoading(true)
    setError(null)

    try {
      // Build conversation history for context (exclude the initial greeting and current message)
      const history = updatedMessages
        .slice(1, -1) // Skip initial bot greeting and current user message
        .map(msg => ({
          role: msg.isUser ? 'user' : 'assistant',
          content: msg.content
        }))

      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId, history })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }

      const data = await response.json()
      
      // Update system status based on trace_stored flag
      if (data.trace_stored === false) {
        setSystemStatus(prev => ({ ...prev, dbAvailable: false }))
      }
      
      setMessages(prev => [...prev, { 
        id: Date.now(), 
        content: data.response, 
        isUser: false,
        time: new Date(),
        notStored: data.trace_stored === false
      }])
    } catch (err) {
      console.error('Chat error:', err)
      const errorMessage = err.message.includes('fetch') || err.message.includes('Failed')
        ? 'Unable to connect to server. Please ensure the backend is running.'
        : err.message || 'Something went wrong. Please try again.'
      setError(errorMessage)
      setMessages(prev => [...prev, { 
        id: Date.now(), 
        content: 'Sorry, I encountered an error. Please try again.', 
        isUser: false,
        time: new Date()
      }])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-avatar">S</div>
          <div className="chat-header-info">
            <h1>SupportLens</h1>
            <p><span className={`status-dot ${systemStatus.status !== 'healthy' ? 'degraded' : ''}`}></span>
              {systemStatus.status === 'healthy' ? 'Online' : 
               systemStatus.status === 'degraded' ? 'Limited Mode' : 'Offline'}
            </p>
          </div>
        </div>
        <button className="dashboard-btn" onClick={onNavigateToDashboard} aria-label="Open Dashboard">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
          Dashboard
        </button>
      </div>

      {!systemStatus.dbAvailable && systemStatus.status !== 'offline' && (
        <div className="degraded-banner" role="alert">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <span>Limited Mode: Chat is available but conversations are not being saved.</span>
        </div>
      )}

      <div className="chat-messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.isUser ? 'user-message' : 'bot-message'}`}>
            <div className="message-content">{msg.content}</div>
            <div className="message-time">{formatTime(msg.time)}</div>
          </div>
        ))}
        {isLoading && (
          <div className="message bot-message">
            <div className="loading-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <form onSubmit={handleSubmit} className="chat-form">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="chat-input"
            placeholder="Type your message..."
            disabled={isLoading}
            aria-label="Type your message"
            autoComplete="off"
          />
          <button type="submit" className="send-button" disabled={isLoading || !input.trim()} aria-label="Send">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </form>
      </div>

      {error && <div className="error-banner" role="alert">{error}</div>}
      
      <div className="chat-footer">
        Powered by <a href="#">SupportLens</a>
      </div>
    </div>
  )
}

export default Chatbot
