# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

# 安装依赖（利用 Docker 层缓存）
COPY package*.json ./
RUN npm ci

# 构建生产产物
COPY . .
RUN npm run build

# ---- Runtime stage ----
FROM nginx:alpine AS runtime

# 拷贝前端构建产物到 nginx 静态目录
COPY --from=build /app/dist /usr/share/nginx/html

# 写入 SPA 所需的 nginx 配置：history 模式回退到 index.html
RUN printf 'server {\n\
  listen 80;\n\
  server_name _;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
