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
  const [traces, setTraces] = useState([])
  const [expandedRows, setExpandedRows] = useState(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalTraces, setTotalTraces] = useState(0)
  const [healthStatus, setHealthStatus] = useState(null)

  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`)
      if (!response.ok) throw new Error('Health check failed')
      const data = await response.json()
      setHealthStatus(data)
    } catch (err) {
      setHealthStatus({ status: 'offline', database: 'unknown' })
    }
  }, [])

  const fetchAnalytics = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setIsRefreshing(true)
    else setIsLoading(true)
    
    try {
      const response = await fetch(`${API_BASE_URL}/analytics`)
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }
      const data = await response.json()
      setAnalytics(data)
      setLastUpdated(new Date())
      setError(null)
    } catch (err) {
      console.error('Analytics fetch error:', err)
      setError(err.message.includes('fetch') || err.message.includes('Failed')
        ? 'Unable to connect to server.'
        : err.message || 'Failed to load analytics.')
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
      console.log('Fetching traces from:', url)
      const response = await fetch(url)
      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }
      const data = await response.json()
      console.log('Traces response:', data)
      console.log('Setting traces:', data.traces)
      setTraces(data.traces || [])
      setTotalPages(data.total_pages || 1)
      setTotalTraces(data.total || 0)
    } catch (err) {
      console.error('Traces fetch error:', err)
      setTraces([])
    }
  }, [])

  const refreshData = useCallback(() => {
    fetchAnalytics(true)
    fetchTraces(categoryFilter, currentPage)
    fetchHealth()
  }, [fetchAnalytics, fetchTraces, fetchHealth, categoryFilter, currentPage])

  useEffect(() => {
    fetchAnalytics()
    fetchHealth()
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

  if (isLoading) {
    return (
      <div className="dashboard-container">
        <div className="dashboard-header"><h1>SupportLens Dashboard</h1><p>Analytics Overview</p></div>
        <div className="dashboard-loading"><div className="loading-spinner"></div><p>Loading...</p></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard-container">
        <div className="dashboard-header"><h1>SupportLens Dashboard</h1><p>Analytics Overview</p></div>
        <div className="dashboard-error"><p>{error}</p><button onClick={() => fetchAnalytics()} className="retry-button">Retry</button></div>
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
          <div className="metric-card"><div className="metric-label">Total Traces</div><div className="metric-value">{analytics?.total_count ?? 0}</div></div>
          <div className="metric-card"><div className="metric-label">Avg Response Time</div><div className="metric-value">{analytics?.average_response_time_ms?.toFixed(1) ?? 0}<span className="metric-unit">ms</span></div></div>
          <div className="metric-card health-card">
            <div className="metric-label">Backend Status</div>
            <div className="health-status">
              <span className={`health-indicator ${healthStatus?.status === 'healthy' ? 'healthy' : healthStatus?.status === 'degraded' ? 'degraded' : 'offline'}`}></span>
              <span className="health-text">{healthStatus?.status === 'healthy' ? 'Healthy' : healthStatus?.status === 'degraded' ? 'Degraded' : 'Offline'}</span>
            </div>
            <div className="health-details">
              <span className="health-detail-label">Database:</span>
              <span className={`health-detail-value ${healthStatus?.database === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                {healthStatus?.database === 'healthy' ? 'Connected' : healthStatus?.database || 'Unknown'}
              </span>
            </div>
          </div>
        </div>

        <div className="category-section">
          <h2>Category Breakdown</h2>
          {analytics?.category_breakdown?.length > 0 ? (
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
          
          {traces.length > 0 ? (
            <>
              <div className="trace-table-container">
                <table className="trace-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th className="hide-mobile">User Message</th>
                      <th className="hide-mobile">Bot Response</th>
                      <th>Category</th>
                      <th className="hide-tablet">Response Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {traces.map((trace) => (
                      <React.Fragment key={trace.id}>
                        <tr className={`trace-row ${expandedRows.has(trace.id) ? 'expanded' : ''}`} onClick={() => toggleRowExpansion(trace.id)}>
                          <td className="trace-timestamp">{formatTimestamp(trace.timestamp)}</td>
                          <td className="trace-message hide-mobile">{truncateText(trace.user_message)}</td>
                          <td className="trace-message hide-mobile">{truncateText(trace.bot_response)}</td>
                          <td><span className="trace-category-badge" style={{ backgroundColor: CATEGORY_COLORS[trace.category] }}>{formatCategoryName(trace.category)}</span></td>
                          <td className="trace-response-time hide-tablet">{trace.response_time_ms} ms</td>
                        </tr>
                        {expandedRows.has(trace.id) && (
                          <tr className="trace-expanded-row">
                            <td colSpan="5">
                              <div className="trace-expanded-content">
                                <div className="trace-full-message"><strong>User Message:</strong><p>{trace.user_message}</p></div>
                                <div className="trace-full-message"><strong>Bot Response:</strong><p>{trace.bot_response}</p></div>
                                <div className="trace-meta"><span>Response Time: {trace.response_time_ms}ms</span></div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
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
