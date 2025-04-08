# k8s-grader
This is the AWS SAM backend for Kubernetes Isekai (異世界), which can be deployed to AWS Academy Learner Lab. This allows educators and students to play and learn Kubernetes for free.

Kubernetes Isekai (異世界) is an open-source RPG designed for hands-on Kubernetes learning through gamification. Ideal for junior to Higher Diploma students of Hong Kong Institute of Information Technology (HKIIT), it transforms Kubernetes education into an engaging adventure.

1. Role-Playing Adventure: Students interact with NPCs who assign Kubernetes tasks.
2. Task-Based Learning: Tasks involve setting up and managing Kubernetes clusters.
3. Free Access: Uses AWS Academy Learner Lab with Minikube or Kubernetes.
4. Scalable Grading: AWS SAM application tests Kubernetes setups within AWS Lambda.
5. Progress Tracking: Students track progress and earn rewards.
6. This game offers practical Kubernetes experience in a fun, cost-effective way.
7. GenAI Chat: Integrates Generative AI to make NPC interactions more dynamic and fun, enhancing the overall learning experience.

This repository hosts a Web RPG game that you can fork and customize to your liking.

AWS SAM Repo for Backend

https://github.com/wongcyrus/k8s-grader

Kubernetes Unit Test for Game Rule

https://github.com/wongcyrus/k8s-game-rule

## Demo

