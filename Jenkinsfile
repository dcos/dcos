#!/usr/bin/env groovy

@Library('sec_ci_libs') _

def master_branches = ["master", ] as String[]

if (master_branches.contains(env.BRANCH_NAME)) {
    // Rebuild main branch once a day
    properties([
        pipelineTriggers([cron('H H * * *')])
    ])
}

task_wrapper('mesos-sec', master_branches){
    stage("Verify author") {
        user_is_authorized(master_branches)
    }

    stage('Cleanup workspace') {
        deleteDir()
    }

    stage('Checkout') {
        checkout scm
    }

    load 'Jenkinsfile-insecure.groovy'
}
