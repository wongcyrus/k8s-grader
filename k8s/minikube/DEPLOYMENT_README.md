# Minikube Deployment Scripts

This directory contains scripts to deploy and manage a Minikube instance on AWS EC2 using CloudFormation.

## Latest AMI

The CloudFormation template dynamically fetches the latest Amazon Linux 2023 AMI using AWS Systems Manager Parameter Store:
- **Parameter**: `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64`
- **Benefit**: Always deploys with the latest Amazon Linux 2023 AMI automatically
- **Region**: us-east-1

This ensures you're always using the most up-to-date AMI with the latest security patches without manual updates.

## Quick Start

### Deploy Minikube

```bash
cd /workspaces/k8s-grader/k8s/minikube
./deploy_minikube.sh
```

This script will:
1. Create a new EC2 key pair (`minikube-keypair`) if it doesn't exist
2. Save the private key to `minikube-keypair.pem` (chmod 400)
3. Deploy the CloudFormation stack with all required resources
4. Output the instance IP and SSH command
5. Save the endpoint URL to `endpoint.txt`

### Undeploy Minikube

```bash
cd /workspaces/k8s-grader/k8s/minikube
./undeploy_minikube.sh
```

This script will:
1. Delete the CloudFormation stack
2. Optionally delete the EC2 key pair from AWS
3. Optionally delete the local key file
4. Clean up the `endpoint.txt` file

## Resources Created

The CloudFormation stack creates:
- **EC2 Instance**: t3.medium with 30GB EBS volume
- **Security Group**: Allows all traffic (⚠️ adjust for production use)
- **Elastic IP**: Static public IP address
- **Minikube**: Pre-installed and configured with Docker driver
- **kubectl**: Pre-installed Kubernetes CLI

## Configuration

You can modify the following in the scripts:

### deploy_minikube.sh
- `STACK_NAME`: CloudFormation stack name (default: `minikube-stack`)
- `KEY_PAIR_NAME`: EC2 key pair name (default: `minikube-keypair`)
- `REGION`: AWS region (default: `us-east-1`)

### minikube.yaml (CloudFormation Template)
- `InstanceType`: EC2 instance type (default: `t3.medium`)
- `LatestAmiId`: SSM Parameter path for AMI (default: dynamically fetched from Parameter Store)
- `VolumeSize`: EBS volume size (default: 30GB)

You can override the AMI parameter during deployment:
```bash
aws cloudformation deploy \
    --template-file minikube.yaml \
    --stack-name minikube-stack \
    --parameter-overrides \
        KeyName=minikube-keypair \
        LatestAmiId=/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64
```

## SSH Access

After deployment, connect to the instance:

```bash
ssh -i minikube-keypair.pem ec2-user@<INSTANCE_IP>
```

The instance IP is displayed after deployment and saved to `endpoint.txt`.

## Checking Minikube Status

Once logged in:

```bash
# Check Minikube status
minikube status

# Check Kubernetes nodes
kubectl get nodes

# Access Kubernetes dashboard
minikube dashboard --url

# Get all pods
kubectl get pods -A
```

## Troubleshooting

### Stack Creation Timeout
The stack waits for Minikube to fully initialize (10 minutes timeout). If it fails:
1. Check the EC2 instance system log in AWS Console
2. SSH into the instance and check: `sudo tail -f /var/log/cloud-init-output.log`

### SSH Connection Issues
- Ensure the security group allows SSH from your IP
- Verify the key file permissions: `chmod 400 minikube-keypair.pem`
- Check that you're using the correct key file

### Minikube Not Starting
SSH into the instance and try:
```bash
minikube stop
minikube start --driver=docker
```

## Cost Considerations

Running this infrastructure incurs AWS costs:
- t3.medium instance: ~$0.04/hour
- Elastic IP: Free when associated with running instance
- EBS storage: ~$0.10/GB-month

Remember to run `./undeploy_minikube.sh` when done to avoid charges.

## Security Notes

⚠️ **Important**: The default security group allows all traffic from anywhere (0.0.0.0/0). 

For production use, restrict access:
1. Modify the `SecurityGroupIngress` in `minikube.yaml`
2. Allow only specific IPs and ports
3. Use AWS Systems Manager Session Manager instead of SSH

## Additional Scripts

- `start_minikube_remote.sh`: Start/restart Minikube on existing instance
- `check_minikube_status.sh`: Check status of remote Minikube
- `run_kube_proxy.sh`: Set up kubectl proxy access
- `download_key.sh`: Download Kubernetes credentials
