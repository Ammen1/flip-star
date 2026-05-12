# Multi-stage Dockerfile for React Frontend with Nginx
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Fix permissions for node_modules executables
RUN chmod -R +x node_modules/.bin/

# Build the application
RUN npm run build

# Production stage with Nginx
FROM nginx:alpine

# Remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config to conf.d instead of main config
COPY nginx.conf /etc/nginx/conf.d/custom.conf

# Copy build artifacts from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
