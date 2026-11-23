// Backend delivery line of karacaismail/frappesetup. Design: backend/docs/dagitim/ortamlar.md.
//
// A push to main builds one release (images pinned by digest), deploys it to alpha and checks
// alpha. beta, rc and prod each wait for a person to press the button. Each step moves the same
// release that is current and healthy in the previous environment; nothing is rebuilt.
//
// Jenkins setup (DevOps owner): Pipeline job, SCM branch */main, script path
// backend/deploy/jenkins/backend.Jenkinsfile, "GitHub hook trigger" on. Plugins: Pipeline,
// Git, GitHub, SSH Agent, Lockable Resources, Pipeline: Milestone Step, Credentials Binding.
// Credentials: atonota-deploy-ssh (SSH key of user "deploy"), atonota-registry (GHCR user and token).
// Agents with label atonota-build: Docker, Python 3.9+, uv, ssh on the Tailscale network.

// DEPLOYING names the environment whose deployment has started. A failure before that point
// (for example a refused promotion check) must not roll back an environment that did not change.
def deployAndCheck(String target) {
    env.DEPLOYING = target
    sshagent(credentials: ['atonota-deploy-ssh']) {
        sh "backend/deploy/bin/deploy ${target} release"
        sh "backend/deploy/bin/health ${target} release"
    }
    env.DEPLOYING = ''
}

def rollbackAfterFailure(String target) {
    if (env.DEPLOYING != target) {
        echo "No deployment started in ${target}; nothing to roll back."
        return
    }
    sshagent(credentials: ['atonota-deploy-ssh']) {
        sh """
            set -eu
            . backend/deploy/environments/${target}.env
            if [ "\$ATONOTA_AUTO_RESTORE_ON_FAILURE" = 1 ]; then
                backend/deploy/bin/rollback ${target} backend --restore-backup
            else
                backend/deploy/bin/rollback ${target} backend
            fi
        """
    }
}

def promote(String target, String source) {
    unstash 'release'
    sshagent(credentials: ['atonota-deploy-ssh']) {
        sh "rm -rf source && backend/deploy/bin/fetch-current ${source} backend source"
        sh "python3 -I backend/deploy/release.py promote-check release/release.json --target ${target} --source-record source/source-record.json"
    }
    deployAndCheck(target)
}

pipeline {
    agent none
    options {
        buildDiscarder(logRotator(numToKeepStr: '100', artifactNumToKeepStr: '100'))
        timestamps()
    }
    triggers {
        githubPush()
    }
    environment {
        ATONOTA_REGISTRY = 'ghcr.io/karacaismail'
    }
    stages {
        stage('Build and alpha') {
            agent { label 'atonota-build' }
            stages {
                stage('Gates') {
                    steps {
                        sh 'python3 -I -m unittest discover -s backend/deploy/tests'
                        sh 'backend/dev/bin/module-boundaries'
                        sh 'backend/dev/bin/security-audit'
                        sh 'backend/dev/bin/test platform_core'
                        sh 'backend/dev/bin/test hrms_tr'
                    }
                }
                stage('Build release') {
                    steps {
                        withCredentials([usernamePassword(credentialsId: 'atonota-registry',
                                usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_TOKEN')]) {
                            sh 'printf %s "$REGISTRY_TOKEN" | docker login ghcr.io --username "$REGISTRY_USER" --password-stdin'
                        }
                        sh 'rm -rf release && backend/deploy/bin/build-release release/release.json'
                        archiveArtifacts artifacts: 'release/release.json', fingerprint: true
                        stash name: 'release', includes: 'release/**'
                    }
                    post {
                        always { sh 'docker logout ghcr.io || true' }
                    }
                }
                stage('Deploy alpha') {
                    steps {
                        milestone(1)
                        lock(resource: 'atonota-alpha') {
                            deployAndCheck('alpha')
                        }
                    }
                    post {
                        failure { rollbackAfterFailure('alpha') }
                    }
                }
            }
        }
        stage('Move to beta') {
            input {
                message 'Move this release from alpha to beta?'
                ok 'Move to beta'
                submitter 'atonota-deployers'
            }
            agent { label 'atonota-build' }
            steps {
                milestone(2)
                lock(resource: 'atonota-beta') {
                    promote('beta', 'alpha')
                }
            }
            post {
                failure { rollbackAfterFailure('beta') }
            }
        }
        stage('Move to rc') {
            input {
                message 'Move this release from beta to rc?'
                ok 'Move to rc'
                submitter 'atonota-deployers'
            }
            agent { label 'atonota-build' }
            steps {
                milestone(3)
                lock(resource: 'atonota-rc') {
                    promote('rc', 'beta')
                }
            }
            post {
                failure { rollbackAfterFailure('rc') }
            }
        }
        stage('Move to prod') {
            input {
                message 'Move this release from rc to prod?'
                ok 'Move to prod'
                submitter 'atonota-release-managers'
            }
            agent { label 'atonota-build' }
            steps {
                milestone(4)
                lock(resource: 'atonota-prod') {
                    promote('prod', 'rc')
                }
            }
            post {
                failure { rollbackAfterFailure('prod') }
            }
        }
    }
}
