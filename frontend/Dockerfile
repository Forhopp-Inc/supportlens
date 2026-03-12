# SupportLens Frontend Dockerfile
# Multi-stage build for production-optimized image

# ============================================================================
# Build stage - compile React application
# ============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first for better layer caching
COPY package*.json ./

# Install dependencies (ci for reproducible builds)
RUN npm ci --silent

# Copy source code (excluding node_modules via .dockerignore)
COPY index.html vite.config.js ./
COPY src/ ./src/

# Build production bundle
RUN npm run build

# ============================================================================
# Production stage - serve with nginx
# ============================================================================
FROM nginx:alpine AS production

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/health || exit 1

# Run nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
