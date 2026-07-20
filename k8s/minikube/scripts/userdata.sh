# https://medium.com/@kuljeetsinghkhurana/access-minikube-using-kubectl-from-remote-machine-2b0eeefad9cb
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-latest.x86_64.rpm
sudo rpm -Uvh minikube-latest.x86_64.rpm
sudo yum update -y
sudo yum install -y docker
sudo usermod -aG docker $USER # && newgrp docker <- this is not working
sudo systemctl start docker && sudo systemctl enable docker
docker -v
curl -Ls https://storage.googleapis.com/kubernetes-release/release/stable.txt
curl -LO https://storage.googleapis.com/kubernetes-release/release/v1.36.2/bin/linux/amd64/kubectl
sudo chmod +x ./kubectl
sudo mv ./kubectl /usr/local/bin/kubectl
TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4 -H "X-aws-ec2-metadata-token: $TOKEN")
minikube start --apiserver-ips=$PRIVATE_IP
minikube addons enable metrics-server
minikube status

# the ca.crt, client.crt and client.key is in ~/.minikube
