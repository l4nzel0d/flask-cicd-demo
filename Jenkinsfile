// Практическая работа №4 — CI/CD-конвейер для Flask-приложения.
// Декларативный пайплайн: сборка образа, тесты, smoke-проверка, публикация
// в реестр, развёртывание в staging, ручное одобрение и выкат в production.

pipeline {

    agent any

    options {
        // Отметки времени в консоли: видно длительность каждой стадии.
        timestamps()
        // Обязательно: контейнеры и порты именованы жёстко, две параллельные
        // сборки дрались бы за одно имя и один порт.
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 1, unit: 'HOURS')
    }

    environment {
        // Два адреса одного реестра — они не взаимозаменяемы:
        //   REGISTRY     разрешает ДЕМОН хоста (через опубликованный порт);
        //   REGISTRY_API разрешает КОНТЕЙНЕР Jenkins (через DNS сети cicd).
        REGISTRY     = 'localhost:5000'
        REGISTRY_API = 'http://pract4-registry:5000'

        IMAGE_NAME   = 'flask-cicd-demo'
        IMAGE_TAG    = "${env.BUILD_NUMBER}"
        IMAGE        = "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        IMAGE_LATEST = "${REGISTRY}/${IMAGE_NAME}:latest"
        TEST_IMAGE   = "${IMAGE_NAME}-test:${IMAGE_TAG}"
        APP_VERSION  = "1.0.${env.BUILD_NUMBER}"

        CICD_NET     = 'pract4-cicd'
        STAGING_NET  = 'pract4-staging'
        PROD_NET     = 'pract4-prod'

        STAGING_NAME = 'flask-staging'
        PROD_NAME    = 'flask-prod'
        SMOKE_NAME   = "pract4-smoke-${env.BUILD_NUMBER}"
        TEST_CONT    = "pract4-test-${env.BUILD_NUMBER}"

        APP_PORT     = '8000'
        STAGING_PORT = '8081'
        PROD_PORT    = '8082'
    }

    triggers {
        // Опрос репозитория вместо webhook: контроллер живёт на localhost
        // и недоступен из интернета, поэтому GitHub до него не достучится.
        pollSCM('H/5 * * * *')
    }

    stages {

        stage('1. Checkout & Prepare') {
            steps {
                checkout scm
                script {
                    env.GIT_SHA = sh(
                        script: 'git rev-parse --short HEAD',
                        returnStdout: true
                    ).trim()
                    currentBuild.displayName = "#${env.BUILD_NUMBER} - ${env.GIT_SHA}"
                    currentBuild.description = "v${env.APP_VERSION}"
                }
                sh '''
                    echo "=== Параметры сборки ==="
                    echo "Сборка:  #${BUILD_NUMBER}"
                    echo "Коммит:  ${GIT_SHA}"
                    echo "Версия:  ${APP_VERSION}"
                    echo "Образ:   ${IMAGE}"
                    echo
                    echo "=== Проверка доступа к демону Docker (DooD) ==="
                    docker version --format 'Клиент: {{.Client.Version}}, сервер: {{.Server.Version}}'
                '''
            }
        }

        stage('2. Build Image') {
            steps {
                sh '''
                    docker build \
                        --target runtime \
                        --build-arg APP_VERSION="${APP_VERSION}" \
                        --build-arg BUILD_NUMBER="${BUILD_NUMBER}" \
                        --build-arg GIT_COMMIT="${GIT_SHA}" \
                        -t "${IMAGE}" \
                        -t "${IMAGE_LATEST}" \
                        .

                    echo "=== Собранный образ ==="
                    docker image inspect "${IMAGE}" \
                        --format 'Размер: {{.Size}} байт, создан: {{.Created}}'
                '''
            }
        }

        stage('3. Unit Tests') {
            steps {
                sh '''
                    docker build --target test -t "${TEST_IMAGE}" .

                    rm -rf reports && mkdir -p reports
                    docker rm -f "${TEST_CONT}" >/dev/null 2>&1 || true

                    # Контейнер запускается БЕЗ --rm: остановленный контейнер должен
                    # сохраниться, чтобы забрать из него отчёты командой docker cp.
                    # Bind-mount здесь не работает: в схеме DooD путь монтирования
                    # разрешает демон хоста, а не контейнер Jenkins.
                    set +e
                    docker run --name "${TEST_CONT}" "${TEST_IMAGE}"
                    RC=$?
                    set -e

                    docker cp "${TEST_CONT}:/app/reports/." reports/ \
                        || echo "ПРЕДУПРЕЖДЕНИЕ: отчёты не получены"
                    docker rm -f "${TEST_CONT}" >/dev/null 2>&1 || true

                    echo "=== Полученные отчёты ==="
                    ls -la reports/

                    # Код возврата pytest возвращается только сейчас, когда
                    # отчёты уже забраны.
                    exit $RC
                '''
            }
            post {
                always {
                    junit allowEmptyResults: false, testResults: 'reports/junit.xml'
                    archiveArtifacts artifacts: 'reports/*.xml', allowEmptyArchive: true
                }
            }
        }

        stage('4. Smoke Test') {
            steps {
                sh '''
                    docker rm -f "${SMOKE_NAME}" >/dev/null 2>&1 || true

                    # Порт наружу не публикуется: Jenkins и smoke-контейнер в одной
                    # сети, обращение идёт по имени контейнера через встроенный DNS.
                    docker run -d \
                        --name "${SMOKE_NAME}" \
                        --network "${CICD_NET}" \
                        -e APP_ENV=smoke \
                        -e APP_VERSION="${APP_VERSION}" \
                        -e BUILD_NUMBER="${BUILD_NUMBER}" \
                        -e GIT_COMMIT="${GIT_SHA}" \
                        -l project=pract4 \
                        "${IMAGE}"

                    echo "Ожидание готовности приложения..."
                    OK=0
                    for i in $(seq 1 30); do
                        if curl -fsS "http://${SMOKE_NAME}:${APP_PORT}/health" >/dev/null 2>&1; then
                            OK=1
                            echo "Приложение ответило с попытки $i"
                            break
                        fi
                        sleep 1
                    done

                    if [ "$OK" != "1" ]; then
                        echo "ОШИБКА: приложение не ответило за 30 секунд"
                        docker logs "${SMOKE_NAME}" || true
                        docker rm -f "${SMOKE_NAME}" >/dev/null 2>&1 || true
                        exit 1
                    fi

                    echo "=== Ответ /health ==="
                    curl -fsS "http://${SMOKE_NAME}:${APP_PORT}/health" | jq .

                    # Проверяем всю цепочку передачи метаданных:
                    # --build-arg -> ARG -> ENV -> os.environ -> HTTP-ответ.
                    ACTUAL=$(curl -fsS "http://${SMOKE_NAME}:${APP_PORT}/health" | jq -r .build)
                    if [ "$ACTUAL" != "${BUILD_NUMBER}" ]; then
                        echo "ОШИБКА: образ сообщает сборку $ACTUAL вместо ${BUILD_NUMBER}"
                        docker rm -f "${SMOKE_NAME}" >/dev/null 2>&1 || true
                        exit 1
                    fi

                    echo "=== Начало HTML-страницы ==="
                    curl -fsS "http://${SMOKE_NAME}:${APP_PORT}/" | head -12

                    docker rm -f "${SMOKE_NAME}" >/dev/null 2>&1 || true
                    echo "Smoke-тест пройден: образ работоспособен"
                '''
            }
        }

        stage('5. Push to Registry') {
            steps {
                sh '''
                    docker push "${IMAGE}"
                    docker push "${IMAGE_LATEST}"

                    echo "=== Теги в реестре ==="
                    curl -fsS "${REGISTRY_API}/v2/${IMAGE_NAME}/tags/list" | jq .
                '''
            }
        }

        stage('6. Deploy to Staging') {
            steps {
                sh '''
                    docker rm -f "${STAGING_NAME}" >/dev/null 2>&1 || true

                    # Локальная копия удаляется намеренно: так docker pull делает
                    # настоящее скачивание и доказывает, что образ лежит в реестре.
                    docker rmi "${IMAGE}" >/dev/null 2>&1 || true
                    docker pull "${IMAGE}"

                    docker run -d \
                        --name "${STAGING_NAME}" \
                        --network "${STAGING_NET}" \
                        --restart unless-stopped \
                        -p "${STAGING_PORT}:${APP_PORT}" \
                        -e APP_ENV=staging \
                        -e APP_VERSION="${APP_VERSION}" \
                        -e BUILD_NUMBER="${BUILD_NUMBER}" \
                        -e GIT_COMMIT="${GIT_SHA}" \
                        -l project=pract4 \
                        -l pract4.env=staging \
                        -l pract4.build="${BUILD_NUMBER}" \
                        "${IMAGE}"

                    docker ps --filter "name=${STAGING_NAME}" \
                        --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
                '''
            }
        }

        stage('7. Verify Staging') {
            steps {
                sh '''
                    echo "Ожидание готовности staging..."
                    OK=0
                    for i in $(seq 1 30); do
                        if curl -fsS "http://${STAGING_NAME}:${APP_PORT}/health" >/dev/null 2>&1; then
                            OK=1
                            echo "Staging ответил с попытки $i"
                            break
                        fi
                        sleep 1
                    done

                    if [ "$OK" != "1" ]; then
                        echo "ОШИБКА: staging не отвечает"
                        docker logs --tail 50 "${STAGING_NAME}" || true
                        exit 1
                    fi

                    echo "=== Ответ /health ==="
                    curl -fsS "http://${STAGING_NAME}:${APP_PORT}/health" | jq .

                    ENV_VALUE=$(curl -fsS "http://${STAGING_NAME}:${APP_PORT}/env")
                    [ "$ENV_VALUE" = "staging" ] \
                        || { echo "ОШИБКА: окружение = $ENV_VALUE, ожидалось staging"; exit 1; }

                    BUILD_VALUE=$(curl -fsS "http://${STAGING_NAME}:${APP_PORT}/health" | jq -r .build)
                    [ "$BUILD_VALUE" = "${BUILD_NUMBER}" ] \
                        || { echo "ОШИБКА: сборка = $BUILD_VALUE, ожидалась ${BUILD_NUMBER}"; exit 1; }

                    echo
                    echo "STAGING ПРОВЕРЕН: сборка ${BUILD_NUMBER}, окружение staging"
                    echo "Открыть в браузере: http://localhost:${STAGING_PORT}/"
                '''
            }
        }

        stage('8. Approval for Production') {
            steps {
                // timeout обязателен: ожидающий input удерживает исполнитель.
                timeout(time: 30, unit: 'MINUTES') {
                    script {
                        def approver = input(
                            id: 'DeployToProd',
                            message: """Сборка #${env.BUILD_NUMBER} успешно проверена на STAGING.

Коммит:   ${env.GIT_SHA}
Версия:   ${env.APP_VERSION}
Staging:  http://localhost:${env.STAGING_PORT}/

Развернуть эту сборку в PRODUCTION?""",
                            ok: 'Развернуть в PRODUCTION',
                            submitterParameter: 'APPROVED_BY'
                        )
                        env.APPROVED_BY = (approver instanceof Map)
                            ? approver['APPROVED_BY']
                            : approver.toString()
                    }
                }
                echo "Развёртывание в production одобрил: ${env.APPROVED_BY}"
            }
        }

        stage('9. Deploy to Production') {
            steps {
                sh '''
                    echo "Одобрено пользователем: ${APPROVED_BY}"

                    PREV=$(docker inspect "${PROD_NAME}" \
                        --format '{{index .Config.Labels "pract4.build"}}' 2>/dev/null || echo "нет")
                    echo "Предыдущая версия в production: сборка ${PREV}"

                    docker rm -f "${PROD_NAME}" >/dev/null 2>&1 || true
                    docker rmi "${IMAGE}" >/dev/null 2>&1 || true
                    docker pull "${IMAGE}"

                    docker run -d \
                        --name "${PROD_NAME}" \
                        --network "${PROD_NET}" \
                        --restart unless-stopped \
                        -p "${PROD_PORT}:${APP_PORT}" \
                        -e APP_ENV=production \
                        -e APP_VERSION="${APP_VERSION}" \
                        -e BUILD_NUMBER="${BUILD_NUMBER}" \
                        -e GIT_COMMIT="${GIT_SHA}" \
                        -l project=pract4 \
                        -l pract4.env=production \
                        -l pract4.build="${BUILD_NUMBER}" \
                        -l pract4.commit="${GIT_SHA}" \
                        -l pract4.approved_by="${APPROVED_BY}" \
                        "${IMAGE}"

                    docker ps --filter "name=${PROD_NAME}" \
                        --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
                '''
            }
        }

        stage('10. Verify Production') {
            steps {
                sh '''
                    echo "Ожидание готовности production..."
                    OK=0
                    for i in $(seq 1 30); do
                        if curl -fsS "http://${PROD_NAME}:${APP_PORT}/health" >/dev/null 2>&1; then
                            OK=1
                            echo "Production ответил с попытки $i"
                            break
                        fi
                        sleep 1
                    done

                    if [ "$OK" != "1" ]; then
                        echo "ОШИБКА: production не отвечает"
                        docker logs --tail 50 "${PROD_NAME}" || true
                        exit 1
                    fi

                    echo "=== Ответ /health ==="
                    curl -fsS "http://${PROD_NAME}:${APP_PORT}/health" | jq .

                    ENV_VALUE=$(curl -fsS "http://${PROD_NAME}:${APP_PORT}/env")
                    [ "$ENV_VALUE" = "production" ] \
                        || { echo "ОШИБКА: окружение = $ENV_VALUE, ожидалось production"; exit 1; }

                    BUILD_VALUE=$(curl -fsS "http://${PROD_NAME}:${APP_PORT}/health" | jq -r .build)
                    [ "$BUILD_VALUE" = "${BUILD_NUMBER}" ] \
                        || { echo "ОШИБКА: сборка = $BUILD_VALUE, ожидалась ${BUILD_NUMBER}"; exit 1; }

                    # Свидетельство развёртывания: ответы самих приложений
                    # сохраняются и прикрепляются к сборке как артефакты.
                    mkdir -p deployment
                    curl -fsS "http://${PROD_NAME}:${APP_PORT}/api/info"    | jq . > deployment/prod-info.json
                    curl -fsS "http://${STAGING_NAME}:${APP_PORT}/api/info" | jq . > deployment/staging-info.json

                    echo
                    echo "=== Свидетельство развёртывания ==="
                    echo "--- production ---"
                    cat deployment/prod-info.json
                    echo "--- staging ---"
                    cat deployment/staging-info.json

                    echo
                    echo "PRODUCTION ПРОВЕРЕН: сборка ${BUILD_NUMBER}, окружение production"
                    echo "Открыть в браузере: http://localhost:${PROD_PORT}/"
                '''
                archiveArtifacts artifacts: 'deployment/*.json', fingerprint: true
            }
        }
    }

    post {
        always {
            sh '''
                echo "=== Контейнеры проекта ==="
                docker ps -a --filter "label=project=pract4" \
                    --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

                # Уборка временных сущностей. Staging и production не трогаем:
                # это развёрнутые среды, они должны продолжать работать.
                docker rm -f "${SMOKE_NAME}" >/dev/null 2>&1 || true
                docker rm -f "${TEST_CONT}"  >/dev/null 2>&1 || true
                docker rmi   "${TEST_IMAGE}" >/dev/null 2>&1 || true
            '''
        }
        success {
            echo "УСПЕХ: сборка ${env.BUILD_NUMBER} развёрнута в production"
            echo "Staging:    http://localhost:${env.STAGING_PORT}/"
            echo "Production: http://localhost:${env.PROD_PORT}/"
        }
        failure {
            echo "ОШИБКА: сборка ${env.BUILD_NUMBER} завершилась неудачно"
        }
        aborted {
            echo "ПРЕРВАНО: развёртывание в production не выполнялось"
        }
        cleanup {
            // Выполняется последним — уже после archiveArtifacts и junit.
            sh 'rm -rf reports deployment || true'
        }
    }
}
