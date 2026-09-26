# frontend/Dockerfile
FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the Vite application (Outputs to /app/dist)
RUN npm run build

# Install a simple static file server
RUN npm install -g serve

EXPOSE 3000

# Serve the 'dist' directory on port 3000
CMD ["serve", "-s", "dist", "-l", "3000"]