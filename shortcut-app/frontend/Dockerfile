FROM node:22-alpine AS build
WORKDIR /app
# 의존성 층을 소스와 분리해 소스만 바뀐 빌드에서 설치를 다시 하지 않는다.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
