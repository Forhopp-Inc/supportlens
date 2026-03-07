import { useState, useRef, useEffect } from 'react'
import './Chatbot.css'

const API_BASE_URL = 'http://localhost:8000'

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
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

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
        body: JSON.stringify({ message, history })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }

      const data = await response.json()
      setMessages(prev => [...prev, { 
        id: Date.now(), 
        content: data.response, 
        isUser: false,
        time: new Date()
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
            <p><span className="status-dot"></span>Online</p>
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