[![#Kubernetes Isekai (Alpha) -  free #k8s #rpggame with free #awsacademy learner lab](https://img.youtube.com/vi/dIwNWwz681k/0.jpg)](https://youtu.be/dIwNWwz681k)


## Setup

### Install the latest AWS SAM.
```
./aws_sam_setup.sh
```
###
Create Python Virtural environment and install dependances.
```
./create_virtural_env.sh
```
### Configure AWS Credentials 
Method 1: Set the token with CLI (Prefered)
```
aws configure
aws configure set aws_session_token <Session Token>
```
Method 2: Configure AWS Account for AWS Academy Learner Lab 
```
export AWS_ACCESS_KEY_ID=ASIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_SESSION_TOKEN=AQoDYXdzEJr...<remainder of session token>
export AWS_DEFAULT_REGION=us-east-1
```

## Deploy the SAM 
Generate a secret hash.
```
cd tools
python genkey.py
```
Deploy the SAM stack with the generated secret hash:
```
./deploy.sh "SecretHash"
```
If you do not set the secret hash, the default one will be used.

Clone the [Google Spreadsheet](https://docs.google.com/spreadsheets/d/1VdQsc9qslvd-gGhydN5dEZEX6Q5uliBQqRguJyHBZM4/edit?gid=0#gid=0) and customize the NPC backgrounds as desired. Modify the `NCPBackgroundSheetId` before deployment to import your personalized NPC backgrounds.

For development, if you want to reset the game, run the following commands
```
cd tools
python reset_game.py
```
It will delete all game state related items.

## Minikube for exercise

A Minikube endpoint accessible via the internet is required, and must remain confidential.  Deployment options include EC2 or Codespaces.

### Deploy Minikube with CloudFormation
After configure the AWS Credentials, then run.
```
cd k8s/minikube
aws cloudformation create-stack --stack-name minikube-stack --template-body file://minikube.yaml
```
Describe Stack
```
aws cloudformation describe-stacks --stack-name minikube-stack --query 'Stacks[0].Outputs'
```

Delete Minikube
```
aws cloudformation delete-stack --stack-name minikube-stack
```

### Deploy Minikube with GitHub CodeSpaces

1. Create CodeSpaces with devcontainer.json
```
{	
	"features": {
		"ghcr.io/devcontainers/features/docker-in-docker:2": {},
		"ghcr.io/devcontainers/features/kubectl-helm-minikube:1": {}
	}
}
```
2. Starts a Minikube 
```
minikube start --apiserver-ips=0.0.0.0 --driver=docker --force
```
3. Start proxy
```
kubectl proxy --address=0.0.0.0 --accept-hosts='.*'
```
4. **VERY IMPORTANT** Make port 8081 public

<img src="https://i.sstatic.net/YGIVx.png" alt="Set Public Port" width="50%">

5. Get the client.crt and client.key from ```/home/vscode/.minikube/profiles/minikube``` .
```
cp /home/vscode/.minikube/profiles/minikube/client.crt /workspaces/k8s-grader/k8s/minikube/downloaded_files
cp /home/vscode/.minikube/profiles/minikube/client.key /workspaces/k8s-grader/k8s/minikube/downloaded_files
```


## Minikube dashboard
For more information on how to make the Minikube dashboard accessible on all IPs (0.0.0.0), refer to [this link](https://unix.stackexchange.com/questions/621369/how-can-i-make-the-minikube-dashboard-answer-on-all-ips-0-0-0-0).

Open a new terminal and ensure the command runs continuously.
```
minikube dashboard --url
```


## Configure Minikube to accept external connections. (VERY IMPORTANT)
Open a new terminal and ensure the command runs continuously.
**To make the API call working, you must start the kubectl proxy!**
```
kubectl proxy --address=0.0.0.0 --accept-hosts='.*'
```
All tests will fail if the proxy is not running.


Sample Data
```
{
 "email": "cywong@vtc.edu.hk",
 "client_certificate": "-----BEGIN RSA PRIVATE KEY-----XXX-----END RSA PRIVATE KEY-----\n",
 "client_key": "-----BEGIN CERTIFICATE-----XX-----END CERTIFICATE-----\n",
 "endpoint": "http://3.90.40.12:8001"
}
```
**Please note that is http but not https!**

## Get the minikube key
1. Download labsuser.pem from AWS Academy Learner Lab
2. Upload to k8s/minikube
3. Open Terminal and run ```chmod 400 labsuser.pem```
4. Run 
```
cd k8s/minikube
./download_key.sh
```


## Local Development

To enable auto-completion 
1. Run ```./create_virtural_env.sh```
2. Set Python Interpreter to ```./venv/bin/python```

Install Kubectl command tools for Unit Test
https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/

1. Run ```./check_minikube_status.sh``` to ensure minikube us running.
2. Run ```./run_kube_proxy.sh ``` to start kube proxy for remote connection.


### Run Local Lambda test
For the first time, generate the env.json.
```
cd k8s-grader-api/events
python set_env.py
```
Test Lambda
```
sam build && sam local invoke GameTaskFunction --event events/event.json --env-vars events/env.json
sam build && sam local invoke GraderFunction --event events/event.json --env-vars events/env.json
```
Test Web API
```
sam build && sam local start-api --log-file log.txt --warm-containers LAZY --env-vars events/env.json
```

API call sequence
1. Register k8s account http://127.0.0.1:3000/save-k8s-account
2. Get Game Task http://127.0.0.1:3000/game-task?game=game01
3. Check setup is ready http://127.0.0.1:3000/grader?game=game01&phrase=ready
4. Work on the answer.
5. Run challenge http://127.0.0.1:3000/grader?game=game01&phrase=challenge
6. Check Result http://127.0.0.1:3000/grader?&game=game01&phrase=check
7. Go back to 2. until it reply "All tasks are completed!"
All API call requires "x-api-key" in header.


## Core Developers
Students from [Higher Diploma in Cloud and Data Centre Administration](https://www.vtc.edu.hk/admission/en/programme/it114115-higher-diploma-in-cloud-and-data-centre-administration/)

- [錢弘毅](https://www.linkedin.com/in/hongyi-qian-a71b17290/)
- [Ho Chun Sun Don (何俊申)](https://www.linkedin.com/in/ho-chun-sun-don-%E4%BD%95%E4%BF%8A%E7%94%B3-660a94290/)
- [Kit Fong Loo](https://www.linkedin.com/in/kit-fong-loo-910482347/)
- [Yuehan WU](https://www.linkedin.com/in/yuehan-wu-a40612290/)

