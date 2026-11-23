// Web delivery line of karacaismail/atonota-web. Design: backend/docs/dagitim/ortamlar.md.
//
// Same shape as backend.Jenkinsfile: a push to atonota-web main builds one bundle, deploys it to
// alpha and checks alpha; beta waits for the button and moves the same bundle. rc and prod move
// with the job "atonota-release/atonota-promote" (promote.Jenkinsfile).
// The bundle is the built "dist" folder as a tar.gz with its SHA-256 in release.json.
//
// Jenkins setup (DevOps owner): Pipeline job "atonota-delivery/atonota-web" whose SCM is
// karacaismail/frappesetup, branch */main, script path backend/deploy/jenkins/web.Jenkinsfile,
// "GitHub hook trigger" on. The job checks out atonota-web itself, so a push to either repository
// starts it. The "Skip unchanged" stage stops a run whose atonota-web commit already runs in alpha.
// Credentials and plugins as in backend.Jenkinsfile. Agents with label atonota-build need Node 24
// and the Playwright system packages.

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

// The server undoes only the bundle named here, and only if it became current.
def rollbackAfterFailure(String target) {
    if (env.DEPLOYING != target) {
        echo "No deployment started in ${target}; nothing to roll back."
        return
    }
    sshagent(credentials: ["atonota-deploy-ssh-${target}"]) {
        sh "backend/deploy/bin/rollback ${target} web --failed ${env.RELEASE_ID}"
    }
}

def useStashes() {
    deleteDir()
    unstash 'deploy'
    unstash 'release'
    sh "test \"\$(python3 -I backend/deploy/release.py field release/release.json commit)\" = '${env.WEB_COMMIT}'"
}

def promote(String target, String source) {
    useStashes()
    sshagent(credentials: ["atonota-deploy-ssh-${source}"]) {
        sh "rm -rf source && backend/deploy/bin/fetch-current ${source} web source"
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
        // The promotion jobs compare a server copy with this build's archived bundle.
        copyArtifactPermission('/atonota-delivery/atonota-promote,/atonota-release/atonota-promote')
    }
    triggers {
        githubPush()
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
                        dir('web') {
                            git url: 'https://github.com/karacaismail/atonota-web.git', branch: 'main'
                        }
                        script {
                            env.WEB_COMMIT = sh(returnStdout: true, script: 'git -C web rev-parse HEAD').trim()
                        }
                    }
                }
                stage('Skip unchanged') {
                    steps {
                        script {
                            def running = ''
                            def source = 'alpha'
                            sshagent(credentials: ["atonota-deploy-ssh-${source}"]) {
                                running = sh(returnStdout: true, script: '''
                                    rm -rf alpha-web
                                    if backend/deploy/bin/fetch-current alpha web alpha-web >/dev/null 2>&1; then
                                        python3 -I backend/deploy/release.py field alpha-web/release.json commit
                                    fi
                                ''').trim()
                            }
                            env.WEB_UNCHANGED = (running == env.WEB_COMMIT) ? 'true' : 'false'
                        }
                    }
                }
                stage('Gates') {
                    when { environment name: 'WEB_UNCHANGED', value: 'false' }
                    steps {
                        dir('web') {
                            sh 'npm ci'
                            sh 'npm run lint'
                            sh 'npm run typecheck'
                            sh 'npm test'
                            // The panel is served under /panel/ on each tenant host (ortamlar.md).
                            sh 'npm run build -- --base=/panel/'
                        }
                    }
                }
                stage('Build release') {
                    when { environment name: 'WEB_UNCHANGED', value: 'false' }
                    steps {
                        sh 'rm -rf release && backend/deploy/bin/build-web web release'
                        // The release carries the server scripts of this checkout; a promotion
                        // sends exactly this copy (docs/dagitim/ortamlar.md).
                        sh 'python3 -I backend/deploy/release.py pack-deploy --commit "$DEPLOY_COMMIT" release'
                        script {
                            env.RELEASE_ID = sh(returnStdout: true,
                                script: 'python3 -I backend/deploy/release.py field release/release.json release_id').trim()
                        }
                        archiveArtifacts artifacts: 'release/**', fingerprint: true
                        stash name: 'release', includes: 'release/**'
                    }
                }
                stage('Deploy alpha') {
                    when { environment name: 'WEB_UNCHANGED', value: 'false' }
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
            when {
                beforeInput true
                environment name: 'WEB_UNCHANGED', value: 'false'
            }
            // The input directive waits before the agent is taken, so no agent sits idle.
            input {
                message 'Move this web bundle from alpha to beta?'
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
