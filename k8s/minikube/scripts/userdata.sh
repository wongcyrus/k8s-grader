#!/bin/bash

# 1. Install latest Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-latest.x86_64.rpm
sudo rpm -Uvh minikube-latest.x86_64.rpm

# 2. Update system and install Docker
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker

# 3. Add user to docker group and fix socket permissions for script execution
sudo usermod -aG docker $USER
# Workaround for 'newgrp' halting scripts: fix permissions on the active socket
sudo chown $USER:docker /var/run/docker.sock 
docker -v

# 4. Fetch and install the LATEST kubectl dynamically
KUBECTL_LATEST=$(curl -L -s https://dl.k8s.io/release/stable.txt)
echo "Downloading kubectl version: $KUBECTL_LATEST"
curl -LO "https://dl.k8s.io/release/${KUBECTL_LATEST}/bin/linux/amd64/kubectl"
sudo chmod +x ./kubectl
sudo mv ./kubectl /usr/local/bin/kubectl

# 5. Get AWS EC2 Private IP using IMDSv2
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4 -H "X-aws-ec2-metadata-token: $TOKEN")

# 6. Start Minikube & Enable Metrics
minikube start --apiserver-ips=$PRIVATE_IP
minikube addons enable metrics-server
minikube status

echo "Done! The ca.crt, client.crt and client.key are located in ~/.minikube/certs or ~/.minikube/profiles/minikube/"