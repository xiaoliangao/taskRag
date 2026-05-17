FROM node:20-slim

ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com

WORKDIR /app

COPY package.json /app/package.json
RUN npm install

COPY . /app

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
