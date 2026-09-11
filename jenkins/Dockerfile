# Контроллер Jenkins с клиентом Docker внутри (паттерн Docker-outside-of-Docker).
# Демон не устанавливается: используется хостовый через проброшенный сокет.
FROM jenkins/jenkins:lts-jdk21

USER root

# Подключаем официальный репозиторий Docker и ставим только CLI и buildx.
# curl и jq нужны пайплайну: он проверяет ими HTTP-ответы и разбирает JSON.
RUN apt-get update && apt-get install -y --no-install-recommends \
        lsb-release ca-certificates curl gnupg jq && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list && \
    apt-get update && apt-get install -y --no-install-recommends \
        docker-ce-cli docker-buildx-plugin && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER jenkins
RUN jenkins-plugin-cli --plugins "docker-workflow"

# Контейнер работает от root: Docker Desktop предъявляет сокет как root:root,
# группы docker внутри контейнера не существует, поэтому group_add бесполезен.
USER root
