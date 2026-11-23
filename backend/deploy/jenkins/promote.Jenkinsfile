// Manual promotion and rollback of any release kind. Design: backend/docs/dagitim/ortamlar.md.
//
// Use it when a release must move outside its own build (an older build waits at a button that a
// newer build already passed), or to roll an environment back. Promotion takes the release that is
// current and healthy in the previous environment, never a build artifact.
//
// Jenkins setup (DevOps owner): Pipeline job, SCM karacaismail/frappesetup branch */main,
// script path backend/deploy/jenkins/promote.Jenkinsfile, no trigger.

pipeline {
    agent { label 'atonota-build' }
    options {
        buildDiscarder(logRotator(numToKeepStr: '200'))
        timestamps()
        disableConcurrentBuilds()
    }
    parameters {
        choice(name: 'ACTION', choices: ['promote', 'rollback', 'rollback-restore'],
            description: 'promote: move the previous environment\'s current release. rollback: previous images or web files. rollback-restore: also restore the backup taken before the failed backend release.')
        choice(name: 'KIND', choices: ['backend', 'web'], description: 'Which release line.')
        choice(name: 'ENVIRONMENT', choices: ['beta', 'rc', 'prod', 'alpha'], description: 'Target environment. alpha accepts rollback only.')
    }
    stages {
        stage('Check request') {
            steps {
                script {
                    if (params.ACTION == 'promote' && params.ENVIRONMENT == 'alpha') {
                        error('alpha is filled from main only.')
                    }
                    if (params.ACTION == 'rollback-restore' && params.KIND != 'backend') {
                        error('rollback-restore applies to backend releases only.')
                    }
                }
            }
        }
        stage('Promote') {
            when { expression { params.ACTION == 'promote' } }
            steps {
                script {
                    def sources = [beta: 'alpha', rc: 'beta', prod: 'rc']
                    def source = sources[params.ENVIRONMENT]
                    sshagent(credentials: ['atonota-deploy-ssh']) {
                        sh "rm -rf release && backend/deploy/bin/fetch-current ${source} ${params.KIND} release"
                        sh "python3 -I backend/deploy/release.py promote-check release/release.json --target ${params.ENVIRONMENT} --source-record release/source-record.json"
                    }
                    def id = sh(returnStdout: true, script: 'python3 -I backend/deploy/release.py field release/release.json release_id').trim()
                    input(message: "Move ${id} from ${source} to ${params.ENVIRONMENT}?", ok: 'Move',
                        submitter: params.ENVIRONMENT == 'prod' ? 'atonota-release-managers' : 'atonota-deployers')
                    lock(resource: "atonota-${params.ENVIRONMENT}") {
                        env.DEPLOYING = params.ENVIRONMENT
                        sshagent(credentials: ['atonota-deploy-ssh']) {
                            sh "backend/deploy/bin/deploy ${params.ENVIRONMENT} release"
                            sh "backend/deploy/bin/health ${params.ENVIRONMENT} release"
                        }
                    }
                }
            }
            post {
                failure {
                    script {
                        // Roll back only when the deployment itself started.
                        if (env.DEPLOYING == params.ENVIRONMENT) {
                            sshagent(credentials: ['atonota-deploy-ssh']) {
                                sh "backend/deploy/bin/rollback ${params.ENVIRONMENT} ${params.KIND}"
                            }
                        }
                    }
                }
            }
        }
        stage('Roll back') {
            when { expression { params.ACTION != 'promote' } }
            steps {
                input(message: "${params.ACTION} ${params.KIND} in ${params.ENVIRONMENT}?", ok: 'Roll back',
                    submitter: params.ENVIRONMENT == 'prod' ? 'atonota-release-managers' : 'atonota-deployers')
                lock(resource: "atonota-${params.ENVIRONMENT}") {
                    sshagent(credentials: ['atonota-deploy-ssh']) {
                        sh "backend/deploy/bin/rollback ${params.ENVIRONMENT} ${params.KIND}" +
                            (params.ACTION == 'rollback-restore' ? ' --restore-backup' : '')
                    }
                }
            }
        }
    }
}
