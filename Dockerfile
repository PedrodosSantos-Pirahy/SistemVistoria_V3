# Stage 1: Build do Angular
FROM node:20-alpine AS build

# Diretório de trabalho
WORKDIR /app

# Copia os arquivos de package para instalar dependências
COPY package*.json ./

# Instala dependências do projeto
RUN npm install

# Copia todo o código fonte do projeto
COPY . .

# Faz o build do Angular em modo produção
RUN npm run build --prod

# Stage 2: Servir com Nginx
FROM nginx:alpine

# Copia o build do Angular para a pasta do Nginx
COPY --from=build /app/dist/browser /usr/share/nginx/html

# Expõe a porta padrão do Nginx
EXPOSE 80

# Comando para manter o Nginx rodando
CMD ["nginx", "-g", "daemon off;"]

