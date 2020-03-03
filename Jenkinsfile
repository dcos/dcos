#!/usr/bin/env groovy

@Library('sec_ci_libs@v2-latest') _

def master_branches = ["master", ] as String[]

pipeline {
  agent none
  triggers {
    // Rebuild main branch once a day
    cron(BRANCH_NAME == "master" ? 'H H * * *' : '')
  }

  stages {
    stage("Verify author for PR") {
      // using shakedown node because it's a lightweight Alpine Docker image instead of full VM
      agent {
        label "shakedown"
      }
      when {
        beforeAgent true
        changeRequest()
      }
      steps {
        user_is_authorized(master_branches, '8b793652-f26a-422f-a9ba-0d1e47eb9d89', '#dcos-security-ci')
      }
    }

    stage('Adminrouter') {
      steps {
        script {
          task_wrapper('mesos-sec', master_branches, '8b793652-f26a-422f-a9ba-0d1e47eb9d89', '#dcos-security-ci') {
              stage('Cleanup workspace') {
                  deleteDir()
              }
          
              stage('Checkout') {
                  checkout scm
              }
          
              load 'Jenkinsfile-insecure.groovy'
	    }
        }  
      }
    }
  }
}
