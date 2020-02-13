#!/usr/bin/env bash
set -e

export PATH="$HOME"/.pyenv/bin:"$PATH"

yum install -y git zlib-devel bzip2 bzip2-devel gcc gcc-c++ make git patch openssl-devel zlib-devel readline-devel sqlite-devel bzip2-devel
curl -L https://raw.githubusercontent.com/yyuu/pyenv-installer/master/bin/pyenv-installer -o /tmp/pyenv-installer

# Install pyenv
bash /tmp/pyenv-installer
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Install Python versions
pyenv install 3.6.3
pyenv install 3.5.9
pyenv global 3.6.3 3.5.9

#Set up shell
cat << 'EOF' > "$HOME"/.pyenvrc
export PATH="$HOME"/.pyenv/bin:"$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
EOF

cat << EOF >> "$HOME"/.bash_profile
if [ -f ~/.pyenvrc ]; then
        . ~/.pyenvrc
fi
EOF

# Inatall Docker
yum install -y yum-utils device-mapper-persistent-data lvm2
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum install -y docker-ce docker-ce-cli containerd.io
