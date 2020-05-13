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

    stage('Build') {
      parallel {
        stage('Tox') {
	  agent {
	    docker {
	      image 'mesosphere/jenkins-dind:0.7.0-ubuntu'
              label 'python-dind'
	      args '-u root --privileged'
	    }
	  }
          environment {
            AWS_REGION = 'us-west-2'
            AWS_DEFAULT_REGION = 'us-west-2'
          }
	  steps {
	    withCredentials([usernamePassword(credentialsId: 'eng-devprod-tox', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
	      sh('curl -O https://bootstrap.pypa.io/get-pip.py && /usr/bin/python3 get-pip.py')
	      sh('pip3 install -U tox pip')
	      sh('wrapper.sh make tox')
	    }
	  }
	  post {
            always {
              junit '**/junit-*.xml'
            }
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
  }
}
