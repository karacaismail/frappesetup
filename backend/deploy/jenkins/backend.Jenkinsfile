// Backend delivery line of karacaismail/frappesetup. Design: backend/docs/dagitim/ortamlar.md.
//
// A push to main builds one release (images pinned by digest), deploys it to alpha and checks
// alpha. beta waits for a person to press the button and moves the same release. rc and prod are
// not in this job: the job "atonota-release/atonota-promote" (promote.Jenkinsfile) moves them,
// because the rc and prod keys live only in that Jenkins folder.
//
// Jenkins setup (DevOps owner): Pipeline job "atonota-delivery/atonota-backend", SCM branch */main,
// script path backend/deploy/jenkins/backend.Jenkinsfile, "GitHub hook trigger" on. Plugins:
// Pipeline, Git, GitHub, SSH Agent, Lockable Resources, Pipeline: Milestone Step, Credentials
// Binding, Copy Artifact, Timestamper. Credentials of the folder "atonota-delivery":
// atonota-deploy-ssh-alpha and atonota-deploy-ssh-beta (one key per environment and server user),
// atonota-registry (GHCR user and token). Agents with label atonota-build: Docker, Python 3.9+, uv,
// ssh on the Tailscale network.
//
// Every stage after the first one starts from an empty workspace and takes the scripts and the
// release from this build's stashes. A later stage never checks out a newer main.

// DEPLOYING names the environment whose deployment has started. A failure before that point
// (for example a refused promotion check) must not roll back an environment that did not change.
def deployAndCheck(String target) {
    env.DEPLOYING = target
    sshagent(credentials: ["atonota-deploy-ssh-${target}"]) {
        sh "backend/deploy/bin/deploy ${target} release"
        sh "backend/deploy/bin/health ${target} release"
    }
    env.DEPLOYING = ''
}

// The server undoes only the release named here, and only if it changed the environment.
def rollbackAfterFailure(String target) {
    if (env.DEPLOYING != target) {
        echo "No deployment started in ${target}; nothing to roll back."
        return
    }
    def restore = sh(returnStdout: true,
        script: "sed -n 's/^ATONOTA_AUTO_RESTORE_ON_FAILURE=//p' backend/deploy/environments/${target}.env").trim()
    def extra = restore == '1' ? ' --restore-backup' : ''
    sshagent(credentials: ["atonota-deploy-ssh-${target}"]) {
        sh "backend/deploy/bin/rollback ${target} backend --failed ${env.RELEASE_ID}${extra}"
    }
}

def useStashes() {
    deleteDir()
    unstash 'deploy'
    unstash 'release'
    sh "test \"\$(python3 -I backend/deploy/release.py field release/release.json commit)\" = '${env.DEPLOY_COMMIT}'"
}

def promote(String target, String source) {
    useStashes()
    sshagent(credentials: ["atonota-deploy-ssh-${source}"]) {
        sh "rm -rf source && backend/deploy/bin/fetch-current ${source} backend source"
    }
    sh "python3 -I backend/deploy/release.py promote-check release/release.json --target ${target} --source-record source/source-record.json"
    deployAndCheck(target)
}

pipeline {
    agent none
    options {
        skipDefaultCheckout()
        buildDiscarder(logRotator(numToKeepStr: '100', artifactNumToKeepStr: '100'))
        timestamps()
        // The promotion jobs compare a server copy with this build's archived release.json.
        copyArtifactPermission('/atonota-delivery/atonota-promote,/atonota-release/atonota-promote')
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
                stage('Checkout') {
                    steps {
                        script {
                            def scmVars = checkout scm
                            env.DEPLOY_COMMIT = scmVars.GIT_COMMIT
                        }
                        stash name: 'deploy', includes: 'backend/deploy/**'
                    }
                }
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
                        sh 'rm -rf release && GIT_COMMIT="$DEPLOY_COMMIT" backend/deploy/bin/build-release release/release.json'
                        script {
                            env.RELEASE_ID = sh(returnStdout: true,
                                script: 'python3 -I backend/deploy/release.py field release/release.json release_id').trim()
                        }
                        // The release carries the compose files and server scripts of its own commit;
                        // a promotion to rc or prod sends exactly this copy (docs/dagitim/ortamlar.md).
                        sh 'python3 -I backend/deploy/release.py pack-deploy --commit "$DEPLOY_COMMIT" release'
                        archiveArtifacts artifacts: 'release/**', fingerprint: true
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
            // The input directive waits before the agent is taken, so no agent sits idle.
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
    }
}
