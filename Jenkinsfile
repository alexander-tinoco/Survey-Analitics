// CI pipeline: lint, test, and enforce the coverage gate on every build.
//
// The stack runs through docker compose so the pipeline executes the same
// images a developer runs locally — a green build here means the same commands
// pass on a workstation.

pipeline {
    agent any

    environment {
        COMPOSE_PROJECT_NAME = "surveyanalytics-${env.BUILD_NUMBER}"
        DJANGO_SETTINGS_MODULE = 'config.settings.local'
    }

    options {
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Prepare environment') {
            steps {
                // CI has no .env; the example carries safe development defaults.
                sh 'cp .env.example .env'
            }
        }

        stage('Build') {
            steps {
                sh 'docker compose build'
            }
        }

        stage('Lint') {
            steps {
                sh 'docker compose run --rm web ruff check --output-format=github .'
                sh 'docker compose run --rm web ruff format --check .'
            }
        }

        stage('Test') {
            steps {
                // pytest carries the coverage gate from pyproject.toml, so a
                // drop below the threshold fails the build here.
                sh 'docker compose run --rm web pytest'
            }
        }
    }

    post {
        always {
            sh 'docker compose down -v --remove-orphans || true'
            cleanWs()
        }
        failure {
            echo 'Build failed — check the lint and test stages above.'
        }
    }
}
