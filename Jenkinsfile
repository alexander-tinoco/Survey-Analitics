// CI pipeline: lint, test, and enforce the coverage gate on every build.
//
// The stack runs through docker compose -f docker-compose.yml so the pipeline executes the same
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
                sh 'docker compose -f docker-compose.yml build'
            }
        }

        stage('Lint') {
            steps {
                sh 'docker compose -f docker-compose.yml run --rm web ruff check --output-format=github .'
                sh 'docker compose -f docker-compose.yml run --rm web ruff format --check .'
            }
        }

        stage('Test') {
            steps {
                // pytest carries the coverage gate from pyproject.toml, so a
                // drop below the threshold fails the build here.
                sh 'docker compose -f docker-compose.yml run --rm web pytest'
            }
        }

        stage('Engine coverage') {
            steps {
                // The analytics engine is held to 100%, not the project-wide
                // floor: it is pure and fast to test, and an untested branch
                // in it produces a plausible wrong number rather than a
                // crash. CLAUDE.md states the rule; this stage enforces it.
                // -o addopts="" clears the project-wide --cov=. from pyproject,
                // which would otherwise be added to this one rather than
                // replaced, and drag the measurement back to the whole repo.
                sh '''docker compose -f docker-compose.yml run --rm web pytest tests/analytics \
                        -o addopts="" \
                        --cov=apps/analytics/engine \
                        --cov-report=term-missing \
                        --cov-fail-under=100'''
            }
        }
    }

    post {
        always {
            sh 'docker compose -f docker-compose.yml down -v --remove-orphans || true'
            cleanWs()
        }
        failure {
            echo 'Build failed — check the lint and test stages above.'
        }
    }
}
