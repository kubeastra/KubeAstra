// ── K8s DevOps Assistant — Jenkins Pipeline ──────────────────────────────────
//
// Builds and pushes two Docker images to your container registry:
//   <REGISTRY>/<FEED>/k8s-devops-backend:<tag>
//   <REGISTRY>/<FEED>/k8s-devops-frontend:<tag>
//
// Required Jenkins credentials (Manage Jenkins → Credentials):
//   docker-registry-credentials  — Username/Password or Secret Text (registry API key)
//
// Optional parameters (can be set as build parameters or left as defaults):
//   REGISTRY   — Docker registry host  (e.g. ghcr.io/your-org, docker.io/your-org)
//   FEED       — Image namespace / feed name
//   IMAGE_TAG  — Override the auto-generated tag (git SHA + branch)

pipeline {
    agent {
        label 'linux'
    }

    environment {
        REGISTRY      = 'ghcr.io/your-org'
        FEED          = 'k8s-devops-assistant'
        BACKEND_IMAGE = "${REGISTRY}/${FEED}/k8s-devops-backend"
        FRONTEND_IMAGE = "${REGISTRY}/${FEED}/k8s-devops-frontend"
    }

    parameters {
        string(name: 'CUSTOM_TAG', defaultValue: '', description: 'Override image tag (leave blank for auto: git-SHA-branch)')
    }

    stages {

        // ── 1. Checkout ──────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    def shortSha = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
                    // BRANCH_NAME is set by Jenkins for multibranch pipelines.
                    // GIT_BRANCH is the fallback (classic pipeline). Strip the
                    // "origin/" prefix if present and sanitise special characters.
                    def rawBranch = (env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'unknown')
                                        .replaceAll('^origin/', '')
                                        .replaceAll('[^a-zA-Z0-9._-]', '-')
                    env.IMAGE_TAG = params.CUSTOM_TAG ?: "${rawBranch}-${shortSha}"
                    echo "Building images with tag: ${env.IMAGE_TAG}"
                }
            }
        }

        // ── 2. Build & push backend ──────────────────────────────────────────
        // Workspace root IS the repo root — no dir() wrapper needed.
        // "." gives Docker access to both mcp/ and ui/backend/
        stage('Build & Push Backend') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'docker-registry-credentials',
                    usernameVariable: 'REGISTRY_USER',
                    passwordVariable: 'REGISTRY_PASSWORD'
                )]) {
                    sh 'echo "$REGISTRY_PASSWORD" | docker login ${REGISTRY} -u "$REGISTRY_USER" --password-stdin'
                    sh """
                        docker build \\
                          -f ui/backend/Dockerfile \\
                          -t ${BACKEND_IMAGE}:${IMAGE_TAG} \\
                          .
                        docker push ${BACKEND_IMAGE}:${IMAGE_TAG}
                    """
                }
            }
        }

        // ── 3. Build & push frontend ─────────────────────────────────────────
        stage('Build & Push Frontend') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'docker-registry-credentials',
                    usernameVariable: 'REGISTRY_USER',
                    passwordVariable: 'REGISTRY_PASSWORD'
                )]) {
                    dir('ui/frontend') {
                        sh 'echo "$REGISTRY_PASSWORD" | docker login ${REGISTRY} -u "$REGISTRY_USER" --password-stdin'
                        sh """
                            docker build \\
                              -t ${FRONTEND_IMAGE}:${IMAGE_TAG} \\
                              .
                            docker push ${FRONTEND_IMAGE}:${IMAGE_TAG}
                        """
                    }
                }
            }
        }

        // ── 4. Summary ───────────────────────────────────────────────────────
        stage('Summary') {
            steps {
                echo """
╔══════════════════════════════════════════════════════════════╗
║  Images pushed                                               ║
╠══════════════════════════════════════════════════════════════╣
║  ${BACKEND_IMAGE}:${IMAGE_TAG}
║  ${FRONTEND_IMAGE}:${IMAGE_TAG}
╚══════════════════════════════════════════════════════════════╝

To deploy with Helm:
  helm upgrade --install k8s-devops helm/k8s-devops-assistant \\
    --namespace k8s-devops --create-namespace \\
    --set backend.image.repository=${BACKEND_IMAGE} \\
    --set backend.image.tag=${IMAGE_TAG} \\
    --set frontend.image.repository=${FRONTEND_IMAGE} \\
    --set frontend.image.tag=${IMAGE_TAG} \\
    -f my-values.yaml
"""
            }
        }
    }

    // ── Post actions ─────────────────────────────────────────────────────────
    post {
        success {
            echo "Build and push succeeded — tag: ${IMAGE_TAG}"
        }
        failure {
            echo "Pipeline failed — check logs above"
        }
    }
}
