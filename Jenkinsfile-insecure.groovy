dir("packages/adminrouter/extra/src") {
    stage('Prepare devkit container') {
        sh 'make update-devkit'
    }

    try {
        stage('make flake8') {
            sh 'make flake8'
        }

        stage('make test') {
            sh 'make test'
        }

    } finally {
        stage('Cleanup docker container'){
            sh 'make clean-containers'
            sh "docker rmi -f adminrouter-devkit || true"
        }
    }
}
