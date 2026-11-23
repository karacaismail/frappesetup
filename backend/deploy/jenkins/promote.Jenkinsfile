// Manual promotion and rollback of any release kind. Design: backend/docs/dagitim/ortamlar.md.
//
// Two Jenkins jobs run this file, each in its own folder with its own keys:
//   atonota-delivery/atonota-promote  keys alpha and beta: promote to beta, roll back alpha or beta
//   atonota-release/atonota-promote   keys beta, rc and prod: promote to rc or prod, roll back rc or prod
// A request for an environment whose key the folder does not hold fails at its first ssh step.
// Jenkins setup (DevOps owner): Pipeline job, SCM karacaismail/frappesetup branch */main,
// script path backend/deploy/jenkins/promote.Jenkinsfile, no trigger.
//
// Promotion moves the release that is current and healthy in the previous environment. The server
// only names that release: the files deployed are the copy that Jenkins archived when it built the
// release, and the server copy must be identical to it. The check runs again after the approval,
// because the source environment may change while the request waits.

@groovy.transform.Field
final Map SOURCES = [beta: 'alpha', rc: 'beta', prod: 'rc']
@groovy.transform.Field
final Map JOBS = [backend: '/atonota-delivery/atonota-backend', web: '/atonota-delivery/atonota-web']

def useStash() {
    deleteDir()
    unstash 'deploy'
}

// Returns the id of the release to move. Leaves the archived copy in archive/release.
def checkSource(String source, String target, String job) {
    sshagent(credentials: ["atonota-deploy-ssh-${source}"]) {
        sh "rm -rf server && backend/deploy/bin/fetch-current ${source} ${params.KIND} server"
    }
    // check refuses a build field that is not a whole number before it is used below.
    sh "python3 -I backend/deploy/release.py check server/release.json --env ${source}"
    def build = sh(returnStdout: true, script: 'python3 -I backend/deploy/release.py field server/release.json build').trim()
    sh 'rm -rf archive'
    copyArtifacts(projectName: job, selector: specific(build), filter: 'release/**', target: 'archive',
        fingerprintArtifacts: true)
    sh 'python3 -I backend/deploy/release.py same-release archive/release/release.json server/release.json'
    sh "python3 -I backend/deploy/release.py promote-check archive/release/release.json --target ${target} --source-record server/source-record.json"
    return sh(returnStdout: true, script: 'python3 -I backend/deploy/release.py field archive/release/release.json release_id').trim()
}

pipeline {
    agent none
    options {
        skipDefaultCheckout()
        buildDiscarder(logRotator(numToKeepStr: '200'))
        timestamps()
        disableConcurrentBuilds()
    }
    parameters {
        choice(name: 'ACTION', choices: ['promote', 'rollback', 'rollback-restore'],
            description: 'promote: move the previous environment\'s current release. rollback: previous images or web files. rollback-restore: also restore the backup taken before the undone backend release.')
        choice(name: 'KIND', choices: ['backend', 'web'], description: 'Which release line.')
        choice(name: 'ENVIRONMENT', choices: ['beta', 'rc', 'prod', 'alpha'], description: 'Target environment. alpha accepts rollback only.')
    }
    stages {
        stage('Check request') {
            agent { label 'atonota-build' }
            steps {
                script {
                    if (params.ACTION == 'promote' && params.ENVIRONMENT == 'alpha') {
                        error('alpha is filled from main only.')
                    }
                    if (params.ACTION == 'rollback-restore' && params.KIND != 'backend') {
                        error('rollback-restore applies to backend releases only.')
                    }
                    env.APPROVERS = params.ENVIRONMENT == 'prod' ? 'atonota-release-managers' : 'atonota-deployers'
                    checkout scm
                }
                stash name: 'deploy', includes: 'backend/deploy/**'
            }
        }
        stage('Prepare promotion') {
            when { expression { params.ACTION == 'promote' } }
            agent { label 'atonota-build' }
            steps {
                useStash()
                script {
                    env.RELEASE_ID = checkSource(SOURCES[params.ENVIRONMENT], params.ENVIRONMENT, JOBS[params.KIND])
                }
            }
        }
        // The input directives wait before any agent is taken, so no agent sits idle.
        stage('Approve promotion') {
            when {
                beforeInput true
                expression { params.ACTION == 'promote' }
            }
            input {
                message "Move ${env.RELEASE_ID} to ${params.ENVIRONMENT}?"
                ok 'Move'
                submitter "${env.APPROVERS}"
            }
            steps {
                echo "Approved: ${env.RELEASE_ID} to ${params.ENVIRONMENT}"
            }
        }
        stage('Promote') {
            when { expression { params.ACTION == 'promote' } }
            agent { label 'atonota-build' }
            steps {
                useStash()
                lock(resource: "atonota-${params.ENVIRONMENT}") {
                    script {
                        def source = SOURCES[params.ENVIRONMENT]
                        def id = checkSource(source, params.ENVIRONMENT, JOBS[params.KIND])
                        if (id != env.RELEASE_ID) {
                            error("${source} now runs ${id}, not the approved ${env.RELEASE_ID}.")
                        }
                        env.DEPLOYING = params.ENVIRONMENT
                        sshagent(credentials: ["atonota-deploy-ssh-${params.ENVIRONMENT}"]) {
                            sh "backend/deploy/bin/deploy ${params.ENVIRONMENT} archive/release"
                            sh "backend/deploy/bin/health ${params.ENVIRONMENT} archive/release"
                        }
                        env.DEPLOYING = ''
                    }
                }
            }
            post {
                failure {
                    script {
                        // Roll back only when the deployment itself started, and only that release.
                        if (env.DEPLOYING == params.ENVIRONMENT) {
                            sshagent(credentials: ["atonota-deploy-ssh-${params.ENVIRONMENT}"]) {
                                sh "backend/deploy/bin/rollback ${params.ENVIRONMENT} ${params.KIND} --failed ${env.RELEASE_ID}"
                            }
                        }
                    }
                }
            }
        }
        stage('Approve rollback') {
            when {
                beforeInput true
                expression { params.ACTION != 'promote' }
            }
            input {
                message "${params.ACTION} ${params.KIND} in ${params.ENVIRONMENT}?"
                ok 'Roll back'
                submitter "${env.APPROVERS}"
            }
            steps {
                echo "Approved: ${params.ACTION} ${params.KIND} in ${params.ENVIRONMENT}"
            }
        }
        stage('Roll back') {
            when { expression { params.ACTION != 'promote' } }
            agent { label 'atonota-build' }
            steps {
                useStash()
                lock(resource: "atonota-${params.ENVIRONMENT}") {
                    sshagent(credentials: ["atonota-deploy-ssh-${params.ENVIRONMENT}"]) {
                        sh "backend/deploy/bin/rollback ${params.ENVIRONMENT} ${params.KIND}${params.ACTION == 'rollback-restore' ? ' --restore-backup' : ''}"
                    }
                }
            }
        }
    }
}
