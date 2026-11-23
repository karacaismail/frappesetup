// Web delivery line of karacaismail/atonota-web. Design: backend/docs/dagitim/ortamlar.md.
//
// Same shape as backend.Jenkinsfile: a push to atonota-web main builds one bundle, deploys it to
// alpha and checks alpha; beta, rc and prod wait for the button and move the same bundle.
// The bundle is the built "dist" folder as a tar.gz with its SHA-256 in release.json.
//
// Jenkins setup (DevOps owner): Pipeline job whose SCM is karacaismail/frappesetup, branch */main,
// script path backend/deploy/jenkins/web.Jenkinsfile, "GitHub hook trigger" on. The job checks
// out atonota-web itself, so a push to either repository starts it. The "Skip unchanged" stage
// stops a run whose atonota-web commit already runs in alpha.
// Agents with label atonota-build need Node 24 and the Playwright system packages.

def webBundle() {
    return sh(returnStdout: true, script: '''python3 -I -c 'import json; print(json.load(open("release/release.json"))["components"]["panel"]["file"])' ''').trim()
}

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
        sh "backend/deploy/bin/rollback ${target} web"
    }
}

def promote(String target, String source) {
    unstash 'release'
    sshagent(credentials: ['atonota-deploy-ssh']) {
        sh "rm -rf source && backend/deploy/bin/fetch-current ${source} web source"
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
    stages {
        stage('Build and alpha') {
            agent { label 'atonota-build' }
            stages {
                stage('Checkout atonota-web') {
                    steps {
                        dir('web') {
                            git url: 'https://github.com/karacaismail/atonota-web.git', branch: 'main'
                        }
                    }
                }
                stage('Skip unchanged') {
                    steps {
                        script {
                            def commit = sh(returnStdout: true, script: 'git -C web rev-parse HEAD').trim()
                            def running = ''
                            sshagent(credentials: ['atonota-deploy-ssh']) {
                                running = sh(returnStdout: true, script: '''
                                    rm -rf alpha-web
                                    if backend/deploy/bin/fetch-current alpha web alpha-web >/dev/null 2>&1; then
                                        python3 -I backend/deploy/release.py field alpha-web/release.json commit
                                    fi
                                ''').trim()
                            }
                            env.WEB_UNCHANGED = (running == commit) ? 'true' : 'false'
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
        stage('Move to rc') {
            when {
                beforeInput true
                environment name: 'WEB_UNCHANGED', value: 'false'
            }
            input {
                message 'Move this web bundle from beta to rc?'
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
            when {
                beforeInput true
                environment name: 'WEB_UNCHANGED', value: 'false'
            }
            input {
                message 'Move this web bundle from rc to prod?'
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
