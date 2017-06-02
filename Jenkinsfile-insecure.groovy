dir("packages/adminrouter/extra/src") {
    stage('Prepare devkit container') {
        sh 'make update-devkit'
    }

    try {
        stage('make check-api-docs') {
            sh 'make check-api-docs'
        }

        stage('make flake8') {
            sh 'make flake8'
        }

        stage('make test') {
            sh 'make test'
        }

    } finally {
        stage('archive build logs') {
             archiveArtifacts artifacts: 'test-harness/logs/*.log', allowEmptyArchive: true, excludes: 'test_harness/', fingerprint: true
        }

        stage('Cleanup docker container'){
            sh 'make clean-containers'
            sh "docker rmi -f adminrouter-devkit || true"
        }
    }
}
