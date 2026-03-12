import React, { useState, useEffect, useCallback } from 'react'
import './Dashboard.css'

const API_BASE_URL = 'http://localhost:8000'

const CATEGORY_COLORS = {
  Billing: '#3B82F6',
  Refund: '#EF4444',
  Account_Access: '#F59E0B',
  Cancellation: '#8B5CF6',
  General_Inquiry: '#10B981'
}

const CATEGORIES = ['Billing', 'Refund', 'Account_Access', 'Cancellation', 'General_Inquiry']
const AUTO_REFRESH_INTERVAL = 30000
const PAGE_SIZE = 10

function Dashboard({ onNavigateToChat }) {
  const [analytics, setAnalytics] = useState(null)
  const [analyticsError, setAnalyticsError] = useState(null)
  const [traces, setTraces] = useState([])
  const [tracesError, setTracesError] = useState(null)
  const [expandedRows, setExpandedRows] = useState(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [categoryFilter, setCategoryFilter] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalTraces, setTotalTraces] = useState(0)
  const [healthStatus, setHealthStatus] = useState(null)
  const [showLogs, setShowLogs] = useState(false)
  const [logs, setLogs] = useState([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [logLevelFilter, setLogLevelFilter] = useState('')

  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`)
      if (!response.ok) throw new Error('Health check failed')
      const data = await response.json()
      // Normalize the health response for display
      setHealthStatus({
        status: data.status,
        can_serve_traffic: data.can_serve_traffic,
        database: data.dependencies?.database?.status || 'unknown',
        database_latency: data.dependencies?.database?.latency_ms,
        llm: data.dependencies?.llm?.status || 'unknown',
        llm_message: data.dependencies?.llm?.message,
        uptime: data.uptime_seconds,
        version: data.version
      })
    } catch (err) {
      setHealthStatus({ 
        status: 'offline', 
        can_serve_traffic: false,
        database: 'unknown',
        llm: 'unknown'
      })
    }
  }, [])

  const fetchLogs = useCallback(async (level = '') => {
    setLogsLoading(true)
    try {
      let url = `${API_BASE_URL}/logs?limit=100`
      if (level) url += `&level=${level}`
      const response = await fetch(url)
      if (!response.ok) throw new Error('Failed to fetch logs')
      const data = await response.json()
      setLogs(data.logs || [])
    } catch (err) {
      console.error('Logs fetch error:', err)
      setLogs([])
    } finally {
      setLogsLoading(false)
    }
  }, [])

  const fetchAnalytics = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setIsRefreshing(true)
    
    try {
      const response = await fetch(`${API_BASE_URL}/analytics`)
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }
      const data = await response.json()
      setAnalytics(data)
      setLastUpdated(new Date())
      setAnalyticsError(null)
    } catch (err) {
      console.error('Analytics fetch error:', err)
      setAnalyticsError(err.message.includes('fetch') || err.message.includes('Failed')
        ? 'Unable to fetch analytics data'
        : err.message || 'Failed to load analytics')
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [])

  const fetchTraces = useCallback(async (category = '', page = 1) => {
    try {
      let url = `${API_BASE_URL}/traces?page=${page}&page_size=${PAGE_SIZE}`
      if (category) {
        url += `&category=${encodeURIComponent(category)}`
      }
      const response = await fetch(url)
      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }
      const data = await response.json()
      setTraces(data.traces || [])
      setTotalPages(data.total_pages || 1)
      setTotalTraces(data.total || 0)
      setTracesError(null)
    } catch (err) {
      console.error('Traces fetch error:', err)
      setTraces([])
      setTracesError('Unable to fetch traces from database')
    }
  }, [])

  const refreshData = useCallback(() => {
    fetchAnalytics(true)
    fetchTraces(categoryFilter, currentPage)
    fetchHealth()
  }, [fetchAnalytics, fetchTraces, fetchHealth, categoryFilter, currentPage])

  useEffect(() => {
    // Fetch health first, then other data
    fetchHealth()
    fetchAnalytics()
  }, [fetchAnalytics, fetchHealth])

  useEffect(() => {
    fetchTraces(categoryFilter, currentPage)
  }, [categoryFilter, currentPage, fetchTraces])

  useEffect(() => {
    const interval = setInterval(refreshData, AUTO_REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [refreshData])

  const handleCategoryFilterChange = (e) => {
    setCategoryFilter(e.target.value)
    setCurrentPage(1)
  }

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage)
      setExpandedRows(new Set())
    }
  }

  const truncateText = (text, maxLength = 50) => {
    if (!text || text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  const formatTimestamp = (timestamp) => new Date(timestamp).toLocaleString()

  const toggleRowExpansion = (traceId) => {
    setExpandedRows(prev => {
      const newSet = new Set(prev)
      if (newSet.has(traceId)) newSet.delete(traceId)
      else newSet.add(traceId)
      return newSet
    })
  }

  const formatCategoryName = (category) => category.replace(/_/g, ' ')
  const formatLastUpdated = () => lastUpdated?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) || ''
  
  const formatUptime = (seconds) => {
    if (!seconds && seconds !== 0) return 'N/A'
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    
    if (days > 0) return `${days}d ${hours}h ${mins}m`
    if (hours > 0) return `${hours}h ${mins}m ${secs}s`
    if (mins > 0) return `${mins}m ${secs}s`
    return `${secs}s`
  }

  const getLogLevelColor = (level) => {
    switch (level) {
      case 'ERROR': return '#EF4444'
      case 'WARNING': return '#F59E0B'
      case 'INFO': return '#10B981'
      case 'DEBUG': return '#6B7280'
      default: return '#6B7280'
    }
  }

  const handleShowLogs = () => {
    setShowLogs(true)
    fetchLogs(logLevelFilter)
  }

  const handleLogLevelChange = (e) => {
    const level = e.target.value
    setLogLevelFilter(level)
    fetchLogs(level)
  }
  
  // Group traces by session_id for visual indication
  const getSessionColor = (sessionId) => {
    if (!sessionId) return null
    // Generate a consistent color based on session_id
    let hash = 0
    for (let i = 0; i < sessionId.length; i++) {
      hash = sessionId.charCodeAt(i) + ((hash << 5) - hash)
    }
    const hue = Math.abs(hash % 360)
    return `hsl(${hue}, 70%, 85%)`
  }
  
  // Get short session ID for display
  const getShortSessionId = (sessionId) => {
    if (!sessionId) return null
    return sessionId.substring(0, 8)
  }

  // Group traces by session_id
  const groupTracesBySession = (traces) => {
    const groups = []
    const sessionMap = new Map()
    
    traces.forEach(trace => {
      const sessionId = trace.session_id || trace.id // Use trace id as fallback for ungrouped
      if (!trace.session_id) {
        // No session - treat as individual
        groups.push({ sessionId: null, traces: [trace] })
      } else if (sessionMap.has(sessionId)) {
        sessionMap.get(sessionId).traces.push(trace)
      } else {
        const group = { sessionId, traces: [trace] }
        sessionMap.set(sessionId, group)
        groups.push(group)
      }
    })
    
    // Sort traces within each group by timestamp (oldest first for conversation flow)
    groups.forEach(group => {
      if (group.traces.length > 1) {
        group.traces.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
      }
    })
    
    return groups
  }

  const [expandedSessions, setExpandedSessions] = useState(new Set())

  const toggleSessionExpansion = (sessionId) => {
    setExpandedSessions(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sessionId)) newSet.delete(sessionId)
      else newSet.add(sessionId)
      return newSet
    })
  }

  if (isLoading) {
    return (
      <div className="dashboard-container">
        <div className="dashboard-header"><h1>SupportLens Dashboard</h1><p>Analytics Overview</p></div>
        <div className="dashboard-loading"><div className="loading-spinner"></div><p>Loading...</p></div>
      </div>
    )
  }

  const renderPagination = () => {
    if (totalPages <= 1) return null
    const pages = []
    let start = Math.max(1, currentPage - 2)
    let end = Math.min(totalPages, start + 4)
    if (end - start < 4) start = Math.max(1, end - 4)
    for (let i = start; i <= end; i++) pages.push(i)

    return (
      <div className="pagination">
        <button className="pagination-btn" onClick={() => handlePageChange(1)} disabled={currentPage === 1}>««</button>
        <button className="pagination-btn" onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1}>«</button>
        {start > 1 && <span className="pagination-ellipsis">...</span>}
        {pages.map(p => (
          <button key={p} className={`pagination-btn ${p === currentPage ? 'active' : ''}`} onClick={() => handlePageChange(p)}>{p}</button>
        ))}
        {end < totalPages && <span className="pagination-ellipsis">...</span>}
        <button className="pagination-btn" onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages}>»</button>
        <button className="pagination-btn" onClick={() => handlePageChange(totalPages)} disabled={currentPage === totalPages}>»»</button>
        <span className="pagination-info">Page {currentPage} of {totalPages} ({totalTraces} total)</span>
      </div>
    )
  }

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <div className="dashboard-header-left"><h1>SupportLens Dashboard</h1><p>Analytics Overview</p></div>
        <div className="dashboard-header-right">
          <div className="last-updated">
            {lastUpdated && <><span className="update-label">Updated</span><span className="update-time">{formatLastUpdated()}</span></>}
            <button className="refresh-btn" onClick={refreshData} disabled={isRefreshing} aria-label="Refresh">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={isRefreshing ? 'spinning' : ''}>
                <path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
            </button>
          </div>
          <button className="back-to-chat-btn" onClick={onNavigateToChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            <span className="btn-text">Back to Chat</span>
          </button>
        </div>
      </div>

      <div className="dashboard-content">
        <div className="metrics-row">
          <div className="metric-card">
            <div className="metric-label">Total Traces</div>
            <div className="metric-value">{analyticsError ? '—' : (analytics?.total_count ?? 0)}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Avg Response Time</div>
            <div className="metric-value">
              {analyticsError ? '—' : (analytics?.average_response_time_ms?.toFixed(1) ?? 0)}
              {!analyticsError && <span className="metric-unit">ms</span>}
            </div>
          </div>
          <div className="metric-card health-card">
            <div className="metric-label">System Status</div>
            <div className="health-status">
              <span className={`health-indicator ${healthStatus?.status === 'healthy' ? 'healthy' : healthStatus?.status === 'degraded' ? 'degraded' : 'offline'}`}></span>
              <span className="health-text">
                {healthStatus?.status === 'healthy' ? 'All Systems Operational' : 
                 healthStatus?.status === 'degraded' ? 'Degraded Mode' : 'Offline'}
              </span>
            </div>
            <div className="health-details">
              <div className="health-detail-row">
                <span className="health-detail-label">Database:</span>
                <span className={`health-detail-value ${healthStatus?.database === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                  {healthStatus?.database === 'healthy' ? 
                    `Connected${healthStatus?.database_latency ? ` (${healthStatus.database_latency.toFixed(0)}ms)` : ''}` : 
                    'Disconnected'}
                </span>
              </div>
              <div className="health-detail-row">
                <span className="health-detail-label">LLM:</span>
                <span className={`health-detail-value ${healthStatus?.llm === 'healthy' ? 'healthy' : healthStatus?.llm === 'degraded' ? 'degraded' : 'unhealthy'}`}>
                  {healthStatus?.llm === 'healthy' ? 'Configured' : 
                   healthStatus?.llm === 'degraded' ? 'Not Configured' : 'Unknown'}
                </span>
              </div>
              <div className="health-detail-row">
                <span className="health-detail-label">Uptime:</span>
                <span className="health-detail-value healthy">{formatUptime(healthStatus?.uptime)}</span>
              </div>
              <div className="health-detail-row">
                <span className="health-detail-label">Version:</span>
                <span className="health-detail-value">{healthStatus?.version || 'N/A'}</span>
              </div>
            </div>
            <button className="logs-btn" onClick={handleShowLogs}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
              View Logs
            </button>
          </div>
        </div>

        {showLogs && (
          <div className="logs-section">
            <div className="logs-header">
              <h2>Application Logs</h2>
              <div className="logs-controls">
                <select value={logLevelFilter} onChange={handleLogLevelChange} className="log-level-select">
                  <option value="">All Levels</option>
                  <option value="ERROR">Error</option>
                  <option value="WARNING">Warning</option>
                  <option value="INFO">Info</option>
                </select>
                <button className="logs-refresh-btn" onClick={() => fetchLogs(logLevelFilter)} disabled={logsLoading}>
                  {logsLoading ? 'Loading...' : 'Refresh'}
                </button>
                <button className="logs-close-btn" onClick={() => setShowLogs(false)}>×</button>
              </div>
            </div>
            <div className="logs-container">
              {logs.length > 0 ? (
                logs.map((log, idx) => (
                  <div key={idx} className="log-entry">
                    <span className="log-timestamp">{new Date(log.timestamp).toLocaleTimeString()}</span>
                    <span className="log-level" style={{ color: getLogLevelColor(log.level) }}>{log.level}</span>
                    <span className="log-logger">{log.logger}</span>
                    <span className="log-message">{log.message}</span>
                    {log.request_id && <span className="log-request-id">[{log.request_id}]</span>}
                    {log.type && <span className="log-type">{log.type}</span>}
                    {log.path && <span className="log-path">{log.method} {log.path}</span>}
                    {log.status_code && <span className={`log-status ${log.status_code >= 400 ? 'error' : 'success'}`}>{log.status_code}</span>}
                    {log.duration_ms && <span className="log-duration">{log.duration_ms.toFixed(0)}ms</span>}
                  </div>
                ))
              ) : (
                <p className="no-logs">No logs available</p>
              )}
            </div>
          </div>
        )}

        <div className="category-section">
          <h2>Category Breakdown</h2>
          {analyticsError ? (
            <div className="section-error">
              <p>{analyticsError}</p>
              <button onClick={() => fetchAnalytics()} className="retry-btn-small">Retry</button>
            </div>
          ) : analytics?.category_breakdown?.length > 0 ? (
            <div className="category-list">
              {analytics.category_breakdown.map((item) => (
                <div key={item.category} className="category-item">
                  <div className="category-info"><span className="category-color" style={{ backgroundColor: CATEGORY_COLORS[item.category] }}></span><span className="category-name">{formatCategoryName(item.category)}</span></div>
                  <div className="category-stats"><span className="category-count">{item.count}</span><span className="category-percentage">({item.percentage.toFixed(1)}%)</span></div>
                  <div className="category-bar-container"><div className="category-bar" style={{ width: `${item.percentage}%`, backgroundColor: CATEGORY_COLORS[item.category] }}></div></div>
                </div>
              ))}
            </div>
          ) : <p className="no-data">No category data available</p>}
        </div>

        <div className="trace-section">
          <div className="trace-section-header">
            <h2>Trace History</h2>
            <div className="category-filter">
              <label htmlFor="category-filter">Filter:</label>
              <select id="category-filter" value={categoryFilter} onChange={handleCategoryFilterChange} className="category-filter-select">
                <option value="">All Categories</option>
                {CATEGORIES.map((cat) => <option key={cat} value={cat}>{formatCategoryName(cat)}</option>)}
              </select>
            </div>
          </div>
          
          {tracesError ? (
            <div className="section-error">
              <p>{tracesError}</p>
              <button onClick={() => fetchTraces(categoryFilter, currentPage)} className="retry-btn-small">Retry</button>
            </div>
          ) : traces.length > 0 ? (
            <>
              <div className="trace-list">
                {groupTracesBySession(traces).map((group) => {
                  const sessionColor = getSessionColor(group.sessionId)
                  const shortSession = getShortSessionId(group.sessionId)
                  const isExpanded = expandedSessions.has(group.sessionId || group.traces[0].id)
                  const groupKey = group.sessionId || group.traces[0].id
                  const firstTrace = group.traces[0]
                  
                  return (
                    <div key={groupKey} className={`trace-card ${isExpanded ? 'expanded' : ''}`} style={sessionColor ? { borderLeftColor: sessionColor } : {}}>
                      <div className="trace-card-header" onClick={() => toggleSessionExpansion(groupKey)}>
                        <div className="trace-card-info">
                          <div className="trace-card-top">
                            {shortSession ? (
                              <span className="session-id" style={{ backgroundColor: sessionColor }} title={group.sessionId}>
                                {shortSession}
                              </span>
                            ) : (
                              <span className="session-id no-session">No Session</span>
                            )}
                            {group.traces.length > 1 && (
                              <span className="msg-count">{group.traces.length} msgs</span>
                            )}
                          </div>
                          <div className="trace-card-preview">
                            <span className="preview-msg">{truncateText(firstTrace.user_message, 100)}</span>
                          </div>
                          <div className="trace-card-meta">
                            <span className="trace-time">{formatTimestamp(firstTrace.timestamp)}</span>
                            <span className="trace-response-time">{firstTrace.response_time_ms}ms</span>
                          </div>
                        </div>
                        <div className="trace-card-right">
                          <span className="trace-category-badge" style={{ backgroundColor: CATEGORY_COLORS[firstTrace.category] }}>
                            {formatCategoryName(firstTrace.category)}
                          </span>
                          <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                        </div>
                      </div>
                      
                      {isExpanded && (
                        <div className="trace-card-messages">
                          {group.traces.map((trace, idx) => (
                            <div key={trace.id} className="chat-message-pair">
                              <div className="chat-msg-header">
                                <span className="chat-msg-num">#{idx + 1}</span>
                                <span className="chat-msg-time">{formatTimestamp(trace.timestamp)}</span>
                                <span className="trace-category-badge small" style={{ backgroundColor: CATEGORY_COLORS[trace.category] }}>
                                  {formatCategoryName(trace.category)}
                                </span>
                                <span className="chat-msg-duration">{trace.response_time_ms}ms</span>
                              </div>
                              <div className="chat-bubble user-bubble">
                                <span className="bubble-label">User</span>
                                <p>{trace.user_message}</p>
                              </div>
                              <div className="chat-bubble bot-bubble">
                                <span className="bubble-label">Bot</span>
                                <p>{trace.bot_response}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
              {renderPagination()}
            </>
          ) : <p className="no-data">No traces available</p>}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
